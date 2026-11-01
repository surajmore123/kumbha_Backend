"""
Who may reach an SOS. Anyone else gets 404, so references can't be probed.

- The person who sent it.
- Family told about it, for as long as they're still in that family.
- Safety staff, and a help desk it's assigned to, through the operations routes.

Volunteers get nothing here, and being family gives no operational power.
"""

from apps.emergency.models import EmergencyRecipient
from apps.family.models import FamilyMember
from apps.lostfound.policy import HELP_DESK, STAFF, helper_role
from apps.lostfound.policy import can_operate as _case_can_operate
from apps.lostfound.policy import ops_scope as _case_scope
from apps.safety import policy as safety_policy
from apps.safety.models import SafetyHelper


def is_operator(user):
    return helper_role(user) in (STAFF, HELP_DESK)


def can_operate(user, sos):
    return _case_can_operate(user, sos)


def ops_scope(user, rows):
    return _case_scope(user, rows)


def is_assignable(user):
    helper = SafetyHelper.current_for(user)
    return helper is not None and helper.role in (STAFF, HELP_DESK)


def recipient_row(user, sos):
    return EmergencyRecipient.objects.filter(sos=sos, member__user=user).select_related("member").first()


def role_for(user, sos):
    """owner, family, ops, or None."""
    if sos.user_id == user.pk:
        return "owner"
    if can_operate(user, sos):
        return "ops"
    return "family" if recipient_row(user, sos) else None


def can_see_location(role, sos):
    """Activating SOS shares the position with these people for that emergency
    only, so family lose it the moment the emergency ends."""
    return role in ("owner", "ops") or (role == "family" and sos.is_active)


def family_members_to_tell(user):
    """Everyone the existing safety rule would tell, across the person's circles."""
    rows = []
    for membership in FamilyMember.objects.filter(user=user).select_related("family"):
        users = safety_policy.recipients_for(membership)
        rows += FamilyMember.objects.filter(family=membership.family, user_id__in=users).select_related("user")
    return rows
