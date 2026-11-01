from django.contrib import admin, messages

from apps.akhadas.admin import PublishableAdmin
from apps.news import models
from apps.news.sync import sync_source


class NewsCategoryTranslationInline(admin.TabularInline):
    model = models.NewsCategoryTranslation
    extra = 0
    max_num = 3


class NewsArticleTranslationInline(admin.StackedInline):
    model = models.NewsArticleTranslation
    extra = 0
    max_num = 3


@admin.register(models.NewsCategory)
class NewsCategoryAdmin(admin.ModelAdmin):
    list_display = ("slug", "position", "is_active")
    list_editable = ("position", "is_active")
    inlines = [NewsCategoryTranslationInline]


@admin.register(models.NewsSource)
class NewsSourceAdmin(admin.ModelAdmin):
    list_display = (
        "name", "publisher_type", "adapter", "is_active", "last_success_at",
        "consecutive_failures", "last_error",
    )
    list_filter = ("publisher_type", "adapter", "is_active")
    search_fields = ("name", "feed_url")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("last_checked_at", "last_success_at", "consecutive_failures", "last_error")
    actions = ["sync_now"]

    @admin.action(description="Sync selected now (respects nothing but the feed's own limits)")
    def sync_now(self, request, queryset):
        for source in queryset.exclude(adapter="manual"):
            log = sync_source(source, force=True)
            level = messages.ERROR if log.status == "failed" else messages.SUCCESS
            self.message_user(
                request,
                f"{source}: {log.get_status_display()}, {log.created} new, {log.duplicates} duplicates. {log.error}",
                level,
            )


@admin.register(models.NewsArticle)
class NewsArticleAdmin(PublishableAdmin):
    list_display = (
        "headline", "publisher", "category", "published_at", "publication_status",
        "is_featured", "is_official_announcement", "source_type",
    )
    list_filter = (
        "publication_status", "verification_status", "category", "publisher",
        "is_official_announcement", "is_featured", "source_type",
    )
    search_fields = ("headline", "summary", "original_url", "editorial_notes")
    date_hierarchy = "published_at"
    readonly_fields = ("created_at", "updated_at", "retrieved_at", "source_type")
    exclude = ("sources",)
    filter_horizontal = ()
    inlines = [NewsArticleTranslationInline]
    list_select_related = ("publisher", "category")

    def get_changeform_initial_data(self, request):
        return {"verification_status": "sourced", **super().get_changeform_initial_data(request)}


@admin.register(models.NewsSyncLog)
class NewsSyncLogAdmin(admin.ModelAdmin):
    list_display = ("source", "started_at", "status", "fetched", "relevant", "created", "duplicates", "error")
    list_filter = ("status", "source")
    date_hierarchy = "started_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
