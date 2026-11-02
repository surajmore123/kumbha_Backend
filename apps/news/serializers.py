from rest_framework import serializers

from apps.akhadas.serializers import image_of
from apps.news.models import NewsArticle, NewsCategory, NewsSource


def _translated(obj, language):
    return next((row for row in obj.translations.all() if row.language == language), None)


class CategorySerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = NewsCategory
        fields = ["slug", "name"]

    def get_name(self, obj):
        language = self.context.get("language", "en")
        row = _translated(obj, language) or _translated(obj, "en")
        return row.name if row else obj.slug


class PublisherSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsSource
        fields = ["slug", "name", "publisher_type", "website_url"]


class ArticleSummarySerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    publisher = PublisherSerializer(read_only=True)
    headline = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()
    content_language = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()

    class Meta:
        model = NewsArticle
        fields = [
            "slug", "headline", "summary", "content_language", "category", "publisher",
            "image", "published_at", "is_featured", "is_official_announcement",
            "verification_status", "last_verified_on", "original_url",
        ]

    def _row(self, obj):
        language = self.context.get("language", "en")
        return None if language == obj.language else _translated(obj, language)

    def get_headline(self, obj):
        row = self._row(obj)
        return row.headline if row else obj.headline

    def get_summary(self, obj):
        row = self._row(obj)
        return row.summary if row else obj.summary

    def get_content_language(self, obj):
        row = self._row(obj)
        return row.language if row else obj.language

    def get_image(self, obj):
        """The story's own image, else its category's. A category image only
        illustrates the topic, so the app labels it."""
        request = self.context.get("request")
        own = image_of(obj, request)
        if own:
            return own
        fallback = image_of(obj.category, request) if obj.category else None
        return {**fallback, "representative": True} if fallback else None


class ArticleDetailSerializer(ArticleSummarySerializer):
    class Meta(ArticleSummarySerializer.Meta):
        fields = ArticleSummarySerializer.Meta.fields + ["attribution", "retrieved_at"]
