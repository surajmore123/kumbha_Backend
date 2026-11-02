"""
Loads the starting Akhadas content.

Safe to run again: it only adds records whose slug doesn't exist yet, so
anything edited in admin is left alone. Records load as drafts unless
--publish is given, so editors can review them first.
"""

import json
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.akhadas import models, seed_articles, seed_directory

_LANGUAGES = ("en", "hi", "mr")
_IMAGES = Path(__file__).resolve().parents[2] / "seed_images"
_IMAGE_MODELS = {
    "akhada": models.Akhada, "tradition": models.Tradition,
    "saint": models.SadhuProfile, "article": models.SpiritualArticle,
}


class Command(BaseCommand):
    help = "Load the sourced starting content for Akhadas & Sadhus."

    def add_arguments(self, parser):
        parser.add_argument("--publish", action="store_true", help="Publish instead of leaving drafts.")

    @transaction.atomic
    def handle(self, *args, **options):
        self.publication = (
            models.Publishable.Publication.PUBLISHED if options["publish"]
            else models.Publishable.Publication.DRAFT
        )
        self.sources = self._load_sources()
        traditions = self._load_plain(models.Tradition, models.TraditionTranslation, seed_directory.TRADITIONS)
        self._load_plain(models.SpiritualTitle, models.SpiritualTitleTranslation, seed_directory.TITLES)
        akhadas = self._load(models.Akhada, models.AkhadaTranslation, seed_directory.AKHADAS, traditions=traditions)
        saints = self._load(models.SadhuProfile, models.SadhuProfileTranslation, seed_directory.SAINTS)
        articles = self._load(models.SpiritualArticle, models.SpiritualArticleTranslation, seed_articles.ARTICLES)
        activities = self._load(models.AkhadaActivity, models.AkhadaActivityTranslation, seed_articles.ACTIVITIES)
        images = self._attach_images()
        self.stdout.write(self.style.SUCCESS(
            f"Added {len(akhadas)} Akhadas, {len(saints)} profiles, {len(articles)} articles, "
            f"{len(activities)} activities ({self.publication}), {images} images."
        ))

    def _attach_images(self):
        """Adds reviewed images to records without one; never replaces an image."""
        added = 0
        for entry in json.loads((_IMAGES / "manifest.json").read_text(encoding="utf-8")):
            obj = _IMAGE_MODELS[entry["kind"]].objects.filter(slug=entry["slug"]).first()
            if obj is None or obj.image:
                continue
            obj.image_usage = entry["usage"]
            obj.image_credit = entry["credit"]
            obj.image_source_url = entry["source_url"]
            with (_IMAGES / entry["file"]).open("rb") as image:
                obj.image.save(entry["file"], File(image), save=True)
            added += 1
        return added

    def _load_sources(self):
        loaded = {}
        for key, data in seed_directory.SOURCES.items():
            values = {**data, "accessed_on": seed_directory.ACCESSED}
            loaded[key], _ = models.ContentSource.objects.get_or_create(
                title=values.pop("title"), url=values.pop("url"), defaults=values,
            )
        return loaded

    def _texts(self, translation_model, parent, item):
        for language in _LANGUAGES:
            translation_model.objects.create(parent=parent, language=language, **item[language])

    def _load_plain(self, model, translation_model, items):
        """Traditions and titles: reference lists, no publishing state."""
        loaded = {}
        for position, item in enumerate(items, start=1):
            obj, created = model.objects.get_or_create(slug=item["slug"], defaults={"position": position})
            loaded[item["slug"]] = obj
            if created:
                obj.sources.set(self.sources[key] for key in item["sources"])
                self._texts(translation_model, obj, item)
        return loaded

    def _load(self, model, translation_model, items, traditions=None):
        added = {}
        for item in items:
            if model.objects.filter(slug=item["slug"]).exists():
                continue
            fields = {
                key: value for key, value in item.items()
                if key not in (*_LANGUAGES, "sources", "tradition", "akhada", "title", "akhadas", "saints")
            }
            if model is models.Akhada:
                fields["tradition"] = traditions[item["tradition"]]
            if model is models.SadhuProfile:
                fields["akhada"] = models.Akhada.objects.filter(slug=item.get("akhada")).first()
                fields["title"] = models.SpiritualTitle.objects.filter(slug=item.get("title")).first()
            if model is models.SpiritualArticle:
                fields["published_on"] = seed_directory.ACCESSED
            verified = (
                models.Publishable.Verification.AWAITING if item.get("confirmation") == "awaiting"
                else models.Publishable.Verification.SOURCED
            )
            obj = model.objects.create(
                publication_status=self.publication, verification_status=verified,
                last_verified_on=seed_directory.ACCESSED, **fields,
            )
            obj.sources.set(self.sources[key] for key in item["sources"])
            self._texts(translation_model, obj, item)
            if model is models.SpiritualArticle:
                obj.related_akhadas.set(models.Akhada.objects.filter(slug__in=item.get("akhadas", ())))
                obj.related_saints.set(models.SadhuProfile.objects.filter(slug__in=item.get("saints", ())))
            if model is models.AkhadaActivity:
                obj.akhadas.set(models.Akhada.objects.filter(slug__in=item.get("akhadas", ())))
            added[item["slug"]] = obj
        return added
