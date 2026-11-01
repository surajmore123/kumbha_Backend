"""
Who may do what, and what's safe for whom. Case access comes from
`apps.lostfound.policy` and family positions from `apps.familylocation.policy`;
neither is widened here. Anyone without access gets 404.
"""

from django.db.models import Q

from apps.family.models import FamilyMember
from apps.familylocation.models import LocationSession
from apps.lostfound import policy as case_policy
from apps.lostfound.models import ACTIVE_STATUSES, LostFoundCase
from apps.reunification.models import MeetingPoint

_CHILD_AGE_GROUPS = (FamilyMember.AgeGroup.UNDER_6, FamilyMember.AgeGroup.AGE_6_12, FamilyMember.AgeGroup.AGE_13_17)
ADULT_AGE = 18

Category = MeetingPoint.Category

# Staffed places, in the order that suits someone who can't look after
# themselves. Distance only decides between places of the same kind.
_SAFE_ORDER = (Category.LOST_FOUND, Category.HELP_DESK, Category.EMERGENCY, Category.POLICE)
_MEDICAL_ORDER = (Category.MEDICAL, Category.HOSPITAL)


def can_coordinate(user, case):
    return case_policy.is_family_side(user, case) or case_policy.can_operate(user, case)


def is_protected(case):
    """A child or vulnerable person: they go to staff, not across the crowd."""
    if case.is_vulnerable or case.is_child:
        return True
    if case.age_max is not None and case.age_max < ADULT_AGE:
        return True
    return case.member_id is not None and case.member.age_group in _CHILD_AGE_GROUPS


def safe_categories(case):
    medical = "medical" in (case.vulnerabilities or []) or case.found_category == case.FoundCategory.MEDICAL
    return (*_MEDICAL_ORDER, *_SAFE_ORDER) if medical else (*_SAFE_ORDER, *_MEDICAL_ORDER)


def is_safe_point(case, point):
    """For a protected person, only a verified, staffed place will do."""
    if not is_protected(case):
        return True
    return point.status == MeetingPoint.Status.VERIFIED and point.category in safe_categories(case)


def visible_points(user):
    """Public points, plus private ones from the person's own circles."""
    families = FamilyMember.objects.filter(user=user).values_list("family_id", flat=True)
    return MeetingPoint.objects.filter(
        Q(status__in=MeetingPoint.PUBLIC) | Q(status__in=MeetingPoint.PRIVATE, family_id__in=families),
    )


def can_edit_point(actor, point):
    return point.status in MeetingPoint.PRIVATE and point.family_id == actor.family_id and (
        point.created_by_id == actor.user_id or actor.role == FamilyMember.Role.ORGANIZER
    )


def self_protected(user, actor):
    """Whether this phone is with someone who shouldn't be sent to walk to
    family: a child's own account, a person with a protected open case, or a
    phone reporting a dependent who is missing."""
    if actor is None:
        return False
    if actor.is_dependent or actor.age_group in _CHILD_AGE_GROUPS:
        return True
    open_cases = LostFoundCase.objects.filter(status__in=ACTIVE_STATUSES, case_type="lost")
    if any(is_protected(c) for c in open_cases.filter(member=actor).select_related("member")):
        return True
    carried = LocationSession.objects.filter(
        started_by=user, status__in=LocationSession.OPEN, member__family_id=actor.family_id,
    ).exclude(member=actor).values_list("member_id", flat=True)
    return open_cases.filter(member_id__in=list(carried)).exists()


def open_protected_case(member):
    """An active case that makes this member someone to reach with care."""
    case = LostFoundCase.objects.filter(
        member=member, case_type="lost", status__in=ACTIVE_STATUSES,
    ).select_related("member").first()
    return case if case is not None and is_protected(case) else None


def family_side_cases(user):
    """Open cases this person may coordinate as family. Helpers use the
    operations routes, so this can't become a way to browse cases."""
    families = FamilyMember.objects.filter(user=user).values_list("family_id", flat=True)
    rows = LostFoundCase.objects.filter(
        Q(family_id__in=families) | Q(reporter=user), status__in=ACTIVE_STATUSES,
    ).select_related("member", "reunification_plan__meeting_point").distinct()
    return [case for case in rows if case_policy.is_family_side(user, case)]
