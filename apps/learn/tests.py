from io import StringIO
from tempfile import TemporaryDirectory

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.akhadas.models import Akhada, ContentSource, Tradition
from apps.learn import models, seed_content
from apps.learn.blocks import parse_blocks, reading_minutes
from apps.news.models import NewsArticle, NewsCategory
from apps.temples.models import Temple

BASE = "/api/learn/"


class BlockTests(TestCase):
    def test_every_block_type(self):
        body = (
            "Intro line\nsecond line\n\n## Heading\n\n- one\n- two\n\n> A quote\n\n"
            "!info Know this\n\n!warn Be careful\n\n[[image:hero]]"
        )
        self.assertEqual([b["type"] for b in parse_blocks(body)], [
            "paragraph", "heading", "list", "quote", "callout", "callout", "image",
        ])
        blocks = parse_blocks(body)
        self.assertEqual(blocks[0]["text"], "Intro line second line")
        self.assertEqual(blocks[2]["items"], ["one", "two"])
        self.assertEqual(blocks[5]["tone"], "warn")

    def test_reading_time_is_at_least_a_minute(self):
        self.assertEqual(reading_minutes("short"), 1)
        self.assertEqual(reading_minutes("word " * 900), 5)


class ApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.source = ContentSource.objects.create(title="S", url="https://example.org", source_type="reference")
        self.section = models.LearningSection.objects.create(slug="history", position=1)
        models.LearningSectionTranslation.objects.create(parent=self.section, language="en", name="History")

    def article(self, slug, status="published", **extra):
        obj = models.LearningArticle.objects.create(
            slug=slug, section=self.section, publication_status=status, **extra,
        )
        models.LearningArticleTranslation.objects.create(
            parent=obj, language="en", title=slug.title(), dek="Dek", body="A paragraph.\n\n[[image:one]]\n\n[[image:gone]]",
        )
        obj.sources.add(self.source)
        return obj

    def test_home_groups_sections_and_hides_empty_ones(self):
        models.LearningSection.objects.create(slug="empty", position=2)
        self.article("first")
        cover = self.article("cover", is_featured=True)
        data = self.client.get(f"{BASE}home/").json()["data"]
        self.assertEqual(data["cover"]["slug"], cover.slug)
        self.assertEqual([s["slug"] for s in data["sections"]], ["history"])
        self.assertEqual(len(data["sections"][0]["articles"]), 2)

    def test_drafts_are_hidden(self):
        self.article("draft", status="draft")
        self.assertEqual(self.client.get(f"{BASE}articles/draft/").status_code, 404)
        self.assertIsNone(self.client.get(f"{BASE}home/").json()["data"]["cover"])

    def test_detail_blocks_keep_only_images_with_rights(self):
        article = self.article("one")
        models.LearningImage.objects.create(
            article=article, key="one", image="learn/a.jpg", image_usage="licensed",
            image_credit="Author", image_source_url="https://example.org", caption="English", caption_hi="हिंदी",
        )
        models.LearningImage.objects.create(article=article, key="gone", image="learn/b.jpg")
        data = self.client.get(f"{BASE}articles/one/", {"language": "hi"}).json()["data"]
        images = [b for b in data["blocks"] if b["type"] == "image"]
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]["caption"], "हिंदी")
        self.assertEqual(data["content_language"], "en")
        self.assertEqual(data["sources"][0]["title"], "S")

    def test_links_to_temples_and_akhadas_not_copies(self):
        tradition = Tradition.objects.create(slug="shaiva")
        hidden = Akhada.objects.create(slug="hidden", tradition=tradition)
        visible = Akhada.objects.create(slug="juna", tradition=tradition, publication_status="published")
        visible.translations.create(language="en", name="Juna", summary="x")
        temple = Temple.objects.create(name="Temple", latitude=1, longitude=1, city="Nashik")
        article = self.article("one")
        article.related_akhadas.set([hidden, visible])
        article.related_temples.add(temple)
        data = self.client.get(f"{BASE}articles/one/").json()["data"]
        self.assertEqual([a["slug"] for a in data["akhadas"]], ["juna"])
        self.assertEqual(data["temples"][0]["id"], str(temple.temple_id))

    def test_related_falls_back_to_the_same_section(self):
        self.article("one")
        self.article("two")
        data = self.client.get(f"{BASE}articles/one/").json()["data"]
        self.assertEqual([a["slug"] for a in data["related"]], ["two"])

    def test_search_filter_and_glossary(self):
        self.article("place", kind="place")
        self.assertEqual(self.client.get(f"{BASE}articles/", {"kind": "guide"}).json()["data"]["count"], 0)
        self.assertEqual(self.client.get(f"{BASE}articles/", {"q": "paragraph"}).json()["data"]["count"], 1)
        term = models.GlossaryTerm.objects.create(slug="ghat", publication_status="published")
        term.translations.create(language="en", term="Ghat", simple="Steps", detail="More")
        term.translations.create(language="hi", term="घाट", simple="सीढ़ियाँ")
        self.assertEqual(self.client.get(f"{BASE}glossary/", {"q": "घाट"}).json()["data"]["count"], 1)
        detail = self.client.get(f"{BASE}glossary/ghat/", {"language": "hi"}).json()["data"]
        self.assertEqual((detail["term"], detail["content_language"]), ("घाट", "hi"))

    def test_read_only(self):
        self.assertEqual(self.client.post(f"{BASE}articles/", {}, format="json").status_code, 405)


class SeedTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_every_article_is_complete_and_properly_sourced(self):
        for article in seed_content.ARTICLES:
            self.assertTrue(article["sources"], article["slug"])
            self.assertLessEqual(set(article["sources"]), set(seed_content.SOURCES))
            for language in ("en", "hi", "mr"):
                title, dek, body = article[language]
                self.assertTrue(title and dek and parse_blocks(body), (article["slug"], language))
            structure = [{b["type"] for b in parse_blocks(article[lang][2])} for lang in ("en", "hi", "mr")]
            self.assertEqual(structure[0], structure[1], article["slug"])
            self.assertEqual(structure[0], structure[2], article["slug"])
        for term in seed_content.GLOSSARY:
            self.assertEqual(len(term), 6)

    def test_seed_loads_drafts_then_publishes_and_keeps_edits(self):
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            out = StringIO()
            call_command("seed_kumbh_content", stdout=out)
            self.assertEqual(self.client_class().get(f"{BASE}home/").json()["data"]["sections"], [])
            self.assertFalse(NewsArticle.objects.published().exists())
            models.LearningArticle.objects.all().delete()
            NewsArticle.objects.all().delete()
            models.GlossaryTerm.objects.all().delete()
            call_command("seed_kumbh_content", "--publish", stdout=out)
            row = models.LearningArticleTranslation.objects.filter(language="en").first()
            row.title = "Edited"
            row.save()
            call_command("seed_kumbh_content", "--publish", stdout=out)
            row.refresh_from_db()
            self.assertEqual(row.title, "Edited")
            self.assertEqual(models.LearningArticle.objects.count(), len(seed_content.ARTICLES))
            self.assertEqual(models.GlossaryTerm.objects.count(), len(seed_content.GLOSSARY))
            for article in models.LearningArticle.objects.all():
                self.assertEqual(article.publish_problems(), [], article.slug)
                self.assertTrue(article.image_source_url, article.slug)
            for story in NewsArticle.objects.all():
                self.assertEqual(story.publish_problems(), [], story.slug)
                self.assertFalse(story.is_official_announcement)
            self.assertEqual(NewsCategory.objects.count(), 10)
            stones = models.LearningArticle.objects.filter(slug__in=("sita-gufa", "tapovan"))
            self.assertEqual({a.verification_status for a in stones}, {"awaiting"})
