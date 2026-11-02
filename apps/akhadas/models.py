"""
Akhadas & Sadhus: a sourced, editor-run directory.

Content is written in Django admin. Each record has one row per language in
its *Translation table (English is required before publishing), a verification
status and a list of ContentSource references. Nothing here is user-submitted.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

LANGUAGES = (("en", "English"), ("hi", "Hindi"), ("mr", "Marathi"))


def validate_https(value):
    if value and not value.lower().startswith("https://"):
        raise ValidationError("Use an https:// link.")


class ContentSource(models.Model):
    """A reference behind published facts, shared between records."""

    class Type(models.TextChoices):
        OFFICIAL_AKHADA = "official_akhada", "Official Akhada publication"
        GOVERNMENT = "government", "Government or Kumbh authority"
        ACADEMIC = "academic", "Academic or historical work"
        REFERENCE = "reference", "Encyclopedia or reference work"
        NEWS = "news", "News organization"

    title = models.CharField(max_length=250)
    url = models.URLField(max_length=500, blank=True, validators=[validate_https])
    organization = models.CharField(max_length=150, blank=True)
    source_type = models.CharField(max_length=20, choices=Type.choices)
    published_on = models.DateField(null=True, blank=True)
    accessed_on = models.DateField(default=timezone.localdate)
    verification_notes = models.TextField(
        blank=True, help_text="Internal: what this source was checked for, and any conflicts. Not shown in the app.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]
        indexes = [models.Index(fields=["source_type"])]
        constraints = [
            models.UniqueConstraint(fields=["title", "url"], name="akhadas_source_unique"),
        ]

    def __str__(self):
        return self.title


class PublishedQuerySet(models.QuerySet):
    def published(self):
        """Public content: published, with the required English text."""
        translations = self.model._meta.get_field("translations").related_model
        english = translations.objects.filter(parent=OuterRef("pk"), language="en")
        return self.filter(publication_status=Publishable.Publication.PUBLISHED).filter(Exists(english))


class Publishable(models.Model):
    """Editorial state shared by everything shown to pilgrims."""

    class Publication(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    class Verification(models.TextChoices):
        OFFICIAL = "official", "Confirmed by an official source"
        SOURCED = "sourced", "Checked against published sources"
        AWAITING = "awaiting", "Awaiting verification"

    publication_status = models.CharField(
        max_length=10, choices=Publication.choices, default=Publication.DRAFT,
    )
    verification_status = models.CharField(
        max_length=10, choices=Verification.choices, default=Verification.AWAITING,
    )
    last_verified_on = models.DateField(null=True, blank=True)
    sources = models.ManyToManyField(ContentSource, blank=True, related_name="%(class)s_set")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PublishedQuerySet.as_manager()

    class Meta:
        abstract = True

    def publish_problems(self):
        """Why this can't go live; empty when it can. Needs a saved record."""
        problems = []
        if not self.translations.filter(language="en").exists():
            problems.append("add the English text")
        if not self.sources.exists():
            problems.append("add at least one source")
        if self.verification_status != self.Verification.AWAITING and not self.last_verified_on:
            problems.append("set the last verified date")
        return problems


class ImageRights(models.Model):
    """An image with the basis for using it. Without both, the app shows a
    neutral placeholder, so an unlicensed upload can't reach pilgrims."""

    class Usage(models.TextChoices):
        OFFICIAL = "official", "Provided by the organization or person"
        LICENSED = "licensed", "Licensed for this use"
        PERMISSION = "permission", "Written permission"
        PUBLIC_DOMAIN = "public_domain", "Public domain"

    image = models.ImageField(upload_to="akhadas/", blank=True)
    image_usage = models.CharField(max_length=15, choices=Usage.choices, blank=True)
    image_credit = models.CharField(max_length=200, blank=True)
    image_source_url = models.URLField(
        max_length=500, blank=True, validators=[validate_https],
        help_text="Where the image and its licence can be checked.",
    )

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if not self.image:
            return
        if not (self.image_usage and self.image_credit.strip()):
            raise ValidationError({"image_usage": "Record the usage basis and credit for this image."})
        if self.image_usage in (self.Usage.LICENSED, self.Usage.PUBLIC_DOMAIN) and not self.image_source_url:
            raise ValidationError({"image_source_url": "Link to where the licence can be checked."})


class Translation(models.Model):
    language = models.CharField(max_length=2, choices=LANGUAGES)

    class Meta:
        abstract = True


def _unique_language(name):
    return models.UniqueConstraint(fields=["parent", "language"], name=f"akhadas_{name}_language")


class Tradition(ImageRights):
    """A broad religious tradition (Shaiva, Vaishnava, Udasin, Nirmal). Its image
    stands in, labelled as representative, for Akhadas without their own."""

    slug = models.SlugField(max_length=40, unique=True)
    position = models.PositiveSmallIntegerField(default=0)
    sources = models.ManyToManyField(ContentSource, blank=True, related_name="tradition_set")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "slug"]

    def __str__(self):
        return self.slug


class TraditionTranslation(Translation):
    parent = models.ForeignKey(Tradition, on_delete=models.CASCADE, related_name="translations")
    name = models.CharField(max_length=80)
    summary = models.TextField(help_text="Plain explanation for pilgrims new to the subject.")
    philosophy = models.TextField(blank=True)
    practices = models.TextField(blank=True)

    class Meta:
        constraints = [_unique_language("tradition")]


class SpiritualTitle(models.Model):
    """A rank or office such as Mahamandaleshwar. Usage differs by Akhada."""

    slug = models.SlugField(max_length=40, unique=True)
    position = models.PositiveSmallIntegerField(default=0)
    traditions = models.ManyToManyField(
        Tradition, blank=True, related_name="titles", help_text="Leave empty if used across traditions.",
    )
    sources = models.ManyToManyField(ContentSource, blank=True, related_name="title_set")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "slug"]

    def __str__(self):
        return self.slug


class SpiritualTitleTranslation(Translation):
    parent = models.ForeignKey(SpiritualTitle, on_delete=models.CASCADE, related_name="translations")
    name = models.CharField(max_length=80)
    meaning = models.TextField()

    class Meta:
        constraints = [_unique_language("title")]


class Akhada(Publishable, ImageRights):
    class Classification(models.TextChoices):
        PARISHAD = "parishad", "One of the 13 Akhadas of the Akhara Parishad"
        ASSOCIATED = "associated", "Associated organization"
        OTHER = "other", "Other"

    slug = models.SlugField(max_length=60, unique=True)
    position = models.PositiveSmallIntegerField(default=0)
    tradition = models.ForeignKey(Tradition, on_delete=models.PROTECT, related_name="akhadas")
    classification = models.CharField(
        max_length=12, choices=Classification.choices, default=Classification.PARISHAD,
    )
    headquarters = models.CharField(max_length=120, blank=True, help_text="Only if verified.")
    website_url = models.URLField(max_length=300, blank=True, validators=[validate_https])
    social_url = models.URLField(
        max_length=300, blank=True, validators=[validate_https], help_text="Official accounts only.",
    )
    contact_email = models.EmailField(blank=True, help_text="Only if officially published.")
    contact_phone = models.CharField(max_length=30, blank=True, help_text="Only if officially published.")

    class Meta:
        ordering = ["position", "slug"]
        indexes = [
            models.Index(fields=["publication_status", "position"]),
            models.Index(fields=["headquarters"]),
        ]

    def __str__(self):
        return self.slug


class AkhadaTranslation(Translation):
    parent = models.ForeignKey(Akhada, on_delete=models.CASCADE, related_name="translations")
    name = models.CharField(max_length=150, help_text="Official name.")
    common_name = models.CharField(max_length=80, blank=True)
    summary = models.TextField()
    history = models.TextField(blank=True, help_text="Historical account. Note disputed dates as disputed.")
    philosophy = models.TextField(blank=True)
    practices = models.TextField(blank=True)
    organization = models.TextField(blank=True, help_text="Current structure: re-verify regularly.")
    kumbh_significance = models.TextField(blank=True)
    nashik_note = models.TextField(blank=True, help_text="Only what a source supports for Nashik.")

    class Meta:
        constraints = [_unique_language("akhada")]


class SadhuProfile(Publishable, ImageRights):
    """A publicly documented saint or leader. Never a private individual."""

    class Era(models.TextChoices):
        HISTORICAL = "historical", "Historical"
        CONTEMPORARY = "contemporary", "Contemporary"

    slug = models.SlugField(max_length=60, unique=True)
    position = models.PositiveSmallIntegerField(default=0)
    era = models.CharField(max_length=12, choices=Era.choices)
    akhada = models.ForeignKey(
        Akhada, on_delete=models.SET_NULL, null=True, blank=True, related_name="saints",
        help_text="Only when a source states the affiliation.",
    )
    title = models.ForeignKey(
        SpiritualTitle, on_delete=models.SET_NULL, null=True, blank=True, related_name="holders",
    )
    website_url = models.URLField(max_length=300, blank=True, validators=[validate_https])
    social_url = models.URLField(
        max_length=300, blank=True, validators=[validate_https], help_text="Official accounts only.",
    )

    class Meta:
        ordering = ["position", "slug"]
        indexes = [models.Index(fields=["publication_status", "position"])]

    def __str__(self):
        return self.slug


class SadhuProfileTranslation(Translation):
    parent = models.ForeignKey(SadhuProfile, on_delete=models.CASCADE, related_name="translations")
    name = models.CharField(max_length=120, help_text="Public name.")
    biography = models.TextField()
    teachings = models.TextField(blank=True)
    public_activities = models.TextField(blank=True)
    significance = models.TextField(blank=True)

    class Meta:
        constraints = [_unique_language("saint")]


class SpiritualArticle(Publishable, ImageRights):
    class Category(models.TextChoices):
        BASICS = "basics", "Basics"
        TRADITIONS = "traditions", "Traditions"
        ORGANIZATION = "organization", "Organization and titles"
        KUMBH = "kumbh", "Kumbh and Amrit Snan"
        ETIQUETTE = "etiquette", "Respectful conduct"

    slug = models.SlugField(max_length=60, unique=True)
    position = models.PositiveSmallIntegerField(default=0)
    category = models.CharField(max_length=15, choices=Category.choices)
    is_editorial = models.BooleanField(
        default=False, help_text="KumbhaPath's own guidance, rather than sourced fact.",
    )
    published_on = models.DateField(null=True, blank=True)
    related_akhadas = models.ManyToManyField(Akhada, blank=True, related_name="articles")
    related_saints = models.ManyToManyField(SadhuProfile, blank=True, related_name="articles")

    class Meta:
        ordering = ["position", "slug"]
        indexes = [models.Index(fields=["publication_status", "category"])]

    def __str__(self):
        return self.slug


class SpiritualArticleTranslation(Translation):
    parent = models.ForeignKey(SpiritualArticle, on_delete=models.CASCADE, related_name="translations")
    title = models.CharField(max_length=200)
    intro = models.TextField()
    body = models.TextField(help_text="Paragraphs separated by a blank line.")

    class Meta:
        constraints = [_unique_language("article")]


class AkhadaActivity(Publishable):
    """Akhada participation and public activity at Nashik–Trimbakeshwar 2027.
    Dates that belong to the wider Kumbh link to events.Event where one exists."""

    class Kind(models.TextChoices):
        CEREMONY = "ceremony", "Ceremony"
        CAMP = "camp", "Camp or location"
        PROCESSION = "procession", "Procession"
        BATHING = "bathing", "Amrit Snan"
        PROGRAMME = "programme", "Public programme"
        ANNOUNCEMENT = "announcement", "Announcement"
        HISTORY = "history", "History"

    class Confirmation(models.TextChoices):
        CONFIRMED = "confirmed", "Officially confirmed"
        ANNOUNCED = "announced", "Announced, subject to change"
        AWAITING = "awaiting", "Awaiting confirmation"
        HISTORICAL = "historical", "Historical information"

    slug = models.SlugField(max_length=60, unique=True)
    kind = models.CharField(max_length=15, choices=Kind.choices)
    confirmation = models.CharField(
        max_length=12, choices=Confirmation.choices, default=Confirmation.AWAITING,
    )
    akhadas = models.ManyToManyField(
        Akhada, blank=True, related_name="activities", help_text="Leave empty if it concerns all Akhadas.",
    )
    event = models.ForeignKey(
        "events.Event", on_delete=models.SET_NULL, null=True, blank=True, related_name="akhada_activities",
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["start_date", "slug"]
        verbose_name_plural = "Akhada activities"
        indexes = [
            models.Index(fields=["publication_status", "start_date"]),
            models.Index(fields=["confirmation"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(start_date__isnull=False, end_date__gte=models.F("start_date")),
                name="akhadas_activity_dates",
            ),
        ]

    def __str__(self):
        return self.slug

    def clean(self):
        super().clean()
        if self.end_date and not self.start_date:
            raise ValidationError({"start_date": "Add a start date."})
        if self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date must be on or after the start date."})

    def publish_problems(self):
        problems = super().publish_problems()
        official = (ContentSource.Type.GOVERNMENT, ContentSource.Type.OFFICIAL_AKHADA)
        if self.confirmation == self.Confirmation.CONFIRMED and not self.sources.filter(source_type__in=official).exists():
            problems.append('"Officially confirmed" needs a government or official Akhada source')
        return problems


class AkhadaActivityTranslation(Translation):
    parent = models.ForeignKey(AkhadaActivity, on_delete=models.CASCADE, related_name="translations")
    title = models.CharField(max_length=200)
    description = models.TextField()
    location = models.CharField(max_length=150, blank=True, help_text="Only if verified.")

    class Meta:
        constraints = [_unique_language("activity")]
