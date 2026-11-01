"""
Loads the starting news and Learn content. Adds only what's missing, so admin
edits are left alone. Stays in draft unless --publish is given.
"""

import json
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.akhadas.models import Akhada, ContentSource, Publishable
from apps.learn import models as learn, seed_content as learn_seed
from apps.news import models as news, seed_content as news_seed
from apps.temples.models import Temple

_IMAGES = Path(__file__).resolve().parents[2] / "seed_images"
_LANGUAGES = ("en", "hi", "mr")


class Command(BaseCommand):
    help = "Load sourced starting content for News and Learn."

    def add_arguments(self, parser):
        parser.add_argument("--publish", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        self.publication = (
            Publishable.Publication.PUBLISHED if options["publish"] else Publishable.Publication.DRAFT
        )
        self.images = {
            e["key"]: e for e in json.loads((_IMAGES / "manifest.json").read_text(encoding="utf-8"))
        }
        stories = self._news()
        articles, terms = self._learn()
        self.stdout.write(self.style.SUCCESS(
            f"Added {stories} stories, {articles} articles, {terms} terms ({self.publication}).",
        ))

    def _attach(self, obj, key):
        if key is None or obj.image:
            return
        entry = self.images[key]
        obj.image_usage = entry["usage"]
        obj.image_credit = entry["credit"]
        obj.image_source_url = entry["source_url"]
        with (_IMAGES / entry["file"]).open("rb") as image:
            obj.image.save(entry["file"], File(image), save=True)

    def _news(self):
        category_images = {
            "spiritual": "nirmal-shahi", "dates": "ramkund-sankranti", "transport": "trimbakeshwar-mist",
            "infrastructure": "ramkund-works", "preparations": "ramkund-works",
            "environment": "ramkund-sankranti", "heritage": "kalaram", "facilities": "sadhus-nashik",
        }
        categories = {}
        for position, (slug, en, hi, mr) in enumerate(news_seed.CATEGORIES, start=1):
            category, created = news.NewsCategory.objects.get_or_create(slug=slug, defaults={"position": position})
            categories[slug] = category
            if created:
                for language, name in zip(_LANGUAGES, (en, hi, mr)):
                    news.NewsCategoryTranslation.objects.create(parent=category, language=language, name=name)
            self._attach(category, category_images.get(slug))
        publishers = {}
        for data in news_seed.SOURCES:
            publisher, _ = news.NewsSource.objects.get_or_create(slug=data["slug"], defaults=data)
            publishers[data["slug"]] = publisher
        added = 0
        for item in news_seed.STORIES:
            url_hash = news.hash_of(news.canonical_url(item["url"]))
            if news.NewsArticle.objects.filter(url_hash=url_hash).exists():
                continue
            headline, summary = item["en"]
            story = news.NewsArticle.objects.create(
                headline=headline, summary=summary, language="en", publisher=publishers[item["publisher"]],
                category=categories[item["category"]], original_url=item["url"],
                published_at=item["published_at"], is_featured=item.get("featured", False),
                publication_status=self.publication, verification_status=Publishable.Verification.SOURCED,
                last_verified_on=learn_seed.CHECKED,
            )
            for language in ("hi", "mr"):
                headline, summary = item[language]
                news.NewsArticleTranslation.objects.create(
                    parent=story, language=language, headline=headline, summary=summary,
                )
            added += 1
        return added

    def _learn(self):
        sources = {}
        for key, data in learn_seed.SOURCES.items():
            values = {**data, "accessed_on": learn_seed.CHECKED}
            sources[key], _ = ContentSource.objects.get_or_create(
                title=values.pop("title"), url=values.pop("url"), defaults=values,
            )
        sections = {}
        for position, (slug, en, hi, mr, t_en, t_hi, t_mr) in enumerate(learn_seed.SECTIONS, start=1):
            section, created = learn.LearningSection.objects.get_or_create(slug=slug, defaults={"position": position})
            sections[slug] = section
            if created:
                for language, name, tagline in zip(_LANGUAGES, (en, hi, mr), (t_en, t_hi, t_mr)):
                    learn.LearningSectionTranslation.objects.create(
                        parent=section, language=language, name=name, tagline=tagline,
                    )
        added = 0
        for position, item in enumerate(learn_seed.ARTICLES, start=1):
            if learn.LearningArticle.objects.filter(slug=item["slug"]).exists():
                continue
            article = learn.LearningArticle.objects.create(
                slug=item["slug"], section=sections[item["section"]], kind=item.get("kind", "article"),
                position=position, is_featured=item.get("featured", False),
                is_editorial=item.get("editorial", False), published_on=learn_seed.CHECKED,
                publication_status=self.publication, last_verified_on=learn_seed.CHECKED,
                verification_status=(
                    Publishable.Verification.AWAITING if item.get("unverified") else Publishable.Verification.SOURCED
                ),
            )
            article.sources.set(sources[key] for key in item["sources"])
            for language in _LANGUAGES:
                title, dek, body = item[language]
                learn.LearningArticleTranslation.objects.create(
                    parent=article, language=language, title=title, dek=dek, body=body,
                )
            article.related_akhadas.set(Akhada.objects.filter(slug__in=item.get("akhadas", ())))
            for name in item.get("temples", ()):
                article.related_temples.add(*Temple.objects.filter(name__icontains=name, is_active=True))
            self._attach(article, item["cover"])
            for key, (image_key, en, hi, mr) in item.get("images", {}).items():
                image = learn.LearningImage(article=article, key=key, caption=en, caption_hi=hi, caption_mr=mr)
                self._attach(image, image_key)
            added += 1
        terms = 0
        for position, (slug, article_slugs, akhada_slugs, en, hi, mr) in enumerate(learn_seed.GLOSSARY, start=1):
            if learn.GlossaryTerm.objects.filter(slug=slug).exists():
                continue
            term = learn.GlossaryTerm.objects.create(
                slug=slug, position=position, publication_status=self.publication,
                verification_status=Publishable.Verification.SOURCED, last_verified_on=learn_seed.CHECKED,
            )
            term.sources.add(sources["nashik_gov"])
            for language, (word, simple, detail) in zip(_LANGUAGES, (en, hi, mr)):
                learn.GlossaryTermTranslation.objects.create(
                    parent=term, language=language, term=word, simple=simple, detail=detail,
                )
            term.related_articles.set(learn.LearningArticle.objects.filter(slug__in=article_slugs))
            term.related_akhadas.set(Akhada.objects.filter(slug__in=akhada_slugs))
            terms += 1
        return added, terms
