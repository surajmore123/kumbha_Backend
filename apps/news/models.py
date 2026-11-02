"""
Kumbh news: curated and ingested stories, always linked to the original.

Feeds only fill a review queue. Nothing from a feed reaches pilgrims until an
editor has written a summary in their own words and published it, and no
publisher text or image is stored. Official notices need an official publisher.
"""

import hashlib
from datetime import timedelta
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from apps.akhadas.models import (
    ImageRights,
    LANGUAGES,
    Publishable,
    PublishedQuerySet,
    Translation,
    validate_https,
)

DEFAULT_KEYWORDS = "kumbh\nsimhastha\nsinhastha\nकुंभ\nसिंहस्थ\nसाधुग्राम\nsadhugram"
_TRACKING = re.compile(r"^(utm_|fbclid$|gclid$|ref$|ref_src$|amp$)")


def canonical_url(url):
    """The same story often arrives with tracking parameters or a trailing slash."""
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query) if not _TRACKING.match(k)]
    return urlunsplit((
        parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query), "",
    ))


def hash_of(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def title_key(publisher_id, headline):
    """Publishers re-post stories under new URLs; the headline stays the same."""
    words = re.sub(r"[^\w\s]", "", headline.casefold()).split()
    return hash_of(f"{publisher_id}:{' '.join(words)}")


class NewsSource(models.Model):
    """A publisher, and how its stories arrive."""

    class PublisherType(models.TextChoices):
        OFFICIAL = "official", "Government or Kumbh authority"
        NEWS = "news", "News organization"
        EDITORIAL = "editorial", "KumbhaPath editorial"

    class Adapter(models.TextChoices):
        MANUAL = "manual", "Entered by editors"
        RSS = "rss", "RSS or Atom feed"

    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=60, unique=True)
    publisher_type = models.CharField(max_length=10, choices=PublisherType.choices)
    website_url = models.URLField(max_length=300, blank=True, validators=[validate_https])
    adapter = models.CharField(max_length=10, choices=Adapter.choices, default=Adapter.MANUAL)
    feed_url = models.URLField(max_length=500, blank=True, validators=[validate_https])
    is_active = models.BooleanField(
        default=False, help_text="Sync this feed. Turn on only after checking the publisher's terms.",
    )
    keywords = models.TextField(default=DEFAULT_KEYWORDS, help_text="One per line. A story needs one of these.")
    language = models.CharField(max_length=2, choices=LANGUAGES, default="en")
    default_category = models.ForeignKey(
        "NewsCategory", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    min_interval_hours = models.PositiveSmallIntegerField(default=6, help_text="Never request this feed more often.")
    terms_notes = models.TextField(blank=True, help_text="Internal: what the publisher's terms allow.")
    etag = models.CharField(max_length=200, blank=True, editable=False)
    last_modified = models.CharField(max_length=100, blank=True, editable=False)
    last_checked_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_success_at = models.DateTimeField(null=True, blank=True, editable=False)
    consecutive_failures = models.PositiveSmallIntegerField(default=0, editable=False)
    last_error = models.CharField(max_length=300, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.adapter != self.Adapter.MANUAL and not self.feed_url:
            raise ValidationError({"feed_url": "Add the feed address."})

    def next_allowed_check(self):
        """Backs off after failures: 6h, 12h, 24h, capped at 48h."""
        if self.last_checked_at is None:
            return None
        hours = min(self.min_interval_hours * 2 ** self.consecutive_failures, 48)
        return self.last_checked_at + timedelta(hours=hours)


class NewsCategory(ImageRights):
    """Its image illustrates stories with no image of their own."""

    slug = models.SlugField(max_length=40, unique=True)
    position = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "slug"]
        verbose_name_plural = "News categories"

    def __str__(self):
        return self.slug


class NewsCategoryTranslation(Translation):
    parent = models.ForeignKey(NewsCategory, on_delete=models.CASCADE, related_name="translations")
    name = models.CharField(max_length=80)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["parent", "language"], name="news_category_language"),
        ]


class NewsQuerySet(PublishedQuerySet):
    def published(self):
        return self.filter(publication_status=Publishable.Publication.PUBLISHED)


class NewsArticle(Publishable, ImageRights):
    """Publication status: draft is the review queue, archived is rejected."""

    class SourceType(models.TextChoices):
        API = "api", "Publisher API"
        RSS = "rss", "RSS feed"
        EDITORIAL = "editorial", "Editorial entry"

    slug = models.SlugField(max_length=120, unique=True)
    headline = models.CharField(max_length=300)
    summary = models.TextField(
        blank=True, help_text="Your own short factual summary. Never paste the publisher's text.",
    )
    language = models.CharField(max_length=2, choices=LANGUAGES, default="en")
    publisher = models.ForeignKey(NewsSource, on_delete=models.PROTECT, related_name="articles")
    category = models.ForeignKey(
        NewsCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="articles",
    )
    original_url = models.URLField(max_length=700, validators=[validate_https])
    url_hash = models.CharField(max_length=64, unique=True, editable=False)
    title_hash = models.CharField(max_length=64, db_index=True, editable=False)
    published_at = models.DateTimeField()
    retrieved_at = models.DateTimeField(default=timezone.now)
    source_type = models.CharField(max_length=10, choices=SourceType.choices, default=SourceType.EDITORIAL)
    is_featured = models.BooleanField(default=False)
    is_official_announcement = models.BooleanField(
        default=False, help_text="Only for notices from an official publisher.",
    )
    editorial_notes = models.TextField(blank=True, help_text="Internal.")
    attribution = models.CharField(max_length=200, blank=True, help_text="Anything the publisher requires.")

    objects = NewsQuerySet.as_manager()

    class Meta:
        ordering = ["-published_at"]
        indexes = [
            models.Index(fields=["publication_status", "-published_at"]),
            models.Index(fields=["publication_status", "is_official_announcement", "-published_at"]),
            models.Index(fields=["publication_status", "is_featured", "-published_at"]),
        ]

    def __str__(self):
        return self.headline[:80]

    def clean(self):
        super().clean()
        if (
            self.is_official_announcement and self.publisher_id
            and self.publisher.publisher_type != NewsSource.PublisherType.OFFICIAL
        ):
            raise ValidationError({
                "is_official_announcement": "Only an official publisher's story can be an official notice.",
            })

    def save(self, *args, **kwargs):
        self.original_url = canonical_url(self.original_url)
        self.url_hash = hash_of(self.original_url)
        self.title_hash = title_key(self.publisher_id, self.headline)
        if not self.slug:
            self.slug = self.unique_slug()
        super().save(*args, **kwargs)

    def unique_slug(self):
        # Devanagari headlines slugify to nothing, so a hash keeps them unique.
        base = slugify(self.headline)[:100].strip("-") or "story"
        return f"{base}-{self.url_hash[:8]}"

    def publish_problems(self):
        problems = []
        if not self.summary.strip():
            problems.append("write a summary in your own words")
        if self.category_id is None:
            problems.append("choose a category")
        if self.verification_status != self.Verification.AWAITING and not self.last_verified_on:
            problems.append("set the last verified date")
        if (
            self.is_official_announcement
            and self.publisher.publisher_type != NewsSource.PublisherType.OFFICIAL
        ):
            problems.append("an official notice needs an official publisher")
        return problems


class NewsArticleTranslation(Translation):
    """Headline and summary in other languages. The main fields stay the original."""

    parent = models.ForeignKey(NewsArticle, on_delete=models.CASCADE, related_name="translations")
    headline = models.CharField(max_length=300)
    summary = models.TextField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["parent", "language"], name="news_article_language"),
        ]


class NewsSyncLog(models.Model):
    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        NOT_MODIFIED = "not_modified", "No changes"
        FAILED = "failed", "Failed"

    source = models.ForeignKey(NewsSource, on_delete=models.CASCADE, related_name="sync_logs")
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=Status.choices)
    fetched = models.PositiveIntegerField(default=0)
    relevant = models.PositiveIntegerField(default=0)
    created = models.PositiveIntegerField(default=0)
    duplicates = models.PositiveIntegerField(default=0)
    error = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["source", "-started_at"])]

    def __str__(self):
        return f"{self.source} {self.started_at:%Y-%m-%d %H:%M} {self.status}"
