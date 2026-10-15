"""Request/response shapes, ported unchanged from the old FastAPI backend so the website sees exactly the
same JSON and the same validation rules."""

import json
import re
from datetime import UTC, date, datetime
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    SerializerFunctionWrapHandler,
    field_serializer,
    field_validator,
    model_validator,
)

from .models import AnnouncementKind, EnquiryStatus, ListingCategory, ListingStatus, PartnerStatus, Trust

T = TypeVar("T")
UserRole = Literal["user", "partner", "admin"]

# ───────────────────────── common ─────────────────────────

_INDIAN_MOBILE = re.compile(r"^[6-9]\d{9}$")
LANGUAGE_CODES = {
    "en", "hi", "bn", "mr", "te", "ta", "gu", "ur", "kn", "or", "ml", "pa", "as", "mai",
    "sat", "ks", "ne", "sd", "doi", "gom", "mni-Mtei", "brx", "sa",
}  # fmt: skip


def _phone(v: str) -> str:
    digits = re.sub(r"\D", "", v)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if not _INDIAN_MOBILE.match(digits):
        raise ValueError("Enter a valid 10-digit Indian mobile number")
    return digits


def _language(v: str) -> str:
    if v not in LANGUAGE_CODES:
        raise ValueError("Unsupported language code")
    return v


def _clean_text(v: str) -> str:
    # Strip control characters; keep all Indian scripts.
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", v).strip()


Phone = Annotated[str, Field(min_length=10, max_length=16), AfterValidator(_phone)]
Language = Annotated[str, AfterValidator(_language)]
Name = Annotated[str, Field(min_length=1, max_length=80), AfterValidator(_clean_text)]
ShortText = Annotated[str, Field(max_length=160), AfterValidator(_clean_text)]
LongText = Annotated[str, Field(max_length=2000), AfterValidator(_clean_text)]


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", str_strip_whitespace=True)

    @field_serializer("*", mode="wrap")
    def _utc_datetimes(self, value: Any, handler: SerializerFunctionWrapHandler) -> Any:
        if isinstance(value, datetime):
            value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return handler(value)


class Page(ApiModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int


class Message(ApiModel):
    message: str


# ───────────────────────── auth ─────────────────────────


class OtpRequest(ApiModel):
    phone: Phone


class OtpRequested(ApiModel):
    expires_in: int
    resend_in: int
    debug_code: str | None = None  # only returned in dev with the console SMS provider


class OtpVerify(ApiModel):
    phone: Phone
    code: str = Field(pattern=r"^\d{4,8}$")


class UserOut(ApiModel):
    id: str
    phone: str | None
    email: str | None = None
    name: str | None
    role: UserRole
    preferred_language: str
    created_at: datetime


class TokenPair(ApiModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class GoogleSignIn(ApiModel):
    credential: str = Field(min_length=100, max_length=4096)  # Google ID token (JWT)


class RefreshIn(ApiModel):
    refresh_token: str = Field(min_length=20, max_length=200)


class ProfileUpdate(ApiModel):
    name: Name | None = None
    preferred_language: Language | None = None


# ───────────────────────── listings & partners ─────────────────────────


class ListingOut(ApiModel):
    id: str
    category: ListingCategory
    name: str
    type: str
    town: str
    area: str
    price_from: int
    unit: str
    highlights: list[str]
    distance: str | None = None
    duration: str | None = None
    trust: Trust
    wheelchair: bool
    image: str | None = None
    is_sample: bool = False
    source: str = "internal"


class ListingQuery(ApiModel):
    # Shared links carry tracking parameters (utm_*, fbclid); ignore them instead of failing with 422.
    model_config = ConfigDict(from_attributes=True, extra="ignore", str_strip_whitespace=True)

    category: ListingCategory | None = None
    type: str | None = Field(default=None, max_length=40)
    town: str | None = Field(default=None, max_length=60)
    q: str | None = Field(default=None, max_length=80)
    accessible: bool = False
    sort: Literal["price-asc", "price-desc"] = "price-asc"
    page: int = Field(default=1, ge=1, le=500)
    size: int = Field(default=24, ge=1, le=100)


class ListingIn(ApiModel):
    """What a partner submits; goes to admin review before publishing."""

    name: ShortText
    type: str = Field(min_length=2, max_length=40)
    town: str = Field(min_length=2, max_length=60)
    area: ShortText
    price_from: int = Field(ge=0, le=10_000_000)
    unit: str = Field(min_length=2, max_length=80)
    highlights: list[str] = Field(default_factory=list, max_length=8)
    distance: str | None = Field(default=None, max_length=60)
    duration: str | None = Field(default=None, max_length=60)
    wheelchair: bool = False


class ListingUpdate(ApiModel):
    price_from: int | None = Field(default=None, ge=0, le=10_000_000)
    unit: str | None = Field(default=None, max_length=80)
    highlights: list[str] | None = Field(default=None, max_length=8)
    wheelchair: bool | None = None


class ListingAdminOut(ListingOut):
    status: ListingStatus
    partner_id: str | None


class PartnerIn(ApiModel):
    name: Name
    category: ListingCategory
    contact_phone: Phone
    contact_email: str | None = Field(default=None, max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    town: str = Field(min_length=2, max_length=60)
    registration_number: str | None = Field(default=None, max_length=60)


class PartnerOut(ApiModel):
    id: str
    name: str
    category: ListingCategory
    contact_phone: str
    town: str
    status: PartnerStatus
    contact_email: str | None = None
    registration_number: str | None = None


# ───────────────────────── enquiries & waitlist ─────────────────────────

KUMBH_START = date(2026, 10, 1)
KUMBH_END = date(2028, 7, 31)


class EnquiryIn(ApiModel):
    subject: ShortText
    listing_id: str | None = Field(default=None, max_length=32)
    name: Name
    phone: Phone
    date_from: date | None = None
    date_to: date | None = None
    people: int = Field(default=1, ge=1, le=60)
    notes: LongText | None = None
    language: Language = "en"
    website: str | None = Field(default=None, max_length=0)  # honeypot: must stay empty

    @model_validator(mode="after")
    def _dates(self) -> "EnquiryIn":
        for d in (self.date_from, self.date_to):
            if d and not (KUMBH_START <= d <= KUMBH_END):
                raise ValueError("Dates must fall within the Simhastha (Oct 2026 – Jul 2028)")
        if self.date_from and self.date_to and self.date_to < self.date_from:
            raise ValueError("End date must be after the start date")
        return self


class EnquiryOut(ApiModel):
    id: str
    subject: str
    status: EnquiryStatus
    created_at: datetime


class EnquiryAdminOut(EnquiryOut):
    listing_id: str | None
    name: str
    phone: str
    date_from: date | None
    date_to: date | None
    people: int
    notes: str | None
    language: str


class EnquiryStatusUpdate(ApiModel):
    status: EnquiryStatus


class WaitlistIn(ApiModel):
    name: Name
    contact: str = Field(min_length=5, max_length=120)
    language: Language = "en"

    @model_validator(mode="after")
    def _contact(self) -> "WaitlistIn":
        c = self.contact.strip()
        digits = re.sub(r"\D", "", c)
        if "@" in c:
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", c):
                raise ValueError("Enter a valid email")
            self.contact = c.lower()
        elif re.match(r"^[6-9]\d{9}$", digits[-10:]) and len(digits) in (10, 12):
            self.contact = digits[-10:]
        else:
            raise ValueError("Enter a 10-digit mobile number or an email")
        return self


# ───────────────────────── safety cards ─────────────────────────

Title = Literal["", "Shri", "Smt.", "Kumari", "Mr", "Mrs", "Ms", "Master"]
BloodGroup = Literal["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
PHOTO_PREFIX = "data:image/jpeg;base64,"
MAX_PHOTO_CHARS = 48_000  # ~35 KB JPEG; keeps each request well under the body-size limit


class SafetyCardIn(ApiModel):
    title: Title = ""
    name: str = Field(min_length=2, max_length=60)
    age: int | None = Field(default=None, ge=1, le=120)
    blood: BloodGroup | None = None
    phones: list[str] = Field(min_length=1, max_length=3)
    meet: str = Field(min_length=3, max_length=80)
    notes: str | None = Field(default=None, max_length=80)
    photo: str | None = Field(default=None, max_length=MAX_PHOTO_CHARS)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if any(ch.isdigit() for ch in v):
            raise ValueError("A name can't contain numbers")
        return v

    @field_validator("phones")
    @classmethod
    def _phones(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for raw in v:
            digits = re.sub(r"\D", "", raw)
            if len(digits) == 12 and digits.startswith("91"):
                digits = digits[2:]
            elif len(digits) == 11 and digits.startswith("0"):
                digits = digits[1:]
            if not _INDIAN_MOBILE.match(digits):
                raise ValueError(f"{raw!r} is not a valid 10-digit mobile number")
            if digits not in out:
                out.append(digits)
        return out

    @field_validator("photo")
    @classmethod
    def _photo(cls, v: str | None) -> str | None:
        if v and not (v.startswith(PHOTO_PREFIX) and re.fullmatch(r"[A-Za-z0-9+/=]+", v[len(PHOTO_PREFIX) :])):
            raise ValueError("Photo must be a JPEG image")
        return v or None


class SafetyCardOut(ApiModel):
    id: str
    title: str
    name: str
    age: int | None
    blood: str | None
    phones: list[str]
    meet: str
    notes: str | None
    photo: str | None
    created_at: datetime
    updated_at: datetime

    @field_validator("phones", mode="before")
    @classmethod
    def _split(cls, v: object) -> object:
        return [p for p in v.split(",") if p] if isinstance(v, str) else v


# ───────────────────────── saved items ─────────────────────────

ItemKind = Literal["insight", "plan", "journal", "packing", "passport"]
KIND_LIMITS: dict[str, int] = {"insight": 500, "plan": 5, "journal": 300, "packing": 5, "passport": 100}
MAX_DATA_CHARS = 16_000
KEY_PATTERN = r"^[A-Za-z0-9._:-]{1,80}$"


class UserItemIn(ApiModel):
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("data")
    @classmethod
    def _size(cls, v: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(v, ensure_ascii=False)) > MAX_DATA_CHARS:
            raise ValueError("Item is too large")
        return v


class UserItemOut(ApiModel):
    kind: str
    key: str
    data: dict[str, Any]
    updated_at: datetime

    @field_validator("data", mode="before")
    @classmethod
    def _load(cls, v: object) -> object:
        return json.loads(v) if isinstance(v, str) else v


# ───────────────────────── admin ─────────────────────────


class UserActivity(ApiModel):
    """Counts only: the content of journals, safety cards etc. stays private to the user."""

    plans: int = 0
    safety_cards: int = 0
    saved_insights: int = 0
    journal_entries: int = 0
    packing_lists: int = 0
    enquiries: int = 0


class UserAdminOut(ApiModel):
    id: str
    name: str | None
    phone: str | None
    email: str | None
    role: UserRole
    is_active: bool
    preferred_language: str
    created_at: datetime
    last_login_at: datetime | None
    activity: UserActivity = UserActivity()


class UserAdminDetail(UserAdminOut):
    enquiries: list[EnquiryAdminOut] = []


class UserAdminUpdate(ApiModel):
    role: UserRole | None = None
    is_active: bool | None = None


class AnnouncementIn(ApiModel):
    title: str = Field(min_length=3, max_length=140)
    body: str | None = Field(default=None, max_length=1000)
    link: HttpUrl | None = None
    kind: AnnouncementKind = AnnouncementKind.info
    pinned: bool = False
    published: bool = False
    starts_on: date | None = None
    ends_on: date | None = None

    @field_validator("link")
    @classmethod
    def _https(cls, v: HttpUrl | None) -> HttpUrl | None:
        if v and v.scheme != "https":
            raise ValueError("Links must start with https://")
        return v

    @model_validator(mode="after")
    def _window(self) -> "AnnouncementIn":
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValueError("End date must be on or after the start date")
        return self


class AnnouncementOut(ApiModel):
    id: str
    title: str
    body: str | None
    link: str | None
    kind: AnnouncementKind
    pinned: bool
    published: bool
    starts_on: date | None
    ends_on: date | None
    created_at: datetime
    updated_at: datetime
