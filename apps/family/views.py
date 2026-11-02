"""
Family Safety Circle API (all under /api/family/, JWT required).

Lookups start from the requester's own membership, so another family's circle,
member or contact answers 404, the same as one that doesn't exist. Nothing here
sends a message: invitations are shared by the organizer, or wait in-app.
"""

import uuid

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.family import policy, serializers
from apps.family.models import (
    EmergencyContact,
    FamilyAuditLog,
    FamilyCircle,
    FamilyInvitation,
    FamilyMember,
    GuardianLink,
    MemberPhoto,
    clean_code,
    hash_code,
    invite_link,
    new_code,
    new_link_token,
    normalize_mobile,
)
from apps.website.images import sniff

MAX_PHOTO_BYTES = 2 * 1024 * 1024
_PHOTO_TYPES = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}


def ok(data, code=status.HTTP_200_OK):
    return Response({"status": "success", "data": data}, status=code)


def error(errors, code=status.HTTP_400_BAD_REQUEST):
    return Response({"status": "error", "errors": errors}, status=code)


def forbidden():
    return error({"detail": "You don't have permission to do this."}, status.HTTP_403_FORBIDDEN)


def audit(family, actor, action, target=None, **details):
    FamilyAuditLog.objects.create(
        family=family, family_ref=family.pk, actor=actor, action=action,
        target_member=target.pk if target else None, details=details,
    )


class InviteCodeThrottle(UserRateThrottle):
    """Slows anyone trying to guess codes."""

    scope = "family_invite_code"
    rate = "20/hour"


class _Family(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def actor_for(self, request, family_id):
        """The requester's membership. 404 for anyone outside the circle."""
        return get_object_or_404(
            FamilyMember.objects.select_related("family", "user"), family_id=family_id, user=request.user,
        )

    def member(self, actor, member_id):
        return get_object_or_404(
            FamilyMember.objects.select_related("user").prefetch_related(
                "guardian_links__guardian__user",
            ),
            pk=member_id, family=actor.family,
        )

    def context(self, request, actor):
        return {"request": request, "actor": actor}


def _members(family):
    return family.members.select_related("user", "photo").prefetch_related("guardian_links__guardian__user")


def _circles_for(user):
    return FamilyCircle.objects.filter(members__user=user).prefetch_related("members").distinct()


class CircleListAPI(_Family):
    def get(self, request):
        circles = _circles_for(request.user)
        return ok(serializers.CircleSerializer(circles, many=True, context={"request": request}).data)

    @transaction.atomic
    def post(self, request):
        if FamilyMember.objects.filter(user=request.user).count() >= FamilyCircle.MAX_PER_USER:
            return error({"non_field_errors": [f"You can be in up to {FamilyCircle.MAX_PER_USER} family circles."]})
        serializer = serializers.CircleSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return error(serializer.errors)
        family = serializer.save()
        me = FamilyMember.objects.create(
            family=family, user=request.user, kind=FamilyMember.Kind.ACCOUNT_HOLDER,
            role=FamilyMember.Role.ORGANIZER, relationship=FamilyMember.Relationship.SELF,
            language=family.language,
        )
        audit(family, request.user, "family_created", me)
        data = serializers.CircleSerializer(family, context={"request": request}).data
        return ok(data, status.HTTP_201_CREATED)


class CircleDetailAPI(_Family):
    def get(self, request, family_id):
        actor = self.actor_for(request, family_id)
        family = FamilyCircle.objects.prefetch_related("members").get(pk=actor.family_id)
        return ok(serializers.CircleSerializer(family, context={"request": request}).data)

    def patch(self, request, family_id):
        actor = self.actor_for(request, family_id)
        if not policy.can_manage_family(actor):
            return forbidden()
        allowed = {k: v for k, v in request.data.items() if k in ("name", "description", "language")}
        serializer = serializers.CircleSerializer(
            actor.family, data=allowed, partial=True, context={"request": request},
        )
        if not serializer.is_valid():
            return error(serializer.errors)
        serializer.save()
        audit(actor.family, request.user, "family_updated", fields=sorted(allowed))
        return ok(serializer.data)

    @transaction.atomic
    def delete(self, request, family_id):
        actor = self.actor_for(request, family_id)
        if not policy.can_manage_family(actor):
            return forbidden()
        if actor.family.members.filter(user__isnull=False).exclude(pk=actor.pk).exists():
            return error({"non_field_errors": [
                "Other adults are in this family. They need to leave first, or hand the organizer role to one of them.",
            ]}, status.HTTP_409_CONFLICT)
        audit(actor.family, request.user, "family_deleted")
        actor.family.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _reassign_dependents(family, leaving, by):
    """No dependent is ever left without someone responsible."""
    organizer = family.members.filter(role=FamilyMember.Role.ORGANIZER).first()
    for link in leaving.dependent_links.select_related("dependent"):
        dependent = link.dependent
        if not dependent.guardian_links.exclude(guardian=leaving).exists() and organizer:
            GuardianLink.objects.get_or_create(dependent=dependent, guardian=organizer)
            audit(family, by, "guardian_reassigned", dependent)


class CircleLeaveAPI(_Family):
    @transaction.atomic
    def post(self, request, family_id):
        actor = self.actor_for(request, family_id)
        if policy.is_organizer(actor):
            return error({"non_field_errors": [
                "Hand the organizer role to another adult first, or delete the family.",
            ]}, status.HTTP_409_CONFLICT)
        _reassign_dependents(actor.family, actor, request.user)
        if actor.family.organizer_offer_id == actor.pk:
            actor.family.organizer_offer = None
            actor.family.save(update_fields=["organizer_offer", "updated_at"])
        audit(actor.family, request.user, "member_left", actor)
        actor.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class OrganizerOfferAPI(_Family):
    """The organizer offers the role; it only moves when the adult accepts."""

    def post(self, request, family_id):
        actor = self.actor_for(request, family_id)
        if not policy.can_manage_family(actor):
            return forbidden()
        target = self.member(actor, request.data.get("member_id"))
        if target.is_dependent or target.pk == actor.pk:
            return error({"member_id": "Choose another adult in the family."})
        actor.family.organizer_offer = target
        actor.family.save(update_fields=["organizer_offer", "updated_at"])
        audit(actor.family, request.user, "organizer_offered", target)
        return ok({"offered_to": str(target.pk)})


class OrganizerAcceptAPI(_Family):
    @transaction.atomic
    def post(self, request, family_id):
        actor = self.actor_for(request, family_id)
        family = FamilyCircle.objects.select_for_update().get(pk=actor.family_id)
        # An organizer who deleted their account leaves the role open to any adult.
        vacant = not family.members.filter(role=FamilyMember.Role.ORGANIZER).exists()
        if family.organizer_offer_id != actor.pk and not vacant:
            return forbidden()
        FamilyMember.objects.filter(family=family, role=FamilyMember.Role.ORGANIZER).update(
            role=FamilyMember.Role.MEMBER,
        )
        actor.role = FamilyMember.Role.ORGANIZER
        actor.save(update_fields=["role", "updated_at"])
        family.organizer_offer = None
        family.save(update_fields=["organizer_offer", "updated_at"])
        audit(family, request.user, "organizer_changed", actor)
        return ok({"role": actor.role})


class MemberListAPI(_Family):
    def get(self, request, family_id):
        actor = self.actor_for(request, family_id)
        return ok(serializers.MemberSerializer(
            _members(actor.family), many=True, context=self.context(request, actor),
        ).data)

    @transaction.atomic
    def post(self, request, family_id):
        """Adds a dependent. Adults can only join by accepting an invitation."""
        actor = self.actor_for(request, family_id)
        if not policy.can_manage_family(actor):
            return forbidden()
        if actor.family.members.count() >= FamilyCircle.MAX_MEMBERS:
            return error({"non_field_errors": [f"A family can have up to {FamilyCircle.MAX_MEMBERS} members."]})
        serializer = serializers.DependentInputSerializer(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        member = FamilyMember.objects.create(family=actor.family, **serializer.validated_data)
        GuardianLink.objects.create(dependent=member, guardian=actor)
        audit(actor.family, request.user, "dependent_added", member, consent_basis=member.consent_basis)
        member = self.member(actor, member.pk)
        return ok(
            serializers.MemberDetailSerializer(member, context=self.context(request, actor)).data,
            status.HTTP_201_CREATED,
        )


class MemberDetailAPI(_Family):
    def get(self, request, family_id, member_id):
        actor = self.actor_for(request, family_id)
        member = self.member(actor, member_id)
        return ok(serializers.MemberDetailSerializer(member, context=self.context(request, actor)).data)

    def patch(self, request, family_id, member_id):
        actor = self.actor_for(request, family_id)
        member = self.member(actor, member_id)
        data = dict(request.data)
        relationship = data.pop("relationship", None)
        if relationship is not None and not policy.can_edit_relationship(actor, member):
            return forbidden()
        if data and not policy.can_edit_profile(actor, member):
            return forbidden()
        if member.is_dependent:
            serializer = serializers.DependentUpdateSerializer(member, data=data, partial=True)
        else:
            serializer = serializers.AdultUpdateSerializer(data=data, partial=True)
        if not serializer.is_valid():
            return error(serializer.errors)
        changes = dict(serializer.validated_data)
        if relationship is not None:
            valid = FamilyMember.Relationship.values
            if relationship not in valid:
                return error({"relationship": "Choose a relationship."})
            changes["relationship"] = relationship
        for field, value in changes.items():
            setattr(member, field, value)
        member.save()
        if {"share_phone", "share_contacts_with_organizer", "location_sharing_consent"} & set(changes):
            audit(actor.family, request.user, "privacy_changed", member, fields=sorted(changes))
        else:
            audit(actor.family, request.user, "member_updated", member, fields=sorted(changes))
        return ok(serializers.MemberDetailSerializer(member, context=self.context(request, actor)).data)

    @transaction.atomic
    def delete(self, request, family_id, member_id):
        actor = self.actor_for(request, family_id)
        member = self.member(actor, member_id)
        if not policy.can_remove(actor, member):
            return forbidden()
        _reassign_dependents(actor.family, member, request.user)
        audit(actor.family, request.user, "member_removed", member, kind=member.kind)
        member.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MemberPhotoAPI(_Family):
    parser_classes = [MultiPartParser]

    def get(self, request, family_id, member_id):
        actor = self.actor_for(request, family_id)
        member = self.member(actor, member_id)
        photo = get_object_or_404(MemberPhoto, member=member)
        response = HttpResponse(bytes(photo.data), content_type=photo.content_type)
        response["Cache-Control"] = "private, no-store"
        return response

    def put(self, request, family_id, member_id):
        actor = self.actor_for(request, family_id)
        member = self.member(actor, member_id)
        if not policy.can_edit_profile(actor, member):
            return forbidden()
        upload = request.FILES.get("photo")
        if upload is None or upload.size > MAX_PHOTO_BYTES:
            return error({"photo": "Choose a photo under 2 MB."})
        data = upload.read()
        # Identified by its bytes: the file's own name and type can't be trusted.
        content_type = _PHOTO_TYPES.get(sniff(data))
        if content_type is None:
            return error({"photo": "Use a JPG, PNG or WebP photo."})
        MemberPhoto.objects.update_or_create(member=member, defaults={"content_type": content_type, "data": data})
        audit(actor.family, request.user, "photo_changed", member)
        return ok({"has_photo": True})

    def delete(self, request, family_id, member_id):
        actor = self.actor_for(request, family_id)
        member = self.member(actor, member_id)
        if not policy.can_edit_profile(actor, member):
            return forbidden()
        MemberPhoto.objects.filter(member=member).delete()
        audit(actor.family, request.user, "photo_removed", member)
        return Response(status=status.HTTP_204_NO_CONTENT)


class GuardianListAPI(_Family):
    def post(self, request, family_id, member_id):
        actor = self.actor_for(request, family_id)
        dependent = self.member(actor, member_id)
        if not policy.can_manage_guardians(actor, dependent):
            return forbidden()
        guardian = self.member(actor, request.data.get("member_id"))
        if guardian.is_dependent:
            return error({"member_id": "A guardian must be an adult with an account."})
        GuardianLink.objects.get_or_create(dependent=dependent, guardian=guardian)
        audit(actor.family, request.user, "guardian_added", dependent, guardian=str(guardian.pk))
        return ok(serializers.MemberDetailSerializer(
            self.member(actor, member_id), context=self.context(request, actor),
        ).data, status.HTTP_201_CREATED)


class GuardianDetailAPI(_Family):
    def delete(self, request, family_id, member_id, guardian_id):
        actor = self.actor_for(request, family_id)
        dependent = self.member(actor, member_id)
        if not policy.can_manage_guardians(actor, dependent):
            return forbidden()
        link = get_object_or_404(GuardianLink, dependent=dependent, guardian_id=guardian_id)
        if dependent.guardian_links.count() <= 1:
            return error({"non_field_errors": ["A dependent must always have a guardian."]}, status.HTTP_409_CONFLICT)
        link.delete()
        audit(actor.family, request.user, "guardian_removed", dependent, guardian=str(guardian_id))
        return Response(status=status.HTTP_204_NO_CONTENT)


class _Contacts(_Family):
    def owner(self, actor, member_id):
        return self.member(actor, member_id) if member_id else None

    def can_view(self, actor, owner):
        return True if owner is None else policy.can_view_contacts(actor, owner)

    def can_edit(self, actor, owner):
        return policy.can_edit_family_contacts(actor) if owner is None else policy.can_edit_contacts(actor, owner)

    def contacts(self, actor, owner):
        return EmergencyContact.objects.filter(family=actor.family, member=owner)


class ContactListAPI(_Contacts):
    """/circles/<id>/contacts/ for the family, or /members/<id>/contacts/ for one person."""

    def get(self, request, family_id, member_id=None):
        actor = self.actor_for(request, family_id)
        owner = self.owner(actor, member_id)
        if not self.can_view(actor, owner):
            return forbidden()
        return ok(serializers.EmergencyContactSerializer(self.contacts(actor, owner), many=True).data)

    def post(self, request, family_id, member_id=None):
        """An app working offline sends its own `id`, so a retried create after
        a lost response returns the first one instead of adding a duplicate."""
        actor = self.actor_for(request, family_id)
        owner = self.owner(actor, member_id)
        if not self.can_edit(actor, owner):
            return forbidden()
        existing = self.contacts(actor, owner)
        contact_id = None
        if request.data.get("id"):
            try:
                contact_id = uuid.UUID(str(request.data["id"]))
            except ValueError:
                return error({"id": "Not a valid id."})
            repeat = existing.filter(pk=contact_id).first()
            if repeat:
                return ok(serializers.EmergencyContactSerializer(repeat).data)
            if EmergencyContact.objects.filter(pk=contact_id).exists():
                return error({"id": "Not a valid id."})
        if existing.count() >= EmergencyContact.MAX_PER_OWNER:
            return error({"non_field_errors": [f"Up to {EmergencyContact.MAX_PER_OWNER} contacts."]})
        serializer = serializers.EmergencyContactSerializer(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        priority = (existing.aggregate(m=Max("priority"))["m"] or 0) + 1
        extra = {"pk": contact_id} if contact_id else {}
        try:
            with transaction.atomic():
                contact = serializer.save(family=actor.family, member=owner, priority=priority, **extra)
        except IntegrityError:
            repeat = existing.filter(pk=contact_id).first()
            if repeat is None:
                return error({"id": "Not a valid id."})
            return ok(serializers.EmergencyContactSerializer(repeat).data)
        audit(actor.family, request.user, "contact_added", owner)
        return ok(serializers.EmergencyContactSerializer(contact).data, status.HTTP_201_CREATED)


class ContactDetailAPI(_Contacts):
    """PATCH and DELETE take an optional `If-Match` with the `updated_at` the
    app last saw. If the contact has changed since, the answer is 412 with the
    current record, so a queued offline change can't overwrite newer data."""

    def contact(self, actor, contact_id):
        return get_object_or_404(
            EmergencyContact.objects.select_for_update(of=("self",)).select_related("member"),
            pk=contact_id, family=actor.family,
        )

    def stale(self, request, contact):
        """A response if the request's If-Match doesn't match, otherwise None."""
        raw = request.headers.get("If-Match")
        if not raw:
            return None
        try:
            seen = parse_datetime(raw.strip().strip('"'))
        except ValueError:
            seen = None
        if seen is None:
            return error({"if_match": "Not a valid timestamp."})
        if seen == contact.updated_at:
            return None
        return Response({
            "status": "error",
            "errors": {"detail": "This contact has changed since you last saw it."},
            "data": serializers.EmergencyContactSerializer(contact).data,
        }, status=status.HTTP_412_PRECONDITION_FAILED)

    @transaction.atomic
    def patch(self, request, family_id, contact_id):
        actor = self.actor_for(request, family_id)
        contact = self.contact(actor, contact_id)
        if not self.can_edit(actor, contact.member):
            return forbidden()
        stale = self.stale(request, contact)
        if stale:
            return stale
        serializer = serializers.EmergencyContactSerializer(contact, data=request.data, partial=True)
        if not serializer.is_valid():
            return error(serializer.errors)
        serializer.save()
        audit(actor.family, request.user, "contact_updated", contact.member)
        return ok(serializer.data)

    @transaction.atomic
    def delete(self, request, family_id, contact_id):
        actor = self.actor_for(request, family_id)
        contact = self.contact(actor, contact_id)
        if not self.can_edit(actor, contact.member):
            return forbidden()
        stale = self.stale(request, contact)
        if stale:
            return stale
        audit(actor.family, request.user, "contact_removed", contact.member)
        contact.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ContactReorderAPI(_Contacts):
    """POST {"contact_ids": [...], "member_id": optional}: the full new order."""

    @transaction.atomic
    def post(self, request, family_id):
        actor = self.actor_for(request, family_id)
        owner = self.owner(actor, request.data.get("member_id"))
        if not self.can_edit(actor, owner):
            return forbidden()
        contacts = {str(c.pk): c for c in self.contacts(actor, owner)}
        ids = [str(i) for i in request.data.get("contact_ids") or []]
        if sorted(ids) != sorted(contacts):
            return error({"contact_ids": "Send every contact exactly once."})
        for priority, contact_id in enumerate(ids, start=1):
            contacts[contact_id].priority = priority
        EmergencyContact.objects.bulk_update(contacts.values(), ["priority"])
        ordered = sorted(contacts.values(), key=lambda c: c.priority)
        return ok(serializers.EmergencyContactSerializer(ordered, many=True).data)


class InvitationListAPI(_Family):
    def get(self, request, family_id):
        actor = self.actor_for(request, family_id)
        if not policy.can_manage_family(actor):
            return forbidden()
        return ok(serializers.InvitationSerializer(actor.family.invitations.all()[:30], many=True).data)

    def post(self, request, family_id):
        """Returns the code and link once. With `phone`, it also waits in that
        person's app. The reply is the same whether or not they have an account."""
        actor = self.actor_for(request, family_id)
        if not policy.can_manage_family(actor):
            return forbidden()
        relationship = request.data.get("relationship")
        if relationship not in FamilyMember.Relationship.values or relationship == "self":
            return error({"relationship": "Choose how they're related to the family."})
        phone = ""
        if request.data.get("phone"):
            phone = normalize_mobile(request.data["phone"])
            if phone is None:
                return error({"phone": "Enter a valid 10-digit mobile number."})
        now = timezone.now()
        open_count = actor.family.invitations.filter(status="pending", expires_at__gt=now).count()
        if open_count >= FamilyInvitation.MAX_PENDING:
            return error({"non_field_errors": ["Too many open invitations. Revoke one first."]})
        code = new_code()
        token = new_link_token()
        invitation = FamilyInvitation.objects.create(
            family=actor.family, code_hash=hash_code(code), link_hash=hash_code(token), invited_phone=phone,
            relationship=relationship, expires_at=now + FamilyInvitation.VALID_FOR, created_by=request.user,
        )
        audit(actor.family, request.user, "invitation_created", in_app=bool(phone))
        data = dict(serializers.InvitationSerializer(invitation).data)
        # Shown this once; only the hashes are kept.
        data["code"] = code
        data["link"] = invite_link(token)
        return ok(data, status.HTTP_201_CREATED)


class InvitationRevokeAPI(_Family):
    def post(self, request, family_id, invitation_id):
        actor = self.actor_for(request, family_id)
        if not policy.can_manage_family(actor):
            return forbidden()
        invitation = get_object_or_404(FamilyInvitation, pk=invitation_id, family=actor.family)
        if invitation.status != FamilyInvitation.Status.PENDING:
            return error({"non_field_errors": ["This invitation is no longer open."]}, status.HTTP_409_CONFLICT)
        invitation.status = FamilyInvitation.Status.REVOKED
        invitation.save(update_fields=["status"])
        audit(actor.family, request.user, "invitation_revoked")
        return ok(serializers.InvitationSerializer(invitation).data)


class _Respond(_Family):
    throttle_classes = [InviteCodeThrottle]

    def find(self, request, lock=False):
        """By link token, code, or id for an in-app invitation to this user's
        number. Anything else is the same 404, so nothing can be probed."""
        queryset = FamilyInvitation.objects.select_related("family")
        if lock:
            queryset = queryset.select_for_update(of=("self",))
        token = request.data.get("token")
        code = clean_code(request.data.get("code"))
        if isinstance(token, str) and token:
            invitation = queryset.filter(link_hash=hash_code(token)).first()
        elif code:
            invitation = queryset.filter(code_hash=hash_code(code)).first()
        elif request.data.get("invitation_id") and request.user.phone_number:
            invitation = queryset.filter(
                pk=request.data["invitation_id"], invited_phone=request.user.phone_number,
            ).first()
        else:
            invitation = None
        if invitation is None:
            return None
        # A targeted invitation can't be used by whoever else saw its code.
        if invitation.invited_phone and invitation.invited_phone != request.user.phone_number:
            return None
        return invitation

    def refusal(self, request, invitation):
        """Why this can't go ahead, or None if it can. A link token is far too
        long to guess, so its holder is told what happened, with 410 and no
        family details. Short codes always get 404, so they can't be probed."""
        if invitation is not None and invitation.is_open:
            return None
        if invitation is not None and request.data.get("token"):
            return Response({
                "status": "error",
                "errors": {"detail": "This invitation can't be used.", "state": invitation.state},
            }, status=status.HTTP_410_GONE)
        return error({"detail": "This invitation isn't valid."}, status.HTTP_404_NOT_FOUND)


class InvitationLookupAPI(_Respond):
    """POST keeps codes and tokens out of URLs and logs."""

    def post(self, request):
        invitation = self.find(request)
        refused = self.refusal(request, invitation)
        if refused:
            return refused
        return ok(serializers.InvitationPreviewSerializer(invitation, context={"request": request}).data)


class InvitationAcceptAPI(_Respond):
    @transaction.atomic
    def post(self, request):
        invitation = self.find(request, lock=True)
        refused = self.refusal(request, invitation)
        if refused:
            return refused
        family = invitation.family
        if FamilyMember.objects.filter(family=family, user=request.user).exists():
            return error({"non_field_errors": ["You're already in this family."]}, status.HTTP_409_CONFLICT)
        if FamilyMember.objects.filter(user=request.user).count() >= FamilyCircle.MAX_PER_USER:
            return error({"non_field_errors": [f"You can be in up to {FamilyCircle.MAX_PER_USER} family circles."]})
        if family.members.count() >= FamilyCircle.MAX_MEMBERS:
            return error({"non_field_errors": ["This family is full."]})
        member = FamilyMember.objects.create(
            family=family, user=request.user, kind=FamilyMember.Kind.INDEPENDENT_ADULT,
            relationship=invitation.relationship, language=family.language,
        )
        invitation.status = FamilyInvitation.Status.ACCEPTED
        invitation.responded_by = request.user
        invitation.responded_at = timezone.now()
        invitation.save(update_fields=["status", "responded_by", "responded_at"])
        audit(family, request.user, "invitation_accepted", member)
        return ok({"family_id": str(family.pk), "member_id": str(member.pk)})


class InvitationDeclineAPI(_Respond):
    @transaction.atomic
    def post(self, request):
        invitation = self.find(request, lock=True)
        refused = self.refusal(request, invitation)
        if refused:
            return refused
        invitation.status = FamilyInvitation.Status.DECLINED
        invitation.responded_by = request.user
        invitation.responded_at = timezone.now()
        invitation.save(update_fields=["status", "responded_by", "responded_at"])
        audit(invitation.family, request.user, "invitation_declined")
        return Response(status=status.HTTP_204_NO_CONTENT)


class MyInvitationsAPI(_Family):
    """In-app invitations waiting for this account's number."""

    def get(self, request):
        phone = request.user.phone_number
        if not phone:
            return ok([])
        invitations = FamilyInvitation.objects.filter(
            invited_phone=phone, status="pending", expires_at__gt=timezone.now(),
        ).select_related("family")
        return ok(serializers.InvitationPreviewSerializer(invitations, many=True, context={"request": request}).data)


