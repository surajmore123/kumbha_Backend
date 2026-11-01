"""
Family Safety Circle: the foundation for later safety features.

A FamilyMember is one person in one circle. Adults with accounts link to their
User, so no profile data is copied, and they only ever join by accepting an
invitation. Dependents have no account and are managed by guardians.

Every access rule lives in `apps.family.policy`, and the API enforces it.
"""

import hashlib
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

LANGUAGES = (("en", "English"), ("hi", "Hindi"), ("mr", "Marathi"))
# No 0/O or 1/I, so a code reads clearly over the phone.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 12
# The token goes after "#": browsers never send that part to a server, so it
# can't reach Cloudflare or nginx logs, and the web page learns nothing.
INVITE_LINK_BASE = "https://kumbhapath.in/join/family"


def normalize_mobile(value):
    """'+91XXXXXXXXXX' from a 10-digit Indian mobile, as stored on User. None if invalid."""
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) == 10 and digits[0] in "6789":
        return f"+91{digits}"
    return None


def validate_mobile(value):
    if value and normalize_mobile(value) is None:
        raise ValidationError("Enter a valid 10-digit mobile number.")


def hash_code(code):
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def clean_code(raw):
    return "".join(ch for ch in str(raw or "").upper() if ch.isalnum())


def new_code():
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(CODE_LENGTH))


def new_link_token():
    return secrets.token_urlsafe(32)  # 256 bits


def invite_link(token):
    return f"{INVITE_LINK_BASE}#t={token}"


class FamilyCircle(models.Model):
    MAX_PER_USER = 3
    MAX_MEMBERS = 30

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=300, blank=True)
    language = models.CharField(max_length=2, choices=LANGUAGES, default="en")
    organizer_offer = models.ForeignKey(
        "FamilyMember", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        help_text="An adult offered the organizer role. They must accept it.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.name


class FamilyMember(models.Model):
    class Kind(models.TextChoices):
        ACCOUNT_HOLDER = "account_holder", "Account holder"
        INDEPENDENT_ADULT = "independent_adult", "Independent adult"
        DEPENDENT_CHILD = "dependent_child", "Dependent child"
        DEPENDENT_ELDERLY = "dependent_elderly", "Dependent elderly member"
        DEPENDENT_OTHER = "dependent_other", "Other dependent"

    class Role(models.TextChoices):
        ORGANIZER = "organizer", "Family organizer"
        MEMBER = "member", "Member"

    class Relationship(models.TextChoices):
        SELF = "self", "Self"
        FATHER = "father", "Father"
        MOTHER = "mother", "Mother"
        SON = "son", "Son"
        DAUGHTER = "daughter", "Daughter"
        GRANDFATHER = "grandfather", "Grandfather"
        GRANDMOTHER = "grandmother", "Grandmother"
        SPOUSE = "spouse", "Spouse"
        SIBLING = "sibling", "Sibling"
        OTHER = "other", "Other relative"

    class AgeGroup(models.TextChoices):
        UNDER_6 = "under_6", "Under 6"
        AGE_6_12 = "6_12", "6 to 12"
        AGE_13_17 = "13_17", "13 to 17"
        ADULT = "adult", "18 to 59"
        SENIOR = "senior", "60 or over"

    class ConsentBasis(models.TextChoices):
        AGREED = "agreed", "They have agreed to this"
        AUTHORITY = "authority", "I have authority to act for them"

    DEPENDENT_KINDS = (Kind.DEPENDENT_CHILD, Kind.DEPENDENT_ELDERLY, Kind.DEPENDENT_OTHER)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    family = models.ForeignKey(FamilyCircle, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True,
        related_name="family_memberships",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    relationship = models.CharField(max_length=12, choices=Relationship.choices)
    # Dependents only. Adults' names come from their account.
    full_name = models.CharField(max_length=120, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    age_group = models.CharField(max_length=8, choices=AgeGroup.choices, blank=True)
    mobile = models.CharField(max_length=20, blank=True, validators=[validate_mobile])
    language = models.CharField(max_length=2, choices=LANGUAGES, default="en")
    consent_basis = models.CharField(max_length=10, choices=ConsentBasis.choices, blank=True)
    # An adult's own choices. All start off.
    share_phone = models.BooleanField(default=False, help_text="Let family members see my number.")
    share_contacts_with_organizer = models.BooleanField(default=False)
    # Recorded now for the later location phase. Nothing uses it yet.
    location_sharing_consent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["family", "kind"])]
        constraints = [
            models.UniqueConstraint(
                fields=["family", "user"], condition=Q(user__isnull=False), name="family_one_membership_per_user",
            ),
            models.UniqueConstraint(
                fields=["family"], condition=Q(role="organizer"), name="family_one_organizer",
            ),
            models.CheckConstraint(
                condition=(
                    Q(kind__in=["account_holder", "independent_adult"], user__isnull=False)
                    | Q(kind__in=["dependent_child", "dependent_elderly", "dependent_other"], user__isnull=True)
                ),
                name="family_adults_have_accounts_dependents_do_not",
            ),
            models.CheckConstraint(
                condition=Q(role="member") | Q(kind__in=["account_holder", "independent_adult"]),
                name="family_organizer_is_an_adult",
            ),
        ]

    def __str__(self):
        return f"{self.pk} ({self.kind})"

    @property
    def is_dependent(self):
        return self.kind in self.DEPENDENT_KINDS

    @property
    def display_name(self):
        if self.user_id:
            return (self.user.full_Name or "").strip() or "Family member"
        return self.full_name


class MemberPhoto(models.Model):
    """Held in the database, not /media/, because media files are public and
    many of these are children. Served only to members of the circle."""

    member = models.OneToOneField(FamilyMember, on_delete=models.CASCADE, primary_key=True, related_name="photo")
    content_type = models.CharField(max_length=40)
    data = models.BinaryField()
    updated_at = models.DateTimeField(auto_now=True)


class GuardianLink(models.Model):
    dependent = models.ForeignKey(FamilyMember, on_delete=models.CASCADE, related_name="guardian_links")
    guardian = models.ForeignKey(FamilyMember, on_delete=models.CASCADE, related_name="dependent_links")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["dependent", "guardian"], name="family_unique_guardian"),
        ]

    def clean(self):
        if self.dependent.family_id != self.guardian.family_id:
            raise ValidationError("A guardian must be in the same family.")
        if not self.dependent.is_dependent or self.guardian.is_dependent:
            raise ValidationError("Guardians are adults with accounts; only dependents have guardians.")


class FamilyInvitation(models.Model):
    """Can be used by a short code or a long link. Neither is stored, only their
    hashes, and both are shown once. One response ends the invitation for both."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        REVOKED = "revoked", "Revoked"

    VALID_FOR = timedelta(days=3)
    MAX_PENDING = 10

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    family = models.ForeignKey(FamilyCircle, on_delete=models.CASCADE, related_name="invitations")
    code_hash = models.CharField(max_length=64, unique=True)
    # Invitations made before links existed have none.
    link_hash = models.CharField(max_length=64, unique=True, null=True, blank=True, editable=False)
    # Set for an in-app invitation: only this number's account can accept.
    invited_phone = models.CharField(max_length=20, blank=True, db_index=True)
    relationship = models.CharField(max_length=12, choices=FamilyMember.Relationship.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    expires_at = models.DateTimeField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+",
    )
    responded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    responded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["family", "status"])]

    def __str__(self):
        return f"{self.family_id} {self.status}"

    @property
    def is_open(self):
        return self.status == self.Status.PENDING and self.expires_at > timezone.now()

    @property
    def state(self):
        if self.status == self.Status.PENDING and not self.is_open:
            return "expired"
        return self.status


class EmergencyContact(models.Model):
    """Belongs to one person (`member`), or to the whole family if none."""

    class Method(models.TextChoices):
        CALL = "call", "Phone call"
        SMS = "sms", "SMS"
        WHATSAPP = "whatsapp", "WhatsApp"

    MAX_PER_OWNER = 10

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    family = models.ForeignKey(FamilyCircle, on_delete=models.CASCADE, related_name="emergency_contacts")
    member = models.ForeignKey(
        FamilyMember, on_delete=models.CASCADE, null=True, blank=True, related_name="emergency_contacts",
    )
    name = models.CharField(max_length=120)
    relationship = models.CharField(max_length=60, blank=True)
    mobile = models.CharField(max_length=20, validators=[validate_mobile])
    priority = models.PositiveSmallIntegerField(default=1)
    method = models.CharField(max_length=10, choices=Method.choices, default=Method.CALL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["priority", "created_at"]
        indexes = [models.Index(fields=["family", "member", "priority"])]

    def __str__(self):
        return str(self.pk)


class FamilyAuditLog(models.Model):
    """Sensitive changes. No names or numbers, and it outlives a deleted family."""

    id = models.BigAutoField(primary_key=True)
    family = models.ForeignKey(FamilyCircle, on_delete=models.SET_NULL, null=True, related_name="audit_logs")
    family_ref = models.UUIDField(db_index=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    action = models.CharField(max_length=40, db_index=True)
    target_member = models.UUIDField(null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} {self.created_at:%Y-%m-%d %H:%M}"
