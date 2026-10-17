"""Website (kumbhapath.in) data: listings, partners, enquiries, saved items, safety cards, announcements,
and the website's sign-in sessions. Users are the shared `authentication.User` (one account for the
website and the mobile app)."""

import uuid

from django.conf import settings
from django.db import models


def new_id() -> str:
    return uuid.uuid4().hex


class ListingCategory(models.TextChoices):
    hotels = "hotels"
    cabs = "cabs"
    tours = "tours"
    packages = "packages"


class ListingStatus(models.TextChoices):
    draft = "draft"
    pending = "pending"  # submitted by a partner, waiting for admin review
    published = "published"
    archived = "archived"


class Trust(models.TextChoices):
    official = "official"
    partner = "partner"


class PartnerStatus(models.TextChoices):
    pending = "pending"
    verified = "verified"
    rejected = "rejected"
    suspended = "suspended"


class EnquiryStatus(models.TextChoices):
    new = "new"
    contacted = "contacted"
    confirmed = "confirmed"
    closed = "closed"
    spam = "spam"


class AnnouncementKind(models.TextChoices):
    official = "official"  # from the Mela authority, police, railways…
    info = "info"  # helpful update from Kumbh Path
    alert = "alert"  # urgent: route closures, weather, crowd warnings


class Base(models.Model):
    id = models.CharField(max_length=32, primary_key=True, default=new_id, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class OtpChallenge(Base):
    """One OTP sent to a phone. Only a keyed hash of the code is stored."""

    phone = models.CharField(max_length=10, db_index=True)
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts = models.IntegerField(default=0)
    consumed_at = models.DateTimeField(null=True, blank=True)
    ip_hash = models.CharField(max_length=32, null=True, blank=True)


class PhoneLock(models.Model):
    """Temporary sign-in lock after too many wrong codes."""

    phone = models.CharField(max_length=10, primary_key=True)
    locked_until = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class RefreshToken(Base):
    """Long-lived website session token; rotated on every refresh, stored hashed."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="website_refresh_tokens")
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    user_agent = models.CharField(max_length=200, null=True, blank=True)


class Partner(Base):
    """A hotel, dharamshala, cab operator, guide or tour company. Verified by an admin before going live."""

    owner_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="website_partners")
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=16, choices=ListingCategory.choices)
    contact_phone = models.CharField(max_length=10)
    contact_email = models.CharField(max_length=120, null=True, blank=True)
    town = models.CharField(max_length=60)
    registration_number = models.CharField(max_length=60, null=True, blank=True)  # GST / trust / transport permit
    status = models.CharField(max_length=16, choices=PartnerStatus.choices, default=PartnerStatus.pending, db_index=True)
    notes = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.name


class Listing(Base):
    """A bookable stay, cab, tour or package."""

    partner = models.ForeignKey(Partner, on_delete=models.SET_NULL, null=True, blank=True, related_name="listings")
    category = models.CharField(max_length=16, choices=ListingCategory.choices)
    name = models.CharField(max_length=160)
    type = models.CharField(max_length=40)
    town = models.CharField(max_length=60, db_index=True)
    area = models.CharField(max_length=160)
    price_from = models.IntegerField(default=0)  # whole rupees; 0 = see official rates
    unit = models.CharField(max_length=80)
    highlights = models.JSONField(default=list, blank=True)
    distance = models.CharField(max_length=60, null=True, blank=True)
    duration = models.CharField(max_length=60, null=True, blank=True)
    trust = models.CharField(max_length=16, choices=Trust.choices, default=Trust.partner)
    wheelchair = models.BooleanField(default=False)
    image = models.CharField(max_length=80, null=True, blank=True)
    status = models.CharField(max_length=16, choices=ListingStatus.choices, default=ListingStatus.draft)
    is_sample = models.BooleanField(default=False)
    source = models.CharField(max_length=40, default="internal")
    external_id = models.CharField(max_length=80, null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["category", "status"])]

    def __str__(self):
        return self.name


class Enquiry(Base):
    listing = models.ForeignKey(Listing, on_delete=models.SET_NULL, null=True, blank=True, related_name="enquiries")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="website_enquiries"
    )
    subject = models.CharField(max_length=160)
    name = models.CharField(max_length=80)
    phone = models.CharField(max_length=10, db_index=True)
    date_from = models.DateField(null=True, blank=True)
    date_to = models.DateField(null=True, blank=True)
    people = models.IntegerField(default=1)
    notes = models.TextField(null=True, blank=True)
    language = models.CharField(max_length=12, default="en")
    status = models.CharField(max_length=16, choices=EnquiryStatus.choices, default=EnquiryStatus.new, db_index=True)
    ip_hash = models.CharField(max_length=32, null=True, blank=True)

    class Meta:
        verbose_name_plural = "enquiries"


class WaitlistEntry(Base):
    name = models.CharField(max_length=80)
    contact = models.CharField(max_length=120, unique=True)
    language = models.CharField(max_length=12, default="en")

    class Meta:
        verbose_name_plural = "waitlist"


class SafetyCard(Base):
    """A family safety card saved to a user's account (private to that user)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="website_safety_cards")
    title = models.CharField(max_length=12, default="", blank=True)
    name = models.CharField(max_length=60)
    age = models.IntegerField(null=True, blank=True)
    blood = models.CharField(max_length=3, null=True, blank=True)
    phones = models.CharField(max_length=40)  # up to three 10-digit mobiles, comma-separated
    meet = models.CharField(max_length=80)
    notes = models.CharField(max_length=80, null=True, blank=True)
    photo = models.TextField(null=True, blank=True)  # small JPEG data URL


class UserItem(Base):
    """Something a user saved (an insight, their plan, a journal entry, packing ticks, passport stamps)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="website_items")
    kind = models.CharField(max_length=20)
    key = models.CharField(max_length=80)
    data = models.TextField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "kind", "key"], name="website_useritem_user_kind_key")]


class Announcement(Base):
    """A notice written by an admin and shown on the website's Today and Home pages."""

    title = models.CharField(max_length=140)
    body = models.TextField(null=True, blank=True)
    link = models.CharField(max_length=300, null=True, blank=True)
    kind = models.CharField(max_length=16, choices=AnnouncementKind.choices, default=AnnouncementKind.info)
    pinned = models.BooleanField(default=False)
    published = models.BooleanField(default=False)
    starts_on = models.DateField(null=True, blank=True)  # optional IST date window, inclusive
    ends_on = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_by_admin = models.ForeignKey("AdminAccount", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    def __str__(self):
        return self.title


class AdminAccount(Base):
    """A person who runs the website admin panel (/admin). Separate from website/app users: own username +
    password and own sessions, so a user account can never open the admin panel."""

    username = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=80)
    password_hash = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    # Too many wrong passwords pause sign-in for this username (in the DB, so every replica enforces it).
    failed_logins = models.IntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    # Bumped on password change / disabling so every open admin session ends at once.
    token_version = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.name} (@{self.username})"


class SiteContent(models.Model):
    """One editable piece of website text or an image reference, e.g. key "home.hero.title".

    Only edited fields are stored: a missing key means the website shows its built-in default.
    """

    key = models.CharField(max_length=120, primary_key=True)
    page = models.CharField(max_length=40, db_index=True)
    value = models.TextField()
    updated_by = models.ForeignKey(AdminAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.key


class MediaFile(Base):
    """An image uploaded in the admin panel. Stored in the database so every API replica can serve it and
    nothing is lost when a container's disk is replaced."""

    name = models.CharField(max_length=160)
    content_type = models.CharField(max_length=40)
    ext = models.CharField(max_length=8)
    size = models.IntegerField()
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    data = models.BinaryField()
    uploaded_by = models.ForeignKey(AdminAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    def __str__(self):
        return self.name
