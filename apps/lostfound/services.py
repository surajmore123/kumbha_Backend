"""
Everything that changes a case. Views only check who's asking and what they sent.

Two rules are enforced here so that no route can get around them: only a person
can confirm a match, and nobody can be recorded as reunited without a confirmed
match and a recorded in-person check.
"""

import io
import logging

from django.db import IntegrityError, transaction
from django.utils import timezone
from PIL import Image, UnidentifiedImageError

from apps.lostfound import matching, notifications
from apps.lostfound.models import (
    ACTIVE_STATUSES,
    CaseAttachment,
    CaseAudit,
    CaseMatch,
    CaseNote,
    CaseSighting,
    CaseStatusHistory,
    LostFoundCase,
    Status,
)
from apps.safety.zones import zone_for
from apps.website.images import sniff

logger = logging.getLogger(__name__)

MAX_PIXELS = 40_000_000
_MAX_SIDE = 1600

TRANSITIONS = {
    Status.SUBMITTED: {
        Status.UNDER_REVIEW, Status.VERIFICATION_REQUIRED, Status.POTENTIAL_MATCH_FOUND,
        Status.REJECTED, Status.CLOSED,
    },
    Status.UNDER_REVIEW: {
        Status.VERIFICATION_REQUIRED, Status.POTENTIAL_MATCH_FOUND, Status.REJECTED, Status.CLOSED,
    },
    Status.VERIFICATION_REQUIRED: {
        Status.UNDER_REVIEW, Status.POTENTIAL_MATCH_FOUND, Status.MATCH_CONFIRMED, Status.REJECTED, Status.CLOSED,
    },
    Status.POTENTIAL_MATCH_FOUND: {
        Status.UNDER_REVIEW, Status.VERIFICATION_REQUIRED, Status.MATCH_CONFIRMED, Status.CLOSED,
    },
    Status.MATCH_CONFIRMED: {Status.UNDER_REVIEW, Status.REUNITED},
    Status.REUNITED: {Status.CLOSED},
    Status.CLOSED: {Status.UNDER_REVIEW},
    Status.REJECTED: {Status.UNDER_REVIEW},
}
# Reachable only through confirm_match, verify_case and record_reunion, which
# demand a recorded check.
_GUARDED = {Status.MATCH_CONFIRMED, Status.REUNITED}


class CaseError(Exception):
    """A request that's understood but not allowed in the case's current state."""

    def __init__(self, message, field="non_field_errors"):
        super().__init__(message)
        self.message = message
        self.field = field


def audit(case, actor, action, **details):
    CaseAudit.objects.create(case=case, actor=actor, action=action, details=details)


def _set_status(case, to, by, reason=""):
    previous = case.status
    case.status = to
    case.save(update_fields=["status", "updated_at"])
    CaseStatusHistory.objects.create(
        case=case, from_status=previous, to_status=to, updated_by=by, reason=reason[:500],
    )


def _after_create(case):
    """Runs after commit: a failed suggestion must not lose a report."""
    try:
        matching.find_matches(case)
    except Exception as exc:
        logger.warning("Matching failed (%s).", type(exc).__name__)


@transaction.atomic
def create_case(*, reporter, reporter_role, case_type, data, member=None, family=None, alert=None, client_id=None):
    """Returns (case, created). A repeated client_id or an active case for the
    same person returns the existing case."""
    if client_id:
        existing = LostFoundCase.objects.filter(reporter=reporter, client_id=client_id).first()
        if existing:
            return existing, False
    if member is not None:
        existing = LostFoundCase.objects.filter(
            member=member, case_type=case_type, status__in=ACTIVE_STATUSES,
        ).first()
        if existing:
            return existing, False
    try:
        with transaction.atomic():
            case = LostFoundCase.objects.create(
                reporter=reporter, reporter_role=reporter_role, case_type=case_type, client_id=client_id,
                member=member, family=family, alert=alert,
                zone=zone_for(data.get("latitude"), data.get("longitude")), **data,
            )
    except IntegrityError:
        existing = LostFoundCase.objects.filter(reporter=reporter, client_id=client_id).first() if client_id else None
        existing = existing or LostFoundCase.objects.filter(
            member=member, case_type=case_type, status__in=ACTIVE_STATUSES,
        ).first()
        if existing is None:
            raise
        return existing, False
    CaseStatusHistory.objects.create(case=case, to_status=Status.SUBMITTED, updated_by=reporter)
    audit(case, reporter, "case_created", case_type=case_type, reporter_role=reporter_role)
    notifications.notify_family(case, "submitted")
    notifications.notify_staff(case, "staff_new")
    transaction.on_commit(lambda: _after_create(case))
    return case, True


@transaction.atomic
def change_status(case, to, by, reason):
    case = LostFoundCase.objects.select_for_update().get(pk=case.pk)
    if to in _GUARDED:
        raise CaseError("This needs a recorded in-person check.", "status")
    if to not in TRANSITIONS.get(case.status, set()):
        raise CaseError("A case can't move to that status from here.", "status")
    if not reason.strip():
        raise CaseError("Give a reason.", "reason")
    was_new = case.status == Status.SUBMITTED
    _set_status(case, to, by, reason)
    audit(case, by, "status_changed", to=to)
    if was_new and to == Status.UNDER_REVIEW:
        notifications.notify_family(case, "reviewed")
    if to == Status.VERIFICATION_REQUIRED:
        notifications.notify_family(case, "info_needed", f"info_needed:{case.status_history.count()}")
    return case


@transaction.atomic
def add_note(case, by, kind, body):
    note = CaseNote.objects.create(case=case, author=by, kind=kind, body=body)
    audit(case, by, "note_added", kind=kind)
    if kind == CaseNote.Kind.FAMILY_UPDATE:
        notifications.notify_family(case, "sighting", f"note:{note.pk}")
    elif kind == CaseNote.Kind.INFO_REQUEST:
        notifications.notify_family(case, "info_needed", f"note:{note.pk}")
    elif kind in (CaseNote.Kind.FAMILY_INFO, CaseNote.Kind.CORRECTION):
        notifications.notify_staff(case, "staff_update", f"note:{note.pk}")
    return note


@transaction.atomic
def add_sighting(case, by, role, data):
    sighting = CaseSighting.objects.create(case=case, reported_by=by, reporter_role=role, **data)
    audit(case, by, "sighting_added", reporter_role=role)
    notifications.notify_staff(case, "staff_update", f"sighting:{sighting.pk}")
    return sighting


@transaction.atomic
def review_sighting(sighting, by, *, approve, verified=False):
    sighting.review = CaseSighting.Review.APPROVED if approve else CaseSighting.Review.REJECTED
    sighting.verified = approve and verified
    sighting.reviewed_by = by
    sighting.reviewed_at = timezone.now()
    sighting.save(update_fields=["review", "verified", "reviewed_by", "reviewed_at"])
    audit(sighting.case, by, "sighting_reviewed", approved=approve, verified=sighting.verified)
    if approve:
        notifications.notify_family(sighting.case, "sighting", f"sighting:{sighting.pk}")
    return sighting


@transaction.atomic
def cancel_report(case, by, reason):
    case = LostFoundCase.objects.select_for_update().get(pk=case.pk)
    if not case.is_active or case.status == Status.MATCH_CONFIRMED:
        raise CaseError("This report can't be cancelled now. Please contact a help desk.")
    _set_status(case, Status.CLOSED, by, reason or "Cancelled by the reporter")
    audit(case, by, "report_cancelled")
    notifications.notify_staff(case, "staff_update", "cancelled")
    return case


@transaction.atomic
def family_confirm_reunion(case, by):
    """Records what the family says. It doesn't close anything: staff decide
    that after checking, which is why this isn't the same as REUNITED."""
    case = LostFoundCase.objects.select_for_update().get(pk=case.pk)
    if not case.is_active:
        raise CaseError("This case is no longer open.")
    case.family_confirmed_at = timezone.now()
    case.save(update_fields=["family_confirmed_at", "updated_at"])
    audit(case, by, "family_confirmed_reunion")
    notifications.notify_staff(case, "staff_update", "family_confirmed")
    return case


def _lock_pair(match):
    ids = [match.lost_case_id, match.found_case_id]
    cases = {c.pk: c for c in LostFoundCase.objects.select_for_update().filter(pk__in=ids)}
    return cases[match.lost_case_id], cases[match.found_case_id]


@transaction.atomic
def approve_match(match, by, *, notify_family):
    """Staff think this is worth checking in person."""
    if match.state != CaseMatch.State.SUGGESTED:
        raise CaseError("This match has already been reviewed.")
    lost, found = _lock_pair(match)
    for case in (lost, found):
        if Status.POTENTIAL_MATCH_FOUND in TRANSITIONS.get(case.status, set()):
            _set_status(case, Status.POTENTIAL_MATCH_FOUND, by, "Possible match being checked")
    match.state = CaseMatch.State.APPROVED
    match.reviewed_by = by
    match.reviewed_at = timezone.now()
    match.save(update_fields=["state", "reviewed_by", "reviewed_at"])
    audit(lost, by, "match_approved", match=str(match.pk), notify_family=notify_family)
    if notify_family:
        notifications.notify_family(lost, "match", f"match:{match.pk}")
    return match


@transaction.atomic
def dismiss_match(match, by, reason):
    if match.state == CaseMatch.State.CONFIRMED:
        raise CaseError("A confirmed match can't be dismissed.")
    lost, found = _lock_pair(match)
    match.state = CaseMatch.State.DISMISSED
    match.reviewed_by = by
    match.reviewed_at = timezone.now()
    match.save(update_fields=["state", "reviewed_by", "reviewed_at"])
    audit(lost, by, "match_dismissed", match=str(match.pk))
    for case in (lost, found):
        still_open = case.matches_as_lost.filter(state="approved").exists() or (
            case.matches_as_found.filter(state="approved").exists()
        )
        if case.status == Status.POTENTIAL_MATCH_FOUND and not still_open:
            _set_status(case, Status.UNDER_REVIEW, by, reason or "Match dismissed")
    return match


def _record_check(case, by, method, remarks):
    if not remarks or len(remarks.strip()) < 10:
        raise CaseError("Describe the check that was made.", "remarks")
    return CaseNote.objects.create(
        case=case, author=by, kind=CaseNote.Kind.VERIFICATION, body=f"{method}: {remarks.strip()}",
    )


@transaction.atomic
def confirm_match(match, by, *, method, remarks):
    """A person has checked this. The score plays no part here."""
    if match.state != CaseMatch.State.APPROVED:
        raise CaseError("Approve the match for checking first.")
    lost, found = _lock_pair(match)
    for case in (lost, found):
        if Status.MATCH_CONFIRMED not in TRANSITIONS.get(case.status, set()):
            raise CaseError("Both cases must be open for this.")
    for case in (lost, found):
        _record_check(case, by, method, remarks)
        _set_status(case, Status.MATCH_CONFIRMED, by, "Confirmed in person by staff")
        audit(case, by, "match_confirmed", match=str(match.pk), method=method)
    match.state = CaseMatch.State.CONFIRMED
    match.reviewed_by = by
    match.reviewed_at = timezone.now()
    match.save(update_fields=["state", "reviewed_by", "reviewed_at"])
    notifications.notify_family(lost, "confirmed", f"match:{match.pk}:confirmed")
    if found.family_id:
        notifications.notify_family(found, "confirmed", f"match:{match.pk}:confirmed")
    return match


@transaction.atomic
def verify_case(case, by, *, method, remarks):
    """For someone already linked to a family, for example by a QR, with no
    separate lost report to match against."""
    case = LostFoundCase.objects.select_for_update().get(pk=case.pk)
    if case.family_id is None:
        raise CaseError("Only a case linked to a family can be verified this way.")
    if Status.MATCH_CONFIRMED not in TRANSITIONS.get(case.status, set()):
        raise CaseError("Move the case to verification first.", "status")
    _record_check(case, by, method, remarks)
    _set_status(case, Status.MATCH_CONFIRMED, by, "Confirmed in person by staff")
    audit(case, by, "case_verified", method=method)
    notifications.notify_family(case, "confirmed", f"verified:{case.status_history.count()}")
    return case


@transaction.atomic
def record_reunion(case, by, *, method, remarks, identity_checked, person_recognised):
    """The handover itself. Needs a confirmed match and a recorded human check."""
    case = LostFoundCase.objects.select_for_update().get(pk=case.pk)
    if case.status != Status.MATCH_CONFIRMED:
        raise CaseError("Only a confirmed match can be recorded as reunited.", "status")
    if not identity_checked:
        raise CaseError("Check the guardian's identity in person first.", "identity_checked")
    if case.is_vulnerable and not person_recognised:
        raise CaseError("Confirm the person recognised and is willing to go with them.", "person_recognised")
    _record_check(case, by, method, remarks)
    now = timezone.now()
    linked = [
        m.found_case for m in case.matches_as_lost.filter(state="confirmed").select_related("found_case")
    ] + [m.lost_case for m in case.matches_as_found.filter(state="confirmed").select_related("lost_case")]
    for item in [case, *linked]:
        if item.status != Status.MATCH_CONFIRMED:
            continue
        _set_status(item, Status.REUNITED, by, "Handover checked in person")
        item.reunited_at = now
        item.reunited_by = by
        item.save(update_fields=["reunited_at", "reunited_by", "updated_at"])
        audit(item, by, "reunion_recorded", method=method)
        notifications.notify_family(item, "reunited")
    return case


def clean_image(raw):
    """Re-encoded rather than stored as sent, which drops hidden GPS and camera
    data and anything else hiding in the file. Returns JPEG bytes."""
    if sniff(raw) not in ("jpg", "png", "webp"):
        raise CaseError("Use a JPG, PNG or WebP photo.", "photo")
    try:
        image = Image.open(io.BytesIO(raw))
        if image.width * image.height > MAX_PIXELS:
            raise CaseError("This photo is too large.", "photo")
        image = image.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise CaseError("This photo can't be read.", "photo") from exc
    image.thumbnail((_MAX_SIDE, _MAX_SIDE))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=85)
    return out.getvalue()


@transaction.atomic
def add_attachment(case, by, raw, client_id=None):
    if client_id:
        existing = case.attachments.filter(client_id=client_id).first()
        if existing:
            return existing
    if case.attachments.count() >= CaseAttachment.MAX_PER_CASE:
        raise CaseError(f"A case can have up to {CaseAttachment.MAX_PER_CASE} photos.", "photo")
    attachment = CaseAttachment.objects.create(
        case=case, uploaded_by=by, client_id=client_id, content_type="image/jpeg", data=clean_image(raw),
    )
    audit(case, by, "attachment_added")
    return attachment


def _alert_data(alert):
    member = alert.member
    vulnerable = {
        "dependent_child": ["child"],
        "dependent_elderly": ["elderly"],
        "dependent_other": ["other"],
    }.get(member.kind, [])
    if alert.kind == "medical":
        vulnerable = [*vulnerable, "medical"]
    return {
        "person_name": member.display_name.split()[0] if member.display_name else "",
        "vulnerabilities": vulnerable,
        "found_category": {"separated": "separated", "medical": "medical"}.get(alert.kind, "other"),
        "assistance_needed": alert.note,
        "safe_facility": alert.note,
        "event_at": alert.created_at,
        "location_text": alert.note or "Reported by a registered helper",
        "latitude": alert.latitude,
        "longitude": alert.longitude,
    }


@transaction.atomic
def case_from_alert(alert):
    """A helper has confirmed something for a scanned QR. Reuses or opens a
    found case, so repeated scans can't pile up. The family was told through
    the safety alert, so this adds no second notice. A QR is not proof of
    identity, so a lost report is linked by a suggestion, never confirmed."""
    data = _alert_data(alert)
    case, created = create_case(
        reporter=alert.helper, reporter_role=alert.helper_role, case_type=LostFoundCase.Type.FOUND,
        data=data, member=alert.member, family=alert.family, alert=alert,
    )
    if not created:
        add_sighting(case, alert.helper, alert.helper_role, {
            "description": f"Safety QR scanned again: {alert.kind}",
            "location_text": data["location_text"],
            "latitude": alert.latitude, "longitude": alert.longitude, "seen_at": alert.created_at,
        })
    lost = LostFoundCase.objects.filter(
        member=alert.member, case_type=LostFoundCase.Type.LOST, status__in=ACTIVE_STATUSES,
    ).first()
    if lost:
        CaseMatch.objects.get_or_create(lost_case=lost, found_case=case, defaults={
            "score": 90,
            "reasons": [{
                "attribute": "qr", "points": 90, "out_of": 100,
                "detail": "their Safety QR was scanned. A card doesn't prove who is holding it",
            }],
        })
        notifications.notify_staff(lost, "staff_update", f"qr:{case.pk}")
    return case
