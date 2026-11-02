"""
Volunteer accounts and case assignment. Views and the admin both come through
here, so the rules are the same from either side.

Availability never grants anything: it only decides whether someone can take
new work.
"""

import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone

from apps.lostfound import policy as case_policy
from apps.lostfound.models import ACTIVE_STATUSES, CaseNote
from apps.lostfound.services import add_note, audit as case_audit
from apps.notifications import services as inbox
from apps.notifications.models import Notification
from apps.operations.models import CaseAssignment, OperationsAudit
from apps.safety.models import SafetyHelper

Status = CaseAssignment.Status
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
SETUP_CODE_LENGTH = 10

# Lock-screen safe: no names, places or case details.
_TEXT = {
    "assigned": {
        "en": ("New case assigned", "A case has been assigned to you. Open the app."),
        "hi": ("नया मामला सौंपा गया", "आपको एक मामला सौंपा गया है। ऐप खोलें।"),
        "mr": ("नवीन प्रकरण सोपवले", "तुम्हाला एक प्रकरण सोपवले आहे. ॲप उघडा."),
    },
    "removed": {
        "en": ("Assignment changed", "A case is no longer assigned to you."),
        "hi": ("कार्य बदला गया", "एक मामला अब आपको नहीं सौंपा गया है।"),
        "mr": ("जबाबदारी बदलली", "एक प्रकरण आता तुम्हाला सोपवलेले नाही."),
    },
    "escalated": {
        "en": ("Case escalated", "A case needs your review. Open the app."),
        "hi": ("मामला आगे बढ़ाया गया", "एक मामले की समीक्षा चाहिए। ऐप खोलें।"),
        "mr": ("प्रकरण पुढे पाठवले", "एका प्रकरणाचा आढावा हवा आहे. ॲप उघडा."),
    },
    "progress": {
        "en": ("Case update", "An assigned case has an update. Open the app."),
        "hi": ("मामले का अपडेट", "सौंपे गए मामले पर अपडेट है। ऐप खोलें।"),
        "mr": ("प्रकरणाचे अपडेट", "सोपवलेल्या प्रकरणावर अपडेट आहे. ॲप उघडा."),
    },
}


class OperationsError(Exception):
    def __init__(self, message, field="non_field_errors"):
        super().__init__(message)
        self.message = message
        self.field = field


def record(actor, target, action, **details):
    OperationsAudit.objects.create(actor=actor, target=target, action=action, details=details)


def _tell(user_id, event, case, key):
    language = inbox.languages([user_id]).get(user_id, "en")
    title, body = _TEXT[event][language]
    inbox.queue(
        user_id, Notification.Category.OPERATIONS, title=title, body=f"{body} {case.reference}",
        push_title=title, push_body=body,
        data={"type": "operations_case", "route": "/opsCase", "case_id": str(case.pk)},
        key=key, critical=True,
    )


# ---- accounts


def new_setup_code():
    return "".join(secrets.choice(_ALPHABET) for _ in range(SETUP_CODE_LENGTH))


def issue_setup_code(helper, by):
    """A fresh one-time code. It's returned once for an admin to pass on in
    person, stored only as a hash, and any password and session end with it."""
    code = new_setup_code()
    helper.setup_code_hash = make_password(code)
    helper.setup_expires_at = timezone.now() + timedelta(hours=settings.OPERATIONS_SETUP_CODE_HOURS)
    helper.save(update_fields=["setup_code_hash", "setup_expires_at"])
    user = helper.user
    user.set_unusable_password()
    user.tokens_valid_after = timezone.now()
    user.save(update_fields=["password", "tokens_valid_after"])
    record(by, user, "credential_reset")
    return code


def setup_is_valid(helper, code):
    return bool(
        helper.setup_code_hash and helper.setup_expires_at and helper.setup_expires_at > timezone.now()
        and check_password(code, helper.setup_code_hash)
    )


@transaction.atomic
def complete_setup(helper, password):
    user = helper.user
    user.set_password(password)
    user.tokens_valid_after = timezone.now()
    user.otp_verified = True
    user.save(update_fields=["password", "tokens_valid_after", "otp_verified"])
    helper.setup_code_hash = ""
    helper.setup_expires_at = None
    helper.credential_set_at = timezone.now()
    helper.save(update_fields=["setup_code_hash", "setup_expires_at", "credential_set_at"])
    record(user, user, "credential_set")


@transaction.atomic
def create_volunteer(*, phone_number, full_name, role, zones, by):
    """Never touches is_staff or is_superuser: a volunteer gets no Django Admin."""
    User = get_user_model()
    user, created = User.objects.get_or_create(
        phone_number=phone_number, defaults={"full_Name": full_name, "is_active": True},
    )
    if not created and (user.is_staff or user.is_superuser):
        raise OperationsError("This account is an administrator.", "phone_number")
    if SafetyHelper.objects.filter(user=user).exists():
        raise OperationsError("This person already has an operations account.", "phone_number")
    if not created and full_name and not user.full_Name:
        user.full_Name = full_name
        user.save(update_fields=["full_Name"])
    helper = SafetyHelper.objects.create(
        user=user, role=role, status=SafetyHelper.Status.PENDING, is_active=False, approved_by=by,
    )
    helper.zones.set(zones)
    record(by, user, "volunteer_created", role=role, zones=[str(z.pk) for z in zones])
    return helper, issue_setup_code(helper, by)


def set_status(helper, status, by):
    """Taking someone off signs them out at once. Their permissions were
    already checked live, so this ends the sessions as well."""
    previous = helper.status
    if previous == status:
        return helper
    helper.status = status
    helper.is_active = status == SafetyHelper.Status.ACTIVE
    helper.save(update_fields=["status", "is_active"])
    if status != SafetyHelper.Status.ACTIVE:
        sign_out_everywhere(helper.user)
        if status == SafetyHelper.Status.DEACTIVATED:
            helper.user.set_unusable_password()
            helper.user.save(update_fields=["password"])
        _release_cases(helper.user, by)
    record(by, helper.user, "status_changed", previous=previous, status=status)
    return helper


def sign_out_everywhere(user):
    user.tokens_valid_after = timezone.now()
    user.save(update_fields=["tokens_valid_after"])


def _release_cases(user, by):
    """Open work goes back to coordinators rather than sitting with someone
    who can no longer act on it."""
    for assignment in CaseAssignment.objects.filter(volunteer=user, status__in=CaseAssignment.OPEN):
        unassign(assignment.case, by, "Volunteer is no longer active")


# ---- assignment


def workload(user):
    return CaseAssignment.objects.filter(volunteer=user, status__in=CaseAssignment.OPEN).count()


def current_assignment(case):
    return CaseAssignment.objects.filter(case=case, status__in=CaseAssignment.OPEN).select_related("volunteer").first()


def check_assignment(case, volunteer):
    if case.status not in ACTIVE_STATUSES:
        raise OperationsError("This case is closed.")
    helper = SafetyHelper.current_for(volunteer)
    if helper is None:
        raise OperationsError("Choose an approved, active volunteer.", "volunteer_id")
    if helper.availability in (SafetyHelper.Availability.OFF_DUTY, SafetyHelper.Availability.UNAVAILABLE):
        raise OperationsError("This volunteer isn't available.", "volunteer_id")
    if case.zone_id and not helper.zones.filter(pk=case.zone_id).exists():
        raise OperationsError("This volunteer doesn't cover this case's zone.", "volunteer_id")


@transaction.atomic
def assign(case, volunteer, by, notes=""):
    check_assignment(case, volunteer)
    previous = CaseAssignment.objects.select_for_update().filter(case=case, status__in=CaseAssignment.OPEN).first()
    if previous:
        if previous.volunteer_id == volunteer.pk:
            raise OperationsError("This volunteer already has this case.", "volunteer_id")
        previous.status = Status.REASSIGNED
        previous.completed_at = timezone.now()
        previous.save(update_fields=["status", "completed_at", "updated_at"])
        _tell(previous.volunteer_id, "removed", case, f"ops:{previous.pk}:removed")
    assignment = CaseAssignment.objects.create(case=case, volunteer=volunteer, assigned_by=by, notes=notes[:500])
    case.assigned_to = volunteer
    case.save(update_fields=["assigned_to", "updated_at"])
    case_audit(case, by, "case_assigned", reassigned=previous is not None)
    _tell(volunteer.pk, "assigned", case, f"ops:{assignment.pk}:assigned")
    return assignment


@transaction.atomic
def unassign(case, by, reason=""):
    assignment = CaseAssignment.objects.select_for_update().filter(case=case, status__in=CaseAssignment.OPEN).first()
    if assignment is None:
        raise OperationsError("This case has no open assignment.")
    assignment.status = Status.REASSIGNED
    assignment.completed_at = timezone.now()
    if reason:
        assignment.notes = reason[:500]
    assignment.save(update_fields=["status", "completed_at", "notes", "updated_at"])
    case.assigned_to = None
    case.save(update_fields=["assigned_to", "updated_at"])
    case_audit(case, by, "case_unassigned")
    _tell(assignment.volunteer_id, "removed", case, f"ops:{assignment.pk}:removed")


_FLOW = {
    Status.ASSIGNED: {Status.ACCEPTED},
    Status.ACCEPTED: {Status.IN_PROGRESS, Status.COMPLETED},
    Status.IN_PROGRESS: {Status.COMPLETED},
    Status.ESCALATED: {Status.IN_PROGRESS, Status.COMPLETED},
}


@transaction.atomic
def progress(assignment, to, by):
    """The volunteer's own work status. The case's status stays with staff, so
    finishing a task can never mark anyone as found or reunited."""
    if to not in _FLOW.get(assignment.status, set()):
        raise OperationsError("This step isn't available now.", "status")
    assignment.status = to
    if to == Status.COMPLETED:
        assignment.completed_at = timezone.now()
        case = assignment.case
        case.assigned_to = None
        case.save(update_fields=["assigned_to", "updated_at"])
    assignment.save(update_fields=["status", "completed_at", "updated_at"])
    case_audit(assignment.case, by, "assignment_progress", status=to)
    for user_id in case_policy.staff_recipients(assignment.case.zone_id):
        if to == Status.COMPLETED and user_id != by.pk:
            _tell(user_id, "progress", assignment.case, f"ops:{assignment.pk}:{to}:{user_id}")
    return assignment


@transaction.atomic
def escalate(case, by, reason):
    """Hands a decision up. It tells coordinators, and changes no case status."""
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise OperationsError("Say why this needs escalating.", "reason")
    assignment = CaseAssignment.objects.select_for_update().filter(case=case, status__in=CaseAssignment.OPEN).first()
    if assignment is None:
        assignment = CaseAssignment.objects.create(case=case, volunteer=by, assigned_by=by, status=Status.ESCALATED)
    assignment.status = Status.ESCALATED
    assignment.escalation_reason = reason[:500]
    assignment.save(update_fields=["status", "escalation_reason", "updated_at"])
    add_note(case, by, CaseNote.Kind.INTERNAL, f"Escalated: {reason}")
    case_audit(case, by, "case_escalated")
    for user_id in case_policy.staff_recipients(case.zone_id):
        if user_id != by.pk:
            _tell(user_id, "escalated", case, f"ops:{assignment.pk}:esc:{assignment.updated_at.timestamp()}:{user_id}")
    return assignment
