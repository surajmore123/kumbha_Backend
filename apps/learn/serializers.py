from rest_framework import serializers

from apps.akhadas.models import Akhada
from apps.akhadas.serializers import (
    AkhadaRefSerializer,
    ImageMixin,
    LocalizedSerializer,
    SourceSerializer,
    image_of,
    pick_translation,
)
from apps.learn import models
from apps.learn.blocks import parse_blocks, reading_minutes
from apps.temples.models import Temple


class SectionSerializer(LocalizedSerializer):
    translated = ("name", "tagline")

    class Meta:
        model = models.LearningSection
        fields = ["slug"]


class TempleLinkSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="temple_id")

    class Meta:
        model = Temple
        fields = ["id", "name", "city"]


class ArticleSummarySerializer(ImageMixin, LocalizedSerializer):
    translated = ("title", "dek")
    section = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    reading_minutes = serializers.SerializerMethodField()

    class Meta:
        model = models.LearningArticle
        fields = [
            "slug", "section", "kind", "is_featured", "is_editorial", "image",
            "reading_minutes", "verification_status", "last_verified_on", "published_on",
        ]

    def get_reading_minutes(self, obj):
        row = pick_translation(obj, self.context.get("language", "en"))
        return reading_minutes(row.body) if row else 1


class ArticleDetailSerializer(ArticleSummarySerializer):
    blocks = serializers.SerializerMethodField()
    sources = SourceSerializer(many=True, read_only=True)
    available_languages = serializers.SerializerMethodField()
    akhadas = serializers.SerializerMethodField()
    temples = serializers.SerializerMethodField()

    class Meta(ArticleSummarySerializer.Meta):
        fields = ArticleSummarySerializer.Meta.fields + [
            "blocks", "sources", "available_languages", "akhadas", "temples",
        ]

    def get_available_languages(self, obj):
        return sorted(row.language for row in obj.translations.all())

    def get_blocks(self, obj):
        language = self.context.get("language", "en")
        request = self.context.get("request")
        row = pick_translation(obj, language)
        images = {image.key: image for image in obj.images.all()}
        blocks = []
        for block in parse_blocks(row.body if row else ""):
            if block["type"] != "image":
                blocks.append(block)
                continue
            # A key with no image, or an image without rights, simply drops out.
            image = images.get(block["key"])
            shown = image_of(image, request) if image else None
            if shown:
                caption = getattr(image, f"caption_{language}", "") or image.caption
                blocks.append({"type": "image", "image": shown, "caption": caption})
        return blocks

    def get_akhadas(self, obj):
        published = Akhada.objects.published().filter(learning_articles=obj).prefetch_related("translations")
        return AkhadaRefSerializer(published, many=True, context=self.context).data

    def get_temples(self, obj):
        temples = obj.related_temples.filter(is_active=True, del_flag=0)
        return TempleLinkSerializer(temples, many=True).data


class TermSummarySerializer(LocalizedSerializer):
    translated = ("term", "simple")

    class Meta:
        model = models.GlossaryTerm
        fields = ["slug"]


class TermDetailSerializer(TermSummarySerializer):
    translated = ("term", "simple", "detail")
    articles = serializers.SerializerMethodField()
    akhadas = serializers.SerializerMethodField()
    temples = serializers.SerializerMethodField()
    sources = SourceSerializer(many=True, read_only=True)

    class Meta(TermSummarySerializer.Meta):
        fields = TermSummarySerializer.Meta.fields + ["articles", "akhadas", "temples", "sources"]

    def get_articles(self, obj):
        articles = models.LearningArticle.objects.published().filter(glossary_terms=obj).select_related(
            "section",
        ).prefetch_related("translations")
        return ArticleSummarySerializer(articles, many=True, context=self.context).data

    def get_akhadas(self, obj):
        published = Akhada.objects.published().filter(glossary_terms=obj).prefetch_related("translations")
        return AkhadaRefSerializer(published, many=True, context=self.context).data

    def get_temples(self, obj):
        temples = obj.related_temples.filter(is_active=True, del_flag=0)
        return TempleLinkSerializer(temples, many=True).data
