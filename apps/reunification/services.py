"""
Everything that changes a meeting point or a plan. A plan records what people
did and never touches a case's status. A reunion is only ever recorded by
`apps.lostfound.services.record_reunion`, after a human check.
"""

import logging

from django.db import transaction
from django.utils import timezone

from apps.aiChat.services.geo import distance_km
from apps.family.models import FamilyMember
from apps.family.views import audit as family_audit
from apps.lostfound import notifications
from apps.lostfound.models import ACTIVE_STATUSES
from apps.lostfound.services import audit as case_audit
from apps.reunification import policy
from apps.reunification.models import MeetingPoint, ReunificationPlan
from utils.push_notifications import send_localized

logger = logging.getLogger(__name__)

_TITLE = {"en": "Family meeting", "hi": "परिवार से मिलना", "mr": "कुटुंब भेट"}
_BODY = {
    "check_map": {
        "en": "A family member asked you to check the reunification map.",
        "hi": "परिवार के एक सदस्य ने आपसे पुनर्मिलन मानचित्र देखने को कहा है।",
        "mr": "कुटुंबातील एका सदस्याने तुम्हाला पुनर्भेट नकाशा पाहण्यास सांगितले आहे.",
    },
    "meet_at_point": {
        "en": "A family member shared a place to meet. Open the app to see it.",
        "hi": "परिवार के एक सदस्य ने मिलने की जगह साझा की है। देखने के लिए ऐप खोलें।",
        "mr": "कुटुंबातील एका सदस्याने भेटण्याची जागा शेअर केली आहे. पाहण्यासाठी अॅप उघडा.",
    },
}


class ReunionError(Exception):
    def __init__(self, message, field="non_field_errors", code=None):
        super().__init__(message)
        self.message = message
        self.field = field
        self.code = code


def plan_for(case):
    return ReunificationPlan.objects.filter(case=case).select_related("meeting_point").first()


def stage_of(case, plan):
    """Where the workflow stands. Worked out from the case first, because the
    case's human checks are what count."""
    if case.status in ("REUNITED", "CLOSED"):
        return "reunited" if case.status == "REUNITED" else "closed"
    if case.status == "REJECTED":
        return "closed"
    if case.status in ("VERIFICATION_REQUIRED", "MATCH_CONFIRMED"):
        return "verifying"
    if plan and (plan.family_arrived_at or plan.person_arrived_at):
        return "at_point"
    if plan and plan.meeting_point_id:
        return "point_chosen"
    return "reported"


def _require_open(case):
    if case.status not in ACTIVE_STATUSES:
        raise ReunionError("This case is no longer open.")


@transaction.atomic
def choose_point(case, point, by):
    _require_open(case)
    if not policy.is_safe_point(case, point):
        raise ReunionError(
            "This person needs a verified, staffed help point.", "meeting_point_id", "use_safe_point",
        )
    plan, _ = ReunificationPlan.objects.select_for_update().get_or_create(case=case)
    plan.meeting_point = point
    plan.selected_by = by
    plan.selected_at = timezone.now()
    plan.family_arrived_at = None
    plan.person_arrived_at = None
    plan.save()
    case_audit(case, by, "meeting_point_selected", status=point.status)
    key = f"meeting:{plan.pk}:{plan.selected_at.timestamp()}"
    notifications.notify_family(case, "meeting_point", key)
    notifications.notify_staff(case, "staff_update", key)
    return plan


@transaction.atomic
def mark_arrived(case, by, who):
    """A note that people have reached the place. Being there, or two phones
    being close together, proves nothing about who anyone is."""
    _require_open(case)
    plan = ReunificationPlan.objects.select_for_update().filter(case=case).first()
    if plan is None or plan.meeting_point_id is None:
        raise ReunionError("Choose a meeting point first.")
    if who == "family":
        plan.family_arrived_at = timezone.now()
    else:
        plan.person_arrived_at = timezone.now()
    plan.save()
    case_audit(case, by, f"{who}_arrived")
    if who == "family":
        notifications.notify_staff(case, "staff_update", f"arrived:{plan.pk}:{who}")
    else:
        notifications.notify_family(case, "meeting_point", f"arrived:{plan.pk}:{who}")
    return plan


def recommended(case, origin=None, limit=5):
    """Places to go, safest kind first. For a protected person that's verified
    staffed points only, however far away, and a nearer family spot never wins."""
    categories = policy.safe_categories(case)
    rows = list(MeetingPoint.objects.filter(status=MeetingPoint.Status.VERIFIED, category__in=categories))
    place = origin
    if place is None and case.latitude is not None:
        place = (case.latitude, case.longitude)

    def km(point):
        return distance_km(place[0], place[1], point.latitude, point.longitude) if place else None

    ranked = sorted(rows, key=lambda p: (categories.index(p.category), km(p) or 0, p.name))
    return [(point, km(point)) for point in ranked[:limit]]


@transaction.atomic
def create_family_point(actor, data):
    point = MeetingPoint.objects.create(
        family=actor.family, created_by=actor.user, status=MeetingPoint.Status.FAMILY,
        category=MeetingPoint.Category.FAMILY_MEETING, source_type=MeetingPoint.Source.COMMUNITY, **data,
    )
    family_audit(actor.family, actor.user, "meeting_point_added")
    return point


def suggest_point(actor, point):
    """Offers a private point to staff. It stays private until they decide."""
    point.status = MeetingPoint.Status.SUGGESTED
    point.save(update_fields=["status", "updated_at"])
    family_audit(actor.family, actor.user, "meeting_point_suggested")
    return point


def review_point(point, by, decision, *, source_type=None, source_detail=""):
    """Staff only, through the admin. `verified` needs a named source."""
    if decision == MeetingPoint.Status.VERIFIED:
        if not (source_detail or point.source_detail).strip():
            raise ReunionError("Say where this was confirmed.", "source_detail")
        point.source_type = source_type or MeetingPoint.Source.FIELD_CHECK
        point.source_detail = (source_detail or point.source_detail).strip()
        point.verified_by = by
        point.verified_at = timezone.now()
    else:
        point.verified_by = None
        point.verified_at = None
    if decision in MeetingPoint.PUBLIC:
        point.family = None
    point.status = decision
    point.save()
    return point


def notify_family(actor, kind, point=None):
    """A nudge to the rest of the family. It holds no place or name: the app
    opens the point by its id, and the server checks access then."""
    users = list(
        FamilyMember.objects.filter(family=actor.family, user__isnull=False)
        .exclude(pk=actor.pk).values_list("user_id", flat=True)
    )
    family_audit(actor.family, actor.user, f"reunion_{kind}", people=len(users))
    if not users:
        return 0

    def build(language):
        return _TITLE[language], _BODY[kind][language]

    try:
        send_localized(
            "reunification", build, users=users, inbox={"category": "reunification"},
            data={
                "type": "family_reunion", "route": "/reunionMap", "family_id": str(actor.family_id),
                **({"point_id": str(point.pk)} if point else {}),
            },
        )
    except Exception as exc:
        logger.warning("Reunion notice failed (%s).", type(exc).__name__)
    return len(users)
