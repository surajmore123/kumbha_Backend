"""
Who may do what. Every rule is here, and every view goes through it.

`actor` is the requesting user's own FamilyMember in the circle. A request from
someone outside a circle never gets this far: the circle answers 404.

Being organizer gives no access to another adult's private details. Those stay
with the adult, who chooses what to share.
"""

from apps.family.models import FamilyMember


def is_organizer(actor):
    return actor.role == FamilyMember.Role.ORGANIZER


def is_guardian_of(actor, member):
    return member.is_dependent and member.guardian_links.filter(guardian=actor).exists()


def manages_dependent(actor, member):
    """The organizer manages every dependent; guardians manage their own."""
    return member.is_dependent and (is_organizer(actor) or is_guardian_of(actor, member))


def can_manage_family(actor):
    return is_organizer(actor)


def can_edit_profile(actor, member):
    """Adults edit themselves. Dependents are edited by whoever manages them."""
    if member.is_dependent:
        return manages_dependent(actor, member)
    return actor.pk == member.pk


def can_edit_relationship(actor, member):
    return is_organizer(actor) or can_edit_profile(actor, member)


def can_see_phone(actor, member):
    if actor.pk == member.pk:
        return True
    if member.is_dependent:
        return manages_dependent(actor, member)
    return member.share_phone


def can_see_birth_details(actor, member):
    return actor.pk == member.pk or manages_dependent(actor, member)


def can_remove(actor, member):
    """Removal is the organizer's, and never of themselves: that's leaving."""
    return is_organizer(actor) and actor.pk != member.pk


def can_manage_guardians(actor, member):
    return is_organizer(actor) and member.is_dependent


def can_view_contacts(actor, member):
    if actor.pk == member.pk:
        return True
    if member.is_dependent:
        return manages_dependent(actor, member)
    return is_organizer(actor) and member.share_contacts_with_organizer


def can_edit_contacts(actor, member):
    """Sharing an adult's contacts lets the organizer read them, not change them."""
    if member.is_dependent:
        return manages_dependent(actor, member)
    return actor.pk == member.pk


def can_view_qr(actor, member):
    """An adult's Safety QR is theirs alone. Being organizer gives no access."""
    return actor.pk == member.pk or manages_dependent(actor, member)


def can_edit_family_contacts(actor):
    return is_organizer(actor)


def permissions_for(actor, member):
    """What the app may offer. The API still checks each action."""
    return {
        "edit_profile": can_edit_profile(actor, member),
        "edit_relationship": can_edit_relationship(actor, member),
        "remove": can_remove(actor, member),
        "manage_guardians": can_manage_guardians(actor, member),
        "view_contacts": can_view_contacts(actor, member),
        "edit_contacts": can_edit_contacts(actor, member),
        "view_qr": can_view_qr(actor, member),
        "make_organizer": is_organizer(actor) and actor.pk != member.pk and not member.is_dependent,
    }
