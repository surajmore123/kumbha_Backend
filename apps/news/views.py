"""
Kumbh news public API (all under /api/news/). Read-only and open without login,
like the Akhadas directory: published stories with nothing personal in them.
Only published stories appear; the review queue never leaves admin.
"""

from datetime import date

from django.db.models import Case, IntegerField, Q, Value, When
from django.shortcuts import get_object_or_404

from apps.akhadas.cache import cached_get
from apps.akhadas.views import _Public, error, ok
from apps.news import serializers
from apps.news.models import NewsArticle, NewsCategory, NewsSource

_HOME_LATEST = 16


def _stories():
    return NewsArticle.objects.published().select_related("publisher", "category").prefetch_related(
        "translations", "category__translations",
    )


def _categories():
    return NewsCategory.objects.filter(
        is_active=True, articles__publication_status=NewsArticle.Publication.PUBLISHED,
    ).distinct().prefetch_related("translations")


def _publishers():
    return NewsSource.objects.filter(
        articles__publication_status=NewsArticle.Publication.PUBLISHED,
    ).distinct()


class HomeAPI(_Public):
    """The front page: lead story, official notices, latest stories, filters."""

    @cached_get
    def get(self, request):
        context = self.context(request)
        summary = serializers.ArticleSummarySerializer
        stories = _stories()
        lead = stories.filter(is_featured=True).first() or stories.first()
        notices = stories.filter(is_official_announcement=True)[:3]
        latest = stories.exclude(pk=lead.pk) if lead else stories
        latest = latest.exclude(pk__in=[n.pk for n in notices])[:_HOME_LATEST]
        return ok({
            "lead": summary(lead, context=context).data if lead else None,
            "announcements": summary(notices, many=True, context=context).data,
            "latest": summary(latest, many=True, context=context).data,
            "categories": serializers.CategorySerializer(_categories(), many=True, context=context).data,
            "publishers": serializers.PublisherSerializer(_publishers(), many=True).data,
        })


class ArticleListAPI(_Public):
    """GET ?q= &category= &publisher= &date_from= &date_to= &ordering=latest|relevant
    &official=true"""

    @cached_get
    def get(self, request):
        params = request.query_params
        queryset = _stories()
        q = params.get("q", "").strip()
        if q:
            queryset = queryset.filter(
                Q(headline__icontains=q) | Q(summary__icontains=q)
                | Q(translations__headline__icontains=q) | Q(translations__summary__icontains=q),
            ).distinct()
        if params.get("category"):
            queryset = queryset.filter(category__slug=params["category"])
        if params.get("publisher"):
            queryset = queryset.filter(publisher__slug=params["publisher"])
        if params.get("official") == "true":
            queryset = queryset.filter(is_official_announcement=True)
        for name, lookup in (("date_from", "gte"), ("date_to", "lte")):
            if params.get(name):
                try:
                    day = date.fromisoformat(params[name])
                except ValueError:
                    return error({name: "Use YYYY-MM-DD."})
                queryset = queryset.filter(**{f"published_at__date__{lookup}": day})
        ordering = params.get("ordering", "latest")
        if ordering not in ("latest", "relevant"):
            return error({"ordering": "Unknown ordering."})
        if ordering == "relevant" and q:
            queryset = queryset.annotate(rank=Case(
                When(Q(headline__icontains=q) | Q(translations__headline__icontains=q), then=Value(1)),
                default=Value(0), output_field=IntegerField(),
            )).order_by("-rank", "-published_at")
        return self.page(request, queryset, serializers.ArticleSummarySerializer)


class ArticleDetailAPI(_Public):
    @cached_get
    def get(self, request, slug):
        story = get_object_or_404(_stories(), slug=slug)
        context = self.context(request)
        data = dict(serializers.ArticleDetailSerializer(story, context=context).data)
        related = _stories().filter(category=story.category).exclude(pk=story.pk)[:4]
        data["related"] = serializers.ArticleSummarySerializer(related, many=True, context=context).data
        return ok(data)
