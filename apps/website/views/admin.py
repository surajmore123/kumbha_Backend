"""Website admin: overview stats, enquiry/partner/listing review, users and announcements.
Only admin panel accounts (AdminAccount, signed in at /admin with username + password) can call these;
website/app users never can, whatever their role."""

from typing import Annotated

from django.db.models import Count, Q
from pydantic import Field

from ..core import AppError, User, endpoint, user_by_id, user_out
from ..models import (
    Announcement,
    Enquiry,
    EnquiryStatus,
    Listing,
    ListingStatus,
    Partner,
    PartnerStatus,
    RefreshToken,
    SafetyCard,
    UserItem,
    WaitlistEntry,
)
from ..schemas import (
    AnnouncementIn,
    AnnouncementOut,
    EnquiryAdminOut,
    EnquiryStatusUpdate,
    ListingAdminOut,
    Page,
    PartnerOut,
    UserActivity,
    UserAdminDetail,
    UserAdminOut,
    UserAdminUpdate,
    UserRole,
)
from .public import enquiries_of

PageNo = Annotated[int, Field(ge=1)]
PageSize = Annotated[int, Field(ge=1, le=100)]


@endpoint(auth="admin")
def stats(ctx):
    """Counts for the admin overview."""
    by_status = dict(Enquiry.objects.values_list("status").annotate(n=Count("id")).values_list("status", "n"))
    return {
        "enquiries": {s.value: by_status.get(s.value, 0) for s in EnquiryStatus} | {"total": sum(by_status.values())},
        "partners_pending": Partner.objects.filter(status=PartnerStatus.pending).count(),
        "listings_pending": Listing.objects.filter(status=ListingStatus.pending).count(),
        "users": User.objects.count(),
        "waitlist": WaitlistEntry.objects.count(),
    }


@endpoint(auth="admin", query={"status": ListingStatus | None})
def list_listings(ctx):
    status = ctx.query.get("status", ListingStatus.pending)
    qs = Listing.objects.order_by("-created_at")
    if status:
        qs = qs.filter(status=status)
    return [ListingAdminOut.model_validate(r) for r in qs[:200]]


@endpoint(auth="admin", query={"status": EnquiryStatus | None, "page": PageNo, "size": PageSize})
def list_enquiries(ctx):
    page, size = ctx.query.get("page", 1), ctx.query.get("size", 50)
    qs = Enquiry.objects.all()
    if ctx.query.get("status"):
        qs = qs.filter(status=ctx.query["status"])
    rows = qs.order_by("-created_at")[(page - 1) * size : page * size]
    return Page[EnquiryAdminOut](items=[EnquiryAdminOut.model_validate(r) for r in rows], total=qs.count(), page=page, size=size)


@endpoint(auth="admin", body=EnquiryStatusUpdate)
def update_enquiry(ctx, enquiry_id: str):
    enquiry = Enquiry.objects.filter(pk=enquiry_id[:32]).first()
    if not enquiry:
        raise AppError(404, "not_found", "Enquiry not found.")
    enquiry.status = ctx.body.status
    enquiry.save()
    return EnquiryAdminOut.model_validate(enquiry)


@endpoint(auth="admin", query={"status": PartnerStatus | None})
def list_partners(ctx):
    status = ctx.query.get("status", PartnerStatus.pending)
    qs = Partner.objects.order_by("created_at")
    if status:
        qs = qs.filter(status=status)
    return [PartnerOut.model_validate(p) for p in qs]


def _required_status(ctx):
    """`?status=` is a required query parameter on the status-change endpoints."""
    if "status" not in ctx.query:
        raise AppError(422, "validation_error", "Some fields are invalid.", fields=[{"field": "status", "message": "Field required"}])
    return ctx.query["status"]


@endpoint(auth="admin", query={"status": PartnerStatus})
def set_partner_status(ctx, partner_id: str):
    status = _required_status(ctx)
    partner = Partner.objects.filter(pk=partner_id[:32]).first()
    if not partner:
        raise AppError(404, "not_found", "Partner not found.")
    partner.status = status
    partner.save()
    return PartnerOut.model_validate(partner)


@endpoint(auth="admin", query={"status": ListingStatus})
def set_listing_status(ctx, listing_id: str):
    status = _required_status(ctx)
    listing = Listing.objects.filter(pk=listing_id[:32]).first()
    if not listing:
        raise AppError(404, "not_found", "Listing not found.")
    listing.status = status
    listing.save()
    return ListingAdminOut.model_validate(listing)


# ───────────────────────── users ─────────────────────────

ITEM_FIELDS = {"plan": "plans", "insight": "saved_insights", "journal": "journal_entries", "packing": "packing_lists"}


def _activity(users: list) -> dict:
    """Counts per user. Only numbers: what users wrote stays private to them."""
    acts = {u.pk: UserActivity() for u in users}
    if not users:
        return acts
    ids = list(acts)
    for uid, kind, n in UserItem.objects.filter(user_id__in=ids).values_list("user_id", "kind").annotate(n=Count("id")):
        if kind in ITEM_FIELDS:
            setattr(acts[uid], ITEM_FIELDS[kind], n)
    for uid, n in SafetyCard.objects.filter(user_id__in=ids).values_list("user_id").annotate(n=Count("id")):
        acts[uid].safety_cards = n
    for u in users:
        acts[u.pk].enquiries = enquiries_of(u).count()
    return acts


def _admin_out(user, activity: UserActivity, cls=UserAdminOut, **extra):
    data = user_out(user)
    data.pop("preferred_language")
    return cls(
        **data,
        is_active=user.is_active,
        preferred_language=user.preferred_language,
        last_login_at=user.last_login,
        activity=activity,
        **extra,
    )


@endpoint(auth="admin", query={"q": Annotated[str, Field(max_length=80)], "role": UserRole, "page": PageNo, "size": PageSize})
def list_users(ctx):
    page, size = ctx.query.get("page", 1), ctx.query.get("size", 50)
    qs = User.objects.all()
    q = (ctx.query.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(full_Name__icontains=q) | Q(phone_number__contains=q) | Q(email__icontains=q))
    if ctx.query.get("role"):
        qs = qs.filter(role=ctx.query["role"])
    total = qs.count()
    users = list(qs.order_by("-created_at")[(page - 1) * size : page * size])
    acts = _activity(users)
    return Page[UserAdminOut](items=[_admin_out(u, acts[u.pk]) for u in users], total=total, page=page, size=size)


def _detail(user) -> UserAdminDetail:
    acts = _activity([user])
    enquiries = [EnquiryAdminOut.model_validate(e) for e in enquiries_of(user).order_by("-created_at")[:100]]
    return _admin_out(user, acts[user.pk], cls=UserAdminDetail, enquiries=enquiries)


def _get_user(user_id: str):
    user = user_by_id(user_id)
    if not user:
        raise AppError(404, "not_found", "User not found.")
    return user


@endpoint(auth="admin")
def get_user(ctx, user_id: str):
    return _detail(_get_user(user_id))


@endpoint(auth="admin", body=UserAdminUpdate)
def update_user(ctx, user_id: str):
    user = _get_user(user_id)
    body = ctx.body
    if body.role == "admin":
        raise AppError(400, "admin_is_separate", "Website users can't be admins. Add an admin account under Admins instead.")
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
        if not body.is_active:
            # Sign them out everywhere; current access tokens already stop working (checked per request).
            RefreshToken.objects.filter(user=user).delete()
    user.save()
    return _detail(user)


# ───────────────────────── announcements ─────────────────────────


@endpoint(auth="admin")
def list_announcements(ctx):
    rows = Announcement.objects.order_by("-pinned", "-created_at")[:200]
    return [AnnouncementOut.model_validate(r) for r in rows]


def _announcement_fields(body: AnnouncementIn) -> dict:
    data = body.model_dump(mode="json", exclude={"starts_on", "ends_on"})
    return data | {"starts_on": body.starts_on, "ends_on": body.ends_on}


@endpoint(auth="admin", body=AnnouncementIn, status=201)
def create_announcement(ctx):
    a = Announcement.objects.create(**_announcement_fields(ctx.body), created_by_admin=ctx.admin)
    return AnnouncementOut.model_validate(a)


@endpoint(auth="admin", body=AnnouncementIn)
def update_announcement(ctx, ann_id: str):
    a = Announcement.objects.filter(pk=ann_id[:32]).first()
    if not a:
        raise AppError(404, "not_found", "Announcement not found.")
    for k, v in _announcement_fields(ctx.body).items():
        setattr(a, k, v)
    a.save()
    return AnnouncementOut.model_validate(a)


@endpoint(auth="admin", status=204)
def delete_announcement(ctx, ann_id: str):
    Announcement.objects.filter(pk=ann_id[:32]).delete()
