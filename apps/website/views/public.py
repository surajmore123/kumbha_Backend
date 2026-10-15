"""Public website endpoints: listing search, enquiries, waitlist and announcements."""

import logging
from datetime import datetime, timedelta, timezone

from django.db import IntegrityError, transaction
from django.db.models import Q

from ..conf import get_settings
from ..core import AppError, anonymize_ip, enforce, endpoint, website_phone
from ..integrations import get_notifier, search_all
from ..models import Announcement, Enquiry, Listing, ListingStatus, WaitlistEntry
from ..schemas import AnnouncementOut, EnquiryIn, EnquiryOut, ListingOut, ListingQuery, Message, Page, WaitlistIn

log = logging.getLogger("apps.website.enquiries")
IST = timezone(timedelta(hours=5, minutes=30))


@endpoint(query=ListingQuery)
def search_listings(ctx):
    """Search stays, cabs, tours and packages across every enabled provider."""
    query = ctx.query
    items = search_all(query)
    start = (query.page - 1) * query.size
    # Public, non-personal data: let the CDN / browser cache briefly.
    ctx.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"
    return Page[ListingOut](items=items[start : start + query.size], total=len(items), page=query.page, size=query.size)


@endpoint()
def get_listing(ctx, listing_id: str):
    listing = Listing.objects.filter(pk=listing_id[:32]).first()
    if not listing or listing.status != ListingStatus.published:
        raise AppError(404, "listing_not_found", "This listing is not available.")
    ctx.headers["Cache-Control"] = "public, max-age=60"
    return ListingOut.model_validate(listing)


@endpoint(auth="optional", body=EnquiryIn, limit=("enquiry", 10), status=201)
def submit_enquiry(ctx):
    """Public enquiry for a stay, cab, tour or package (or general help)."""
    data = ctx.body
    if data.website:  # hidden honeypot field filled in -> almost certainly a bot
        raise AppError(400, "invalid", "Could not submit the enquiry.")
    enforce(f"enquiry-phone:{data.phone}", 5, 3_600)
    if data.listing_id:
        listing = Listing.objects.filter(pk=data.listing_id).first()
        if not listing or listing.status != ListingStatus.published:
            raise AppError(404, "listing_not_found", "This listing is not available.")
    enquiry = Enquiry.objects.create(
        **data.model_dump(exclude={"website"}),
        user=ctx.user,
        ip_hash=anonymize_ip(ctx.ip),
    )
    _notify(enquiry)
    return EnquiryOut.model_validate(enquiry)


def _notify(e: Enquiry) -> None:
    notifier = get_notifier()
    to = get_settings().enquiry_notify_to
    if not notifier or not to:
        return
    dates = f"{e.date_from} → {e.date_to}" if e.date_from else "flexible"
    body = (
        f"New Kumbh Path enquiry #{e.id[:8]}\n{e.subject}\n"
        f"{e.name} · +91 {e.phone}\nDates: {dates} · People: {e.people} · Lang: {e.language}\n{e.notes or ''}"
    )
    if not notifier.send_text(to, body):
        log.warning("enquiry notification not delivered", extra={"enquiry_id": e.id})


def enquiries_of(user):
    """Enquiries made by this account, or with its verified mobile before signing in."""
    cond = Q(user=user)
    phone = website_phone(user)
    if phone:
        cond |= Q(phone=phone)
    return Enquiry.objects.filter(cond)


@endpoint(auth="user")
def my_enquiries(ctx):
    rows = enquiries_of(ctx.user).order_by("-created_at")[:50]
    return [EnquiryOut.model_validate(r) for r in rows]


@endpoint(body=WaitlistIn, limit=("waitlist", 5), status=201)
def join_waitlist(ctx):
    body = ctx.body
    if not WaitlistEntry.objects.filter(contact=body.contact).exists():
        try:
            with transaction.atomic():
                WaitlistEntry.objects.create(**body.model_dump())
        except IntegrityError:  # concurrent duplicate; same outcome
            pass
    # Same response whether new or existing, so the endpoint can't be used to probe who signed up.
    return Message(message="You're on the list")


@endpoint()
def current_announcements(ctx):
    """Announcements on show now: published and inside their (IST) date window."""
    today = datetime.now(IST).date()
    rows = (
        Announcement.objects.filter(published=True)
        .filter(Q(starts_on__isnull=True) | Q(starts_on__lte=today))
        .filter(Q(ends_on__isnull=True) | Q(ends_on__gte=today))
        .order_by("-pinned", "-created_at")[:10]
    )
    return [AnnouncementOut.model_validate(r) for r in rows]
