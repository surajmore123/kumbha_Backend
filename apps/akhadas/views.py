"""
Akhadas & Sadhus public API (all under /api/akhadas/).

Read-only and open without login: this is published reference content with
nothing personal in it. Editing happens only in Django admin. Drafts and
archived records answer 404, the same as records that don't exist.
"""

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.akhadas import serializers
from apps.akhadas.cache import cached_get
from apps.akhadas.models import (
    Akhada,
    AkhadaActivity,
    SadhuProfile,
    SpiritualArticle,
    SpiritualTitle,
    Tradition,
)


def ok(data):
    return Response({"status": "success", "data": data})


def error(errors):
    return Response({"status": "error", "errors": errors}, status=status.HTTP_400_BAD_REQUEST)


class ContentPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50


class _Public(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    http_method_names = ["get", "head", "options"]
    orderings = {}

    def language(self, request):
        value = request.query_params.get("language", "en")
        return value if value in ("en", "hi", "mr") else "en"

    def context(self, request):
        return {"request": request, "language": self.language(request)}

    def ordered(self, request, queryset):
        """(queryset, None), or (None, error response) for an unknown value."""
        value = request.query_params.get("ordering")
        if value is None:
            return queryset, None
        if value not in self.orderings:
            return None, error({"ordering": "Unknown ordering."})
        return queryset.order_by(*self.orderings[value]), None

    def page(self, request, queryset, serializer):
        paginator = ContentPagination()
        items = paginator.paginate_queryset(queryset, request, view=self)
        return ok({
            "count": paginator.page.paginator.count,
            "page": paginator.page.number,
            "num_pages": paginator.page.paginator.num_pages,
            "has_next": paginator.page.has_next(),
            "results": serializer(items, many=True, context=self.context(request)).data,
        })


def _akhadas():
    return Akhada.objects.published().select_related("tradition").prefetch_related(
        "translations", "tradition__translations",
    )


def _saints():
    return SadhuProfile.objects.published().select_related("title", "akhada").prefetch_related(
        "translations", "title__translations", "akhada__translations",
    )


def _articles():
    return SpiritualArticle.objects.published().prefetch_related("translations")


def _activities():
    return AkhadaActivity.objects.published().prefetch_related(
        "translations", "sources", "akhadas", "akhadas__translations",
    )


def _search(queryset, q, *fields):
    condition = Q()
    for field in fields:
        condition |= Q(**{f"translations__{field}__icontains": q})
    return queryset.filter(condition).distinct()


class FiltersAPI(_Public):
    """Choices for the app's filters; only ones with published content."""

    @cached_get
    def get(self, request):
        context = self.context(request)
        published = Akhada.objects.published()
        traditions = Tradition.objects.filter(akhadas__in=published).distinct().prefetch_related("translations")
        titles = SpiritualTitle.objects.filter(
            holders__in=SadhuProfile.objects.published(),
        ).distinct().prefetch_related("translations")
        return ok({
            "traditions": serializers.TraditionSerializer(traditions, many=True, context=context).data,
            "classifications": sorted(set(published.values_list("classification", flat=True))),
            "locations": sorted(set(published.exclude(headquarters="").values_list("headquarters", flat=True))),
            "titles": serializers.TitleSerializer(titles, many=True, context=context).data,
            "saint_akhadas": serializers.AkhadaRefSerializer(
                _akhadas().filter(saints__in=SadhuProfile.objects.published()).distinct(),
                many=True, context=context,
            ).data,
            "article_categories": sorted(set(
                SpiritualArticle.objects.published().values_list("category", flat=True)
            )),
        })


class AkhadaListAPI(_Public):
    """GET ?q= &tradition= &classification= &location= &ordering=position|tradition|-updated"""

    orderings = {
        "position": ["position"],
        "tradition": ["tradition__position", "position"],
        "-updated": ["-updated_at"],
    }

    @cached_get
    def get(self, request):
        params = request.query_params
        queryset = _akhadas()
        if params.get("q", "").strip():
            queryset = _search(queryset, params["q"].strip(), "name", "common_name")
        if params.get("tradition"):
            queryset = queryset.filter(tradition__slug=params["tradition"])
        if params.get("classification"):
            queryset = queryset.filter(classification=params["classification"])
        if params.get("location"):
            queryset = queryset.filter(headquarters=params["location"])
        queryset, problem = self.ordered(request, queryset)
        return problem or self.page(request, queryset, serializers.AkhadaSummarySerializer)


class AkhadaDetailAPI(_Public):
    @cached_get
    def get(self, request, slug):
        akhada = get_object_or_404(_akhadas().prefetch_related("sources"), slug=slug)
        context = self.context(request)
        data = dict(serializers.AkhadaDetailSerializer(akhada, context=context).data)
        titles = SpiritualTitle.objects.filter(
            Q(traditions__isnull=True) | Q(traditions=akhada.tradition),
        ).distinct().prefetch_related("translations")
        data["titles"] = serializers.TitleSerializer(titles, many=True, context=context).data
        data["saints"] = serializers.SaintSummarySerializer(
            _saints().filter(akhada=akhada), many=True, context=context,
        ).data
        data["articles"] = serializers.ArticleSummarySerializer(
            _articles().filter(related_akhadas=akhada), many=True, context=context,
        ).data
        data["activities"] = serializers.ActivitySerializer(
            _activities().filter(akhadas=akhada), many=True, context=context,
        ).data
        return ok(data)


class SaintListAPI(_Public):
    """GET ?q= &akhada= &title= &era= &ordering=position|-updated"""

    orderings = {"position": ["position"], "-updated": ["-updated_at"]}

    @cached_get
    def get(self, request):
        params = request.query_params
        queryset = _saints()
        if params.get("q", "").strip():
            queryset = _search(queryset, params["q"].strip(), "name")
        if params.get("akhada"):
            queryset = queryset.filter(akhada__slug=params["akhada"])
        if params.get("title"):
            queryset = queryset.filter(title__slug=params["title"])
        if params.get("era"):
            queryset = queryset.filter(era=params["era"])
        queryset, problem = self.ordered(request, queryset)
        return problem or self.page(request, queryset, serializers.SaintSummarySerializer)


class SaintDetailAPI(_Public):
    @cached_get
    def get(self, request, slug):
        saint = get_object_or_404(_saints().prefetch_related("sources"), slug=slug)
        context = self.context(request)
        data = dict(serializers.SaintDetailSerializer(saint, context=context).data)
        data["articles"] = serializers.ArticleSummarySerializer(
            _articles().filter(related_saints=saint), many=True, context=context,
        ).data
        return ok(data)


class ArticleListAPI(_Public):
    """GET ?q= &category= &language= &translated=true (only that language)
    &ordering=position|-published"""

    orderings = {"position": ["position"], "-published": ["-published_on", "position"]}

    @cached_get
    def get(self, request):
        params = request.query_params
        queryset = _articles()
        if params.get("q", "").strip():
            queryset = _search(queryset, params["q"].strip(), "title", "intro", "body")
        if params.get("category"):
            queryset = queryset.filter(category=params["category"])
        if params.get("translated") == "true":
            queryset = queryset.filter(translations__language=self.language(request))
        queryset, problem = self.ordered(request, queryset)
        return problem or self.page(request, queryset, serializers.ArticleSummarySerializer)


class ArticleDetailAPI(_Public):
    @cached_get
    def get(self, request, slug):
        article = get_object_or_404(_articles().prefetch_related("sources"), slug=slug)
        context = self.context(request)
        data = dict(serializers.ArticleDetailSerializer(article, context=context).data)
        data["akhadas"] = serializers.AkhadaRefSerializer(
            _akhadas().filter(articles=article), many=True, context=context,
        ).data
        data["saints"] = serializers.SaintSummarySerializer(
            _saints().filter(articles=article), many=True, context=context,
        ).data
        return ok(data)


class ActivityListAPI(_Public):
    """GET ?akhada= &confirmation= &kind= &upcoming=true &ordering=date|-date"""

    orderings = {"date": ["start_date", "slug"], "-date": ["-start_date", "slug"]}

    @cached_get
    def get(self, request):
        params = request.query_params
        queryset = _activities()
        if params.get("akhada"):
            queryset = queryset.filter(akhadas__slug=params["akhada"])
        if params.get("confirmation"):
            queryset = queryset.filter(confirmation=params["confirmation"])
        if params.get("kind"):
            queryset = queryset.filter(kind=params["kind"])
        if params.get("upcoming") == "true":
            today = timezone.localdate()
            queryset = queryset.filter(
                Q(start_date__gte=today) | Q(end_date__gte=today) | Q(start_date__isnull=True),
            ).exclude(confirmation=AkhadaActivity.Confirmation.HISTORICAL)
        queryset, problem = self.ordered(request, queryset)
        return problem or self.page(request, queryset, serializers.ActivitySerializer)
