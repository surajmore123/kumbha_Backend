from django.contrib import admin

from apps.akhadas.admin import PublishableAdmin, _languages
from apps.learn import models


class SectionTranslationInline(admin.TabularInline):
    model = models.LearningSectionTranslation
    extra = 0
    max_num = 3


class ArticleTranslationInline(admin.StackedInline):
    model = models.LearningArticleTranslation
    extra = 0
    max_num = 3


class ArticleImageInline(admin.StackedInline):
    model = models.LearningImage
    extra = 0


class TermTranslationInline(admin.StackedInline):
    model = models.GlossaryTermTranslation
    extra = 0
    max_num = 3


@admin.register(models.LearningSection)
class LearningSectionAdmin(admin.ModelAdmin):
    list_display = ("slug", "position", _languages)
    list_editable = ("position",)
    inlines = [SectionTranslationInline]


@admin.register(models.LearningArticle)
class LearningArticleAdmin(PublishableAdmin):
    list_display = (
        "slug", "section", "kind", "is_featured", "publication_status",
        "verification_status", "last_verified_on", _languages,
    )
    list_filter = ("publication_status", "verification_status", "section", "kind", "is_featured", "is_editorial")
    search_fields = ("slug", "translations__title", "translations__body")
    filter_horizontal = ("sources", "related_articles", "related_akhadas", "related_temples")
    inlines = [ArticleTranslationInline, ArticleImageInline]


@admin.register(models.GlossaryTerm)
class GlossaryTermAdmin(PublishableAdmin):
    list_display = ("slug", "position", "publication_status", "verification_status", _languages)
    search_fields = ("slug", "translations__term", "translations__simple")
    filter_horizontal = ("sources", "related_articles", "related_akhadas", "related_temples")
    inlines = [TermTranslationInline]
