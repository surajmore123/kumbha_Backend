"""
Who can do what. Being organizer gives no access to an adult's location, and
nothing here looks at whether someone has been reported missing.
"""

from apps.family import policy as family_policy
from apps.family.models import FamilyMember


def can_start_for(actor, member):
    """Adults start their own, and nobody else can. A dependent's is started
    by someone who manages them."""
    if member.is_dependent:
        return family_policy.manages_dependent(actor, member)
    return actor.pk == member.pk


def can_manage(actor, session):
    return can_start_for(actor, session.member)


def eligible_viewers(member):
    """Who could be chosen. A dependent's location only ever goes to the people
    responsible for them, however the list is changed."""
    adults = FamilyMember.objects.filter(family_id=member.family_id, user__isnull=False).exclude(pk=member.pk)
    if member.is_dependent:
        guardians = member.guardian_links.values_list("guardian_id", flat=True)
        adults = adults.filter(pk__in=guardians) | adults.filter(role=FamilyMember.Role.ORGANIZER)
    return adults.select_related("user").distinct()


def can_view(actor, session):
    """Chosen, not revoked, and still eligible, checked on every request."""
    if actor.pk == session.member_id:
        return True
    grant = session.recipients.filter(member=actor, revoked_at__isnull=True).exists()
    return grant and eligible_viewers(session.member).filter(pk=actor.pk).exists()
