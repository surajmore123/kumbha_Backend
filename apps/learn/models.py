"""
Learn About Kumbh: a structured library written in Django admin.

Article bodies use a small line-based format, so editors never touch JSON
(see `apps.learn.blocks`). Akhada detail stays in the Akhadas module and temple
detail in Temple Explorer; records here link to them instead of repeating them.
"""

from django.db import models

from apps.akhadas.models import Akhada, ImageRights, Publishable, Translation


def _unique_language(name):
    return models.UniqueConstraint(fields=["parent", "language"], name=f"learn_{name}_language")


class LearningSection(models.Model):
    slug = models.SlugField(max_length=40, unique=True)
    position = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "slug"]

    def __str__(self):
        return self.slug


class LearningSectionTranslation(Translation):
    parent = models.ForeignKey(LearningSection, on_delete=models.CASCADE, related_name="translations")
    name = models.CharField(max_length=100)
    tagline = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [_unique_language("section")]


class LearningArticle(Publishable, ImageRights):
    class Kind(models.TextChoices):
        ARTICLE = "article", "Article"
        GUIDE = "guide", "Pilgrim guide"
        PLACE = "place", "Place"

    slug = models.SlugField(max_length=70, unique=True)
    section = models.ForeignKey(LearningSection, on_delete=models.PROTECT, related_name="articles")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.ARTICLE)
    position = models.PositiveSmallIntegerField(default=0)
    is_featured = models.BooleanField(default=False, help_text="Used as the Learn cover story.")
    is_editorial = models.BooleanField(default=False, help_text="KumbhaPath's own guidance.")
    published_on = models.DateField(null=True, blank=True)
    related_articles = models.ManyToManyField("self", blank=True, symmetrical=True)
    related_akhadas = models.ManyToManyField(Akhada, blank=True, related_name="learning_articles")
    related_temples = models.ManyToManyField("temples.Temple", blank=True, related_name="learning_articles")

    class Meta:
        ordering = ["section__position", "position", "slug"]
        indexes = [models.Index(fields=["publication_status", "kind"])]

    def __str__(self):
        return self.slug


class LearningArticleTranslation(Translation):
    parent = models.ForeignKey(LearningArticle, on_delete=models.CASCADE, related_name="translations")
    title = models.CharField(max_length=200)
    dek = models.CharField(max_length=300, help_text="One line under the title.")
    body = models.TextField(help_text=(
        "One block per paragraph, separated by a blank line. Start a line with: "
        "'## ' heading, '- ' list item, '> ' quote, '!info ' or '!warn ' callout, "
        "'[[image:key]]' for an image added below."
    ))

    class Meta:
        constraints = [_unique_language("article")]


class LearningImage(ImageRights):
    """An image placed inside an article with [[image:key]]."""

    article = models.ForeignKey(LearningArticle, on_delete=models.CASCADE, related_name="images")
    key = models.SlugField(max_length=40)
    caption = models.CharField(max_length=200, blank=True)
    caption_hi = models.CharField(max_length=200, blank=True)
    caption_mr = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["article", "key"], name="learn_image_key"),
        ]

    def __str__(self):
        return self.key


class GlossaryTerm(Publishable):
    slug = models.SlugField(max_length=50, unique=True)
    position = models.PositiveSmallIntegerField(default=0)
    related_articles = models.ManyToManyField(LearningArticle, blank=True, related_name="glossary_terms")
    related_akhadas = models.ManyToManyField(Akhada, blank=True, related_name="glossary_terms")
    related_temples = models.ManyToManyField("temples.Temple", blank=True, related_name="glossary_terms")

    class Meta:
        ordering = ["position", "slug"]

    def __str__(self):
        return self.slug


class GlossaryTermTranslation(Translation):
    parent = models.ForeignKey(GlossaryTerm, on_delete=models.CASCADE, related_name="translations")
    term = models.CharField(max_length=80)
    simple = models.CharField(max_length=250, help_text="One plain sentence.")
    detail = models.TextField(blank=True)

    class Meta:
        constraints = [_unique_language("term")]
