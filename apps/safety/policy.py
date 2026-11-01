"""Who sees safety alerts. QR access itself is in `apps.family.policy`."""

from apps.safety.models import SafetyHelper
from apps.family import policy as family_policy
from apps.family.models import FamilyMember


def can_review_alert(actor, member):
    """A dependent's alerts go to those who manage them. An adult's go to the
    circle they chose to join, and to the adult."""
    if member.is_dependent:
        return family_policy.manages_dependent(actor, member)
    return actor.family_id == member.family_id


def can_see_alert_location(actor, member):
    """A dependent's guardians always see it. An adult's family only does if
    the adult agreed to that, so a scan can't reveal them without consent."""
    return member.is_dependent or actor.pk == member.pk or member.location_sharing_consent


def recipients_for(member):
    """User ids to notify. An adult isn't told about themselves."""
    adults = FamilyMember.objects.filter(family_id=member.family_id, user__isnull=False).exclude(pk=member.pk)
    if member.is_dependent:
        guardians = member.guardian_links.values_list("guardian_id", flat=True)
        adults = adults.filter(pk__in=guardians) | adults.filter(role=FamilyMember.Role.ORGANIZER)
    return list(adults.values_list("user_id", flat=True).distinct())


def zone_ids(user):
    """The zones this person currently works in. Live, like every other check."""
    helper = SafetyHelper.current_for(user)
    return set(helper.zones.values_list("pk", flat=True)) if helper else set()
