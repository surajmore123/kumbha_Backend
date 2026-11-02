"""Learn About Kumbh public API (all under /api/learn/). Read-only, no login."""

from django.db.models import Q
from django.shortcuts import get_object_or_404

from apps.akhadas.cache import cached_get
from apps.akhadas.views import _Public, _search, ok
from apps.learn import serializers
from apps.learn.models import GlossaryTerm, LearningArticle, LearningSection


def _articles():
    return LearningArticle.objects.published().select_related("section").prefetch_related("translations")


def _terms():
    return GlossaryTerm.objects.published().prefetch_related("translations")


class HomeAPI(_Public):
    """The library: cover story, sections with their articles, a glossary term."""

    @cached_get
    def get(self, request):
        context = self.context(request)
        summary = serializers.ArticleSummarySerializer
        articles = list(_articles())
        cover = next((a for a in articles if a.is_featured), articles[0] if articles else None)
        sections = []
        for section in LearningSection.objects.prefetch_related("translations"):
            members = [a for a in articles if a.section_id == section.pk]
            if members:
                sections.append({
                    **serializers.SectionSerializer(section, context=context).data,
                    "articles": summary(members, many=True, context=context).data,
                })
        term = _terms().first()
        return ok({
            "cover": summary(cover, context=context).data if cover else None,
            "sections": sections,
            "term": serializers.TermSummarySerializer(term, context=context).data if term else None,
        })


class ArticleListAPI(_Public):
    """GET ?q= &section= &kind= &translated=true"""

    @cached_get
    def get(self, request):
        params = request.query_params
        queryset = _articles()
        if params.get("q", "").strip():
            queryset = _search(queryset, params["q"].strip(), "title", "dek", "body")
        if params.get("section"):
            queryset = queryset.filter(section__slug=params["section"])
        if params.get("kind"):
            queryset = queryset.filter(kind=params["kind"])
        if params.get("translated") == "true":
            queryset = queryset.filter(translations__language=self.language(request))
        return self.page(request, queryset, serializers.ArticleSummarySerializer)


class ArticleDetailAPI(_Public):
    @cached_get
    def get(self, request, slug):
        article = get_object_or_404(_articles().prefetch_related("sources", "images"), slug=slug)
        context = self.context(request)
        data = dict(serializers.ArticleDetailSerializer(article, context=context).data)
        related = _articles().filter(related_articles=article)
        if not related.exists():
            related = _articles().filter(section=article.section).exclude(pk=article.pk)
        data["related"] = serializers.ArticleSummarySerializer(related[:4], many=True, context=context).data
        return ok(data)


class GlossaryListAPI(_Public):
    """GET ?q= (matches a term or meaning in any language)"""

    @cached_get
    def get(self, request):
        queryset = _terms()
        q = request.query_params.get("q", "").strip()
        if q:
            queryset = queryset.filter(
                Q(translations__term__icontains=q) | Q(translations__simple__icontains=q),
            ).distinct()
        return self.page(request, queryset, serializers.TermSummarySerializer)


class GlossaryDetailAPI(_Public):
    @cached_get
    def get(self, request, slug):
        term = get_object_or_404(_terms().prefetch_related("sources"), slug=slug)
        return ok(serializers.TermDetailSerializer(term, context=self.context(request)).data)
