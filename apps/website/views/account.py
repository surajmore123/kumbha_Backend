"""Signed-in user's own data: saved items, family safety cards, and the partner portal."""

import json
from typing import Annotated

from pydantic import StringConstraints

from ..core import AppError, endpoint
from ..models import Listing, ListingStatus, Partner, PartnerStatus, SafetyCard, UserItem
from ..schemas import (
    KEY_PATTERN,
    KIND_LIMITS,
    ItemKind,
    ListingAdminOut,
    ListingIn,
    ListingUpdate,
    PartnerIn,
    PartnerOut,
    SafetyCardIn,
    SafetyCardOut,
    UserItemIn,
    UserItemOut,
)

Key = Annotated[str, StringConstraints(pattern=KEY_PATTERN)]

# ───────────────────────── saved items ─────────────────────────


@endpoint(auth="user", query={"kind": ItemKind})
def list_items(ctx):
    """Everything the signed-in user saved (optionally one kind), newest first."""
    qs = UserItem.objects.filter(user=ctx.user)
    if ctx.query.get("kind"):
        qs = qs.filter(kind=ctx.query["kind"])
    return [UserItemOut.model_validate(r) for r in qs.order_by("-updated_at")]


@endpoint(auth="user", path={"kind": ItemKind, "key": Key}, body=UserItemIn, limit=("user_items", 120))
def put_item(ctx, kind: str, key: str):
    """Create or replace one saved item."""
    item = UserItem.objects.filter(user=ctx.user, kind=kind, key=key).first()
    data = json.dumps(ctx.body.data, ensure_ascii=False)
    if item:
        item.data = data
        item.save()
    else:
        if UserItem.objects.filter(user=ctx.user, kind=kind).count() >= KIND_LIMITS[kind]:
            raise AppError(409, "too_many_items", f"You can save up to {KIND_LIMITS[kind]} items of this kind.")
        item = UserItem.objects.create(user=ctx.user, kind=kind, key=key, data=data)
    return UserItemOut.model_validate(item)


@endpoint(auth="user", path={"kind": ItemKind, "key": Key}, status=204)
def delete_item(ctx, kind: str, key: str):
    # Deleting something already gone is fine (idempotent).
    UserItem.objects.filter(user=ctx.user, kind=kind, key=key).delete()


# ───────────────────────── safety cards ─────────────────────────

MAX_CARDS = 12  # a large family; keeps one account from filling the table


def _card_fields(body: SafetyCardIn) -> dict:
    data = body.model_dump()
    data["phones"] = ",".join(data["phones"])
    return data


def _own_card(user, card_id: str) -> SafetyCard:
    card = SafetyCard.objects.filter(pk=card_id, user=user).first()
    if not card:  # same answer for "missing" and "someone else's"
        raise AppError(404, "not_found", "Safety card not found.")
    return card


@endpoint(auth="user")
def list_cards(ctx):
    return [SafetyCardOut.model_validate(r) for r in SafetyCard.objects.filter(user=ctx.user).order_by("-updated_at")]


@endpoint(auth="user", body=SafetyCardIn, limit=("safety_card", 30), status=201)
def create_card(ctx):
    if SafetyCard.objects.filter(user=ctx.user).count() >= MAX_CARDS:
        raise AppError(409, "too_many_cards", f"You can keep up to {MAX_CARDS} safety cards. Delete one to add another.")
    card = SafetyCard.objects.create(user=ctx.user, **_card_fields(ctx.body))
    return SafetyCardOut.model_validate(card)


@endpoint(auth="user", body=SafetyCardIn, limit=("safety_card", 30))
def update_card(ctx, card_id: str):
    card = _own_card(ctx.user, card_id)
    for k, v in _card_fields(ctx.body).items():
        setattr(card, k, v)
    card.save()
    return SafetyCardOut.model_validate(card)


@endpoint(auth="user", status=204)
def delete_card(ctx, card_id: str):
    _own_card(ctx.user, card_id).delete()


# ───────────────────────── partner portal ─────────────────────────


def _my_partner(user) -> Partner:
    partner = Partner.objects.filter(owner_user=user).first()
    if not partner:
        raise AppError(404, "partner_not_found", "Register as a partner first.")
    return partner


@endpoint(auth="user", body=PartnerIn, status=201)
def apply_partner(ctx):
    """Apply to list a business. An admin verifies documents before anything goes live."""
    if Partner.objects.filter(owner_user=ctx.user).exists():
        raise AppError(409, "already_partner", "You have already applied.")
    partner = Partner.objects.create(**ctx.body.model_dump(), owner_user=ctx.user)
    if ctx.user.role == "user":
        ctx.user.role = "partner"
        ctx.user.save(update_fields=["role", "updated_at"])
    return PartnerOut.model_validate(partner)


@endpoint(auth="user")
def my_partner(ctx):
    return PartnerOut.model_validate(_my_partner(ctx.user))


@endpoint(auth="user")
def my_listings(ctx):
    partner = _my_partner(ctx.user)
    return [ListingAdminOut.model_validate(r) for r in Listing.objects.filter(partner=partner)]


@endpoint(auth="user", body=ListingIn, status=201)
def create_listing(ctx):
    partner = _my_partner(ctx.user)
    if partner.status != PartnerStatus.verified:
        raise AppError(403, "partner_not_verified", "Your business must be verified before adding listings.")
    listing = Listing.objects.create(**ctx.body.model_dump(), category=partner.category, partner=partner, status=ListingStatus.pending)
    return ListingAdminOut.model_validate(listing)


@endpoint(auth="user", body=ListingUpdate)
def update_listing(ctx, listing_id: str):
    """Partners can update prices and details of their own listings (e.g. rates for Amrit Snan dates)."""
    partner = _my_partner(ctx.user)
    if partner.status != PartnerStatus.verified:
        raise AppError(403, "partner_not_verified", "Your business must be verified to change listings.")
    listing = Listing.objects.filter(pk=listing_id[:32]).first()
    if not listing or listing.partner_id != partner.id:
        raise AppError(404, "listing_not_found", "Listing not found.")
    for field, value in ctx.body.model_dump(exclude_none=True).items():
        setattr(listing, field, value)
    listing.save()
    return ListingAdminOut.model_validate(listing)
