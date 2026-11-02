"""
Digital Safety QR API (all under /api/safety/, JWT required).

Family routes reuse the family app's scoping: someone outside the circle gets
404. Scanning is separate and needs a SafetyHelper record. Anyone else gets the
same 403 before the token is looked at, so scanning can't test whether a token
is real. Nothing here returns a phone number.
"""

from django.conf import settings
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.throttling import UserRateThrottle

from apps.family import policy as family_policy
from apps.family.views import _Family, audit, error, forbidden, ok
from apps.safety import policy, serializers
from apps.safety.models import (
    SafetyAlert,
    SafetyHelper,
    SafetyQRIdentity,
    SafetyScanLog,
    hash_token,
)
from apps.safety.notifications import notify_family
from apps.safety.signals import alert_confirmed


class ScanThrottle(UserRateThrottle):
    scope = "safety_scan"
    rate = "120/hour"


class QrChangeThrottle(UserRateThrottle):
    scope = "safety_qr_change"
    rate = "30/hour"


def _private(response):
    response["Cache-Control"] = "no-store"
    return response


class _Safety(_Family):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self._insecure = settings.SAFETY_REQUIRE_HTTPS and not request.is_secure()

    def handle_insecure(self):
        return error({"detail": "This needs a secure connection."})


class _MemberQr(_Safety):
    def target(self, request, family_id, member_id):
        """The member, once the requester may see their QR. Being organizer
        isn't enough for an adult: an adult's QR stays with that adult."""
        actor = self.actor_for(request, family_id)
        member = self.member(actor, member_id)
        return member if family_policy.can_view_qr(actor, member) else None

    def active(self, member):
        return member.safety_qrs.filter(status=SafetyQRIdentity.Status.ACTIVE).select_related("member__user").first()

    def respond(self, identity, code=status.HTTP_200_OK):
        if identity.payload is None:
            return error({"detail": "The server key changed. Generate a new QR."}, status.HTTP_409_CONFLICT)
        return _private(ok(serializers.IdentitySerializer(identity).data, code))

    def create(self, member, user):
        """Safe against two guardians pressing at once: the database allows
        one active QR, and whoever loses gets the winner's."""
        try:
            with transaction.atomic():
                identity = SafetyQRIdentity.objects.create(member=member, created_by=user)
            audit(member.family, user, "safety_qr_created", member)
            return identity, True
        except IntegrityError:
            return self.active(member), False


class MemberQrAPI(_MemberQr):
    def get_throttles(self):
        return [QrChangeThrottle()] if self.request.method == "POST" else []

    def get(self, request, family_id, member_id):
        if self._insecure:
            return self.handle_insecure()
        member = self.target(request, family_id, member_id)
        if member is None:
            return forbidden()
        identity = self.active(member)
        if identity is None:
            return _private(ok(None))
        return self.respond(identity)

    def post(self, request, family_id, member_id):
        """Returns the active QR, making one if there is none."""
        if self._insecure:
            return self.handle_insecure()
        member = self.target(request, family_id, member_id)
        if member is None:
            return forbidden()
        identity = self.active(member)
        created = False
        if identity is None:
            identity, created = self.create(member, request.user)
        return self.respond(identity, status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class MemberQrRevokeAPI(_MemberQr):
    throttle_classes = [QrChangeThrottle]

    @transaction.atomic
    def post(self, request, family_id, member_id):
        member = self.target(request, family_id, member_id)
        if member is None:
            return forbidden()
        identity = member.safety_qrs.select_for_update().filter(status=SafetyQRIdentity.Status.ACTIVE).first()
        if identity is None:
            return error({"detail": "There's no active QR."}, status.HTTP_409_CONFLICT)
        identity.revoke(request.user)
        audit(member.family, request.user, "safety_qr_revoked", member)
        return _private(ok({"status": identity.status, "revoked_at": identity.revoked_at}))


class MemberQrRegenerateAPI(_MemberQr):
    throttle_classes = [QrChangeThrottle]

    def post(self, request, family_id, member_id):
        if self._insecure:
            return self.handle_insecure()
        member = self.target(request, family_id, member_id)
        if member is None:
            return forbidden()
        with transaction.atomic():
            for identity in member.safety_qrs.select_for_update().filter(status=SafetyQRIdentity.Status.ACTIVE):
                identity.revoke(request.user)
            identity, _ = self.create(member, request.user)
        return self.respond(identity, status.HTTP_201_CREATED)


class HelperStatusAPI(_Safety):
    def get(self, request):
        helper = SafetyHelper.current_for(request.user)
        return ok({"is_helper": helper is not None, "role": helper.role if helper else None})


class ScanResolveAPI(_Safety):
    """Checked in this order so a non-helper learns nothing about the token."""

    throttle_classes = [ScanThrottle]

    def log(self, request, outcome, identity=None):
        return SafetyScanLog.objects.create(user=request.user, identity=identity, outcome=outcome)

    def post(self, request):
        if self._insecure:
            return self.handle_insecure()
        helper = SafetyHelper.current_for(request.user)
        if helper is None:
            self.log(request, SafetyScanLog.Outcome.DENIED)
            return forbidden()
        token = request.data.get("token")
        identity = None
        if isinstance(token, str) and token:
            identity = (
                SafetyQRIdentity.objects.select_related("member__user", "member__family")
                .filter(token_hash=hash_token(token)).first()
            )
        if identity is None:
            self.log(request, SafetyScanLog.Outcome.UNKNOWN)
            return error({"detail": "This isn't a valid safety QR."}, status.HTTP_404_NOT_FOUND)
        if not identity.is_usable:
            self.log(request, SafetyScanLog.Outcome.REVOKED, identity)
            return error({"detail": "This safety QR is no longer active."}, status.HTTP_410_GONE)

        scan = self.log(request, SafetyScanLog.Outcome.RESOLVED, identity)
        identity.last_scanned_at = timezone.now()
        identity.save(update_fields=["last_scanned_at"])
        member = identity.member
        audit(member.family, request.user, "safety_qr_scanned", member)
        open_alerts = member.safety_alerts.filter(status__in=SafetyAlert.OPEN_STATUSES)
        return _private(ok({
            "scan_id": str(scan.pk),
            "first_name": serializers.first_name_of(member),
            "category": serializers.category_of(member),
            "language": member.language,
            "open_alerts": [{"kind": a.kind, "reference": a.reference} for a in open_alerts],
            "valid_seconds": int(SafetyScanLog.VALID_FOR.total_seconds()),
        }))


class ScanConfirmAPI(_Safety):
    """The helper's decision. A scan alone never reaches this."""

    def create_alert(self, scan, helper, data, request):
        identity = scan.identity
        member = identity.member
        kind = data["situation"]
        existing = member.safety_alerts.filter(kind=kind, status__in=SafetyAlert.OPEN_STATUSES).first()
        if existing:
            return existing, False
        try:
            with transaction.atomic():
                alert = SafetyAlert.objects.create(
                    family=member.family, member=member, identity=identity, kind=kind, helper=request.user,
                    helper_role=helper.role, note=data.get("note", "").strip(),
                    latitude=data.get("latitude"), longitude=data.get("longitude"),
                )
        except IntegrityError:
            return member.safety_alerts.get(kind=kind, status__in=SafetyAlert.OPEN_STATUSES), False
        audit(member.family, request.user, "safety_alert_created", member, kind=kind)
        return alert, True

    def post(self, request, scan_id):
        if self._insecure:
            return self.handle_insecure()
        helper = SafetyHelper.current_for(request.user)
        if helper is None:
            return forbidden()
        scan = get_object_or_404(
            SafetyScanLog.objects.select_related("identity__member__family", "alert"),
            pk=scan_id, user=request.user, outcome=SafetyScanLog.Outcome.RESOLVED,
        )
        # Pressing twice gives the same result, not a second report.
        if scan.confirmed_at:
            if scan.alert:
                return ok({**serializers.HelperAlertSerializer(scan.alert).data, "duplicate": True})
            return ok({"recorded": True})
        if not scan.is_fresh or scan.identity is None or not scan.identity.is_usable:
            return error({"detail": "This scan has expired. Scan the QR again."}, status.HTTP_410_GONE)
        serializer = serializers.ConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        data = serializer.validated_data
        scan.situation = data["situation"]
        scan.confirmed_at = timezone.now()
        if data["situation"] == "suspicious":
            # For review only. The family isn't alarmed by a doubtful scan.
            scan.save(update_fields=["situation", "confirmed_at"])
            audit(scan.identity.member.family, request.user, "safety_scan_flagged", scan.identity.member)
            return ok({"recorded": True})
        alert, created = self.create_alert(scan, helper, data, request)
        scan.alert = alert
        scan.save(update_fields=["situation", "confirmed_at", "alert"])
        if created:
            notify_family(alert)
            alert_confirmed.send(sender=SafetyAlert, alert=alert)
        body = {**serializers.HelperAlertSerializer(alert).data, "duplicate": not created}
        return ok(body, status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class HelperAlertAPI(_Safety):
    """A helper can follow only reports they made."""

    def get(self, request, alert_id):
        if SafetyHelper.current_for(request.user) is None:
            return forbidden()
        alert = get_object_or_404(SafetyAlert, pk=alert_id, helper=request.user)
        return ok(serializers.HelperAlertSerializer(alert).data)


class _FamilyAlerts(_Safety):
    def context(self, request, actor):
        return {"request": request, "actor": actor}

    def alert(self, actor, alert_id):
        """404 rather than 403: someone who can't review it shouldn't learn of it."""
        alert = get_object_or_404(
            SafetyAlert.objects.select_for_update(of=("self",)).select_related("member__user"),
            pk=alert_id, family=actor.family,
        )
        if not policy.can_review_alert(actor, alert.member):
            alert = None
        return alert


class FamilyAlertListAPI(_FamilyAlerts):
    def get(self, request, family_id):
        actor = self.actor_for(request, family_id)
        alerts = (
            SafetyAlert.objects.filter(family=actor.family)
            .select_related("member__user").prefetch_related("member__guardian_links")
        )
        visible = [a for a in alerts[:100] if policy.can_review_alert(actor, a.member)]
        return ok(serializers.FamilyAlertSerializer(visible, many=True, context=self.context(request, actor)).data)


class FamilyAlertAckAPI(_FamilyAlerts):
    @transaction.atomic
    def post(self, request, family_id, alert_id):
        actor = self.actor_for(request, family_id)
        alert = self.alert(actor, alert_id)
        if alert is None:
            return error({"detail": "Not found."}, status.HTTP_404_NOT_FOUND)
        if alert.status == SafetyAlert.Status.OPEN:
            alert.status = SafetyAlert.Status.ACKNOWLEDGED
            alert.acknowledged_at = timezone.now()
            alert.acknowledged_by = request.user
            alert.save(update_fields=["status", "acknowledged_at", "acknowledged_by"])
            audit(actor.family, request.user, "safety_alert_acknowledged", alert.member)
        return ok(serializers.FamilyAlertSerializer(alert, context=self.context(request, actor)).data)


class FamilyAlertResolveAPI(_FamilyAlerts):
    @transaction.atomic
    def post(self, request, family_id, alert_id):
        actor = self.actor_for(request, family_id)
        alert = self.alert(actor, alert_id)
        if alert is None:
            return error({"detail": "Not found."}, status.HTTP_404_NOT_FOUND)
        if alert.status != SafetyAlert.Status.RESOLVED:
            alert.status = SafetyAlert.Status.RESOLVED
            alert.resolved_at = timezone.now()
            alert.resolved_by = request.user
            alert.save(update_fields=["status", "resolved_at", "resolved_by"])
            audit(actor.family, request.user, "safety_alert_resolved", alert.member)
        return ok(serializers.FamilyAlertSerializer(alert, context=self.context(request, actor)).data)
