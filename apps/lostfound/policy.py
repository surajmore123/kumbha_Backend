"""
Who may reach a case. Every view goes through here, and anyone without access
gets 404, so references can't be probed.

- Reporter: their own report.
- Family: a case linked to their circle, by the same rule as safety alerts.
- Volunteers and help desks: reports they made, plus cases assigned to a help desk.
- Safety staff: everything, through the operations routes only.
"""

from django.db.models import Q

from apps.family.models import FamilyMember
from apps.safety import policy as safety_policy
from apps.safety.models import SafetyHelper

STAFF = SafetyHelper.Role.SAFETY_STAFF
HELP_DESK = SafetyHelper.Role.HELP_DESK


def helper_role(user):
    """The live role. A Django superuser is the ADMIN role: all zones."""
    helper = SafetyHelper.current_for(user)
    if helper:
        return helper.role
    return STAFF if user.is_superuser else None


def is_staff(user):
    return helper_role(user) == STAFF


def can_operate(user, case):
    """Working a case: all of them for staff, assigned ones for a help desk."""
    role = helper_role(user)
    if role == STAFF:
        return user.is_superuser or case.zone_id is None or case.zone_id in safety_policy.zone_ids(user)
    if role == HELP_DESK:
        return case.assigned_to_id == user.pk or case.zone_id in safety_policy.zone_ids(user)
    return False


def ops_scope(user, rows):
    """The same rule as `can_operate`, for a list."""
    role = helper_role(user)
    if user.is_superuser:
        return rows
    zones = safety_policy.zone_ids(user)
    if role == STAFF:
        return rows.filter(Q(zone__isnull=True) | Q(zone_id__in=zones))
    if role == HELP_DESK:
        return rows.filter(Q(assigned_to=user) | Q(zone_id__in=zones))
    return rows.none()


def is_assigned_volunteer(user, case):
    return case.assigned_to_id == user.pk and helper_role(user) is not None


def family_actor(user, case):
    """The user's membership, if the case's family gives them access."""
    if case.family_id is None or case.member_id is None:
        return None
    actor = FamilyMember.objects.filter(family_id=case.family_id, user=user).first()
    if actor is None:
        return None
    return actor if safety_policy.can_review_alert(actor, case.member) else None


def is_family_side(user, case):
    """A helper who filed a found report isn't family, even though they
    reported it, so they don't get the family's view of it."""
    own_report = case.reporter_id == user.pk and case.reporter_role == "pilgrim"
    return own_report or family_actor(user, case) is not None


def can_view(user, case):
    return (
        case.reporter_id == user.pk or is_family_side(user, case) or can_operate(user, case)
        or is_assigned_volunteer(user, case)
    )


def can_see_location(user, case):
    """A child's or vulnerable person's found location stays with those
    responsible. An adult's family needs that adult's consent."""
    if can_operate(user, case) or case.reporter_id == user.pk:
        return True
    actor = family_actor(user, case)
    return actor is not None and safety_policy.can_see_alert_location(actor, case.member)


def family_recipients(case):
    """User ids told about a case: the reporter, and the family who may see it."""
    users = {case.reporter_id} if case.reporter_id and case.reporter_role == "pilgrim" else set()
    if case.member_id:
        users.update(safety_policy.recipients_for(case.member))
    return [u for u in users if u]


def staff_recipients(zone_id=None):
    """Coordinators to tell: those in the zone, or everyone if nobody covers it,
    so no alert goes unseen."""
    helpers = [h for h in SafetyHelper.objects.filter(role=STAFF, is_active=True) if h.is_current]
    if zone_id:
        local = [h for h in helpers if h.zones.filter(pk=zone_id).exists()]
        helpers = local or helpers
    return [h.user_id for h in helpers]
