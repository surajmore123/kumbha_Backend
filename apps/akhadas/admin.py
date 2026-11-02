"""
Editorial workflow. A record can go live only with its English text and at
least one source; the publish action and the edit form apply the same check.
"""

from django.contrib import admin, messages
from django.utils import timezone

from apps.akhadas import models


def _languages(obj):
    return ", ".join(sorted(row.language for row in obj.translations.all())) or "—"


_languages.short_description = "Languages"


class PublishableAdmin(admin.ModelAdmin):
    actions = ["publish", "unpublish", "mark_verified_today", "mark_awaiting"]
    filter_horizontal = ("sources",)
    readonly_fields = ("created_at", "updated_at")
    list_filter = ("publication_status", "verification_status")
    list_per_page = 50

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("translations")

    def save_related(self, request, form, formsets, change):
        # Checked here because translations and sources are saved after the
        # record itself.
        super().save_related(request, form, formsets, change)
        obj = form.instance
        if obj.publication_status == obj.Publication.PUBLISHED and (problems := obj.publish_problems()):
            obj.publication_status = obj.Publication.DRAFT
            obj.save(update_fields=["publication_status", "updated_at"])
            self.message_user(
                request, f"{obj} was kept as a draft: {'; '.join(problems)}.", messages.ERROR,
            )

    @admin.action(description="Publish selected")
    def publish(self, request, queryset):
        done = 0
        for obj in queryset:
            if problems := obj.publish_problems():
                self.message_user(request, f"{obj} not published: {'; '.join(problems)}.", messages.ERROR)
                continue
            obj.publication_status = obj.Publication.PUBLISHED
            obj.save(update_fields=["publication_status", "updated_at"])
            done += 1
        if done:
            self.message_user(request, f"Published {done}.", messages.SUCCESS)

    @admin.action(description="Unpublish selected (back to draft)")
    def unpublish(self, request, queryset):
        for obj in queryset:
            obj.publication_status = obj.Publication.DRAFT
            obj.save(update_fields=["publication_status", "updated_at"])

    @admin.action(description="Mark verified today (checked against sources)")
    def mark_verified_today(self, request, queryset):
        for obj in queryset:
            obj.verification_status = obj.Verification.SOURCED
            obj.last_verified_on = timezone.localdate()
            obj.save(update_fields=["verification_status", "last_verified_on", "updated_at"])

    @admin.action(description="Mark awaiting verification")
    def mark_awaiting(self, request, queryset):
        for obj in queryset:
            obj.verification_status = obj.Verification.AWAITING
            obj.save(update_fields=["verification_status", "updated_at"])


class _TranslationInline(admin.StackedInline):
    extra = 0
    max_num = 3


class TraditionTranslationInline(_TranslationInline):
    model = models.TraditionTranslation


class SpiritualTitleTranslationInline(_TranslationInline):
    model = models.SpiritualTitleTranslation


class AkhadaTranslationInline(_TranslationInline):
    model = models.AkhadaTranslation


class SadhuProfileTranslationInline(_TranslationInline):
    model = models.SadhuProfileTranslation


class SpiritualArticleTranslationInline(_TranslationInline):
    model = models.SpiritualArticleTranslation


class AkhadaActivityTranslationInline(_TranslationInline):
    model = models.AkhadaActivityTranslation


@admin.register(models.ContentSource)
class ContentSourceAdmin(admin.ModelAdmin):
    list_display = ("title", "organization", "source_type", "accessed_on", "used_by")
    list_filter = ("source_type",)
    search_fields = ("title", "organization", "url", "verification_notes")
    date_hierarchy = "accessed_on"

    @admin.display(description="Used by")
    def used_by(self, obj):
        return (
            obj.akhada_set.count() + obj.sadhuprofile_set.count()
            + obj.spiritualarticle_set.count() + obj.akhadaactivity_set.count()
        )


@admin.register(models.Tradition)
class TraditionAdmin(admin.ModelAdmin):
    list_display = ("slug", "position", _languages)
    inlines = [TraditionTranslationInline]
    filter_horizontal = ("sources",)
    search_fields = ("slug", "translations__name")


@admin.register(models.SpiritualTitle)
class SpiritualTitleAdmin(admin.ModelAdmin):
    list_display = ("slug", "position", _languages)
    inlines = [SpiritualTitleTranslationInline]
    filter_horizontal = ("sources", "traditions")
    search_fields = ("slug", "translations__name")


@admin.register(models.Akhada)
class AkhadaAdmin(PublishableAdmin):
    list_display = (
        "slug", "tradition", "classification", "publication_status",
        "verification_status", "last_verified_on", _languages,
    )
    list_filter = ("publication_status", "verification_status", "tradition", "classification")
    search_fields = ("slug", "translations__name", "translations__common_name", "headquarters")
    inlines = [AkhadaTranslationInline]


@admin.register(models.SadhuProfile)
class SadhuProfileAdmin(PublishableAdmin):
    list_display = (
        "slug", "era", "akhada", "title", "publication_status",
        "verification_status", "last_verified_on", _languages,
    )
    list_filter = ("publication_status", "verification_status", "era", "akhada", "title")
    search_fields = ("slug", "translations__name")
    autocomplete_fields = ("akhada",)
    inlines = [SadhuProfileTranslationInline]


@admin.register(models.SpiritualArticle)
class SpiritualArticleAdmin(PublishableAdmin):
    list_display = (
        "slug", "category", "is_editorial", "publication_status",
        "verification_status", "last_verified_on", _languages,
    )
    list_filter = ("publication_status", "verification_status", "category", "is_editorial")
    search_fields = ("slug", "translations__title", "translations__body")
    filter_horizontal = ("sources", "related_akhadas", "related_saints")
    inlines = [SpiritualArticleTranslationInline]


@admin.register(models.AkhadaActivity)
class AkhadaActivityAdmin(PublishableAdmin):
    list_display = (
        "slug", "kind", "confirmation", "start_date", "publication_status",
        "verification_status", "last_verified_on", _languages,
    )
    list_filter = ("publication_status", "confirmation", "kind", "akhadas")
    search_fields = ("slug", "translations__title", "translations__location")
    filter_horizontal = ("sources", "akhadas")
    raw_id_fields = ("event",)
    date_hierarchy = "start_date"
    inlines = [AkhadaActivityTranslationInline]
