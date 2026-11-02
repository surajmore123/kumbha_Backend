from rest_framework import serializers

from apps.akhadas import models


def pick_translation(obj, language):
    """The requested language, else English. Uses prefetched rows."""
    rows = {row.language: row for row in obj.translations.all()}
    return rows.get(language) or rows.get("en")


class LocalizedSerializer(serializers.ModelSerializer):
    """Adds the `translated` fields in the requested language, and
    `content_language` so the app can say when it fell back to English."""

    translated = ()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        row = pick_translation(instance, self.context.get("language", "en"))
        for field in self.translated:
            data[field] = getattr(row, field, "") if row else ""
        data["content_language"] = row.language if row else None
        return data


def image_of(obj, request):
    """Only images with a recorded usage basis and credit are ever exposed."""
    if not (obj.image and obj.image_usage and obj.image_credit):
        return None
    url = obj.image.url
    return {
        "url": request.build_absolute_uri(url) if request else url,
        "credit": obj.image_credit,
        "source_url": obj.image_source_url or None,
        "representative": False,
    }


class ImageMixin(serializers.Serializer):
    image = serializers.SerializerMethodField()

    def get_image(self, obj):
        return image_of(obj, self.context.get("request"))


class SourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ContentSource
        fields = ["title", "url", "organization", "source_type", "published_on", "accessed_on"]


class TraditionSerializer(LocalizedSerializer):
    translated = ("name", "summary")

    class Meta:
        model = models.Tradition
        fields = ["slug"]


class TraditionDetailSerializer(TraditionSerializer):
    translated = ("name", "summary", "philosophy", "practices")


class TitleSerializer(LocalizedSerializer):
    translated = ("name", "meaning")

    class Meta:
        model = models.SpiritualTitle
        fields = ["slug"]


class AkhadaRefSerializer(LocalizedSerializer):
    translated = ("name", "common_name")

    class Meta:
        model = models.Akhada
        fields = ["slug"]


class AkhadaSummarySerializer(ImageMixin, LocalizedSerializer):
    translated = ("name", "common_name", "summary")
    tradition = TraditionSerializer(read_only=True)

    class Meta:
        model = models.Akhada
        fields = [
            "slug", "tradition", "classification", "headquarters", "image",
            "verification_status", "last_verified_on",
        ]

    def get_image(self, obj):
        own = super().get_image(obj)
        if own:
            return own
        # Never presented as this Akhada's own: the app labels it.
        fallback = image_of(obj.tradition, self.context.get("request"))
        return {**fallback, "representative": True} if fallback else None


class SaintSummarySerializer(ImageMixin, LocalizedSerializer):
    translated = ("name",)
    title = TitleSerializer(read_only=True)
    akhada = serializers.SerializerMethodField()

    class Meta:
        model = models.SadhuProfile
        fields = ["slug", "era", "title", "akhada", "image", "verification_status", "last_verified_on"]

    def get_akhada(self, obj):
        # A draft Akhada stays hidden even when a published profile names it.
        if obj.akhada is None or obj.akhada.publication_status != models.Publishable.Publication.PUBLISHED:
            return None
        return AkhadaRefSerializer(obj.akhada, context=self.context).data


class ArticleSummarySerializer(ImageMixin, LocalizedSerializer):
    translated = ("title", "intro")

    class Meta:
        model = models.SpiritualArticle
        fields = [
            "slug", "category", "is_editorial", "image", "verification_status",
            "last_verified_on", "published_on",
        ]


class ActivitySerializer(LocalizedSerializer):
    translated = ("title", "description", "location")
    akhadas = serializers.SerializerMethodField()
    sources = SourceSerializer(many=True, read_only=True)

    class Meta:
        model = models.AkhadaActivity
        fields = [
            "slug", "kind", "confirmation", "akhadas", "event", "start_date", "end_date",
            "verification_status", "last_verified_on", "sources",
        ]

    def get_akhadas(self, obj):
        visible = [
            a for a in obj.akhadas.all()
            if a.publication_status == models.Publishable.Publication.PUBLISHED
        ]
        return AkhadaRefSerializer(visible, many=True, context=self.context).data


class AkhadaDetailSerializer(AkhadaSummarySerializer):
    translated = AkhadaSummarySerializer.translated + (
        "history", "philosophy", "practices", "organization", "kumbh_significance", "nashik_note",
    )
    tradition = TraditionDetailSerializer(read_only=True)
    sources = SourceSerializer(many=True, read_only=True)

    class Meta(AkhadaSummarySerializer.Meta):
        fields = AkhadaSummarySerializer.Meta.fields + [
            "website_url", "social_url", "contact_email", "contact_phone", "sources",
        ]


class SaintDetailSerializer(SaintSummarySerializer):
    translated = SaintSummarySerializer.translated + (
        "biography", "teachings", "public_activities", "significance",
    )
    sources = SourceSerializer(many=True, read_only=True)

    class Meta(SaintSummarySerializer.Meta):
        fields = SaintSummarySerializer.Meta.fields + ["website_url", "social_url", "sources"]


class ArticleDetailSerializer(ArticleSummarySerializer):
    translated = ArticleSummarySerializer.translated + ("body",)
    sources = SourceSerializer(many=True, read_only=True)
    available_languages = serializers.SerializerMethodField()

    class Meta(ArticleSummarySerializer.Meta):
        fields = ArticleSummarySerializer.Meta.fields + ["sources", "available_languages"]

    def get_available_languages(self, obj):
        return sorted(row.language for row in obj.translations.all())
