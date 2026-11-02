from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO
from unittest import mock

import requests
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.news import adapters, models, seed_content
from apps.news.models import NewsArticle, NewsSource, canonical_url
from apps.news.sync import sync_all, sync_source

BASE = "/api/news/"
RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Nashik Kumbh road works begin</title><link>https://example.org/a?utm_source=rss</link>
<pubDate>Fri, 30 Oct 2026 10:00:00 +0530</pubDate><description>Publisher text must never be kept</description></item>
<item><title>Cricket score</title><link>https://example.org/b</link><pubDate>Fri, 30 Oct 2026 10:00:00 +0530</pubDate></item>
<item><title>Simhastha update with no date</title><link>https://example.org/c</link></item>
<item><title>Kumbh insecure link</title><link>http://example.org/d</link><pubDate>Fri, 30 Oct 2026 10:00:00 +0530</pubDate></item>
</channel></rss>"""


def response(status=200, body=RSS, headers=None):
    fake = mock.Mock(status_code=status, headers=headers or {})
    fake.iter_content.return_value = [body.encode("utf-8")]
    return fake


class NewsTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.official = NewsSource.objects.create(name="PIB", slug="pib", publisher_type="official")
        self.paper = NewsSource.objects.create(
            name="Paper", slug="paper", publisher_type="news", adapter="rss",
            feed_url="https://example.org/feed", is_active=True,
        )
        self.category = models.NewsCategory.objects.create(slug="transport", position=1)
        models.NewsCategoryTranslation.objects.create(parent=self.category, language="en", name="Transport")
        models.NewsCategoryTranslation.objects.create(parent=self.category, language="hi", name="परिवहन")
        self.other = models.NewsCategory.objects.create(slug="dates", position=2)
        models.NewsCategoryTranslation.objects.create(parent=self.other, language="en", name="Dates")

    def story(self, headline, publisher=None, publication="published", days_ago=0, **extra):
        extra.setdefault("category", self.category)
        extra.setdefault("summary", f"About {headline}")
        return NewsArticle.objects.create(
            headline=headline, publisher=publisher or self.paper, publication_status=publication,
            original_url=extra.pop("url", f"https://example.org/{abs(hash(headline))}"),
            published_at=timezone.now() - timedelta(days=days_ago), **extra,
        )

    def results(self, **params):
        response_ = self.client.get(BASE, params)
        self.assertEqual(response_.status_code, 200, response_.content)
        return response_.json()["data"]["results"]


class ApiTests(NewsTestCase):
    def test_home_has_a_lead_notices_and_latest_without_repeats(self):
        self.story("Old", days_ago=3)
        lead = self.story("Lead", days_ago=2, is_featured=True)
        notice = self.story("Notice", publisher=self.official, is_official_announcement=True, days_ago=1)
        data = self.client.get(f"{BASE}home/").json()["data"]
        self.assertEqual(data["lead"]["slug"], lead.slug)
        self.assertEqual([n["slug"] for n in data["announcements"]], [notice.slug])
        self.assertEqual([s["headline"] for s in data["latest"]], ["Old"])
        self.assertEqual([c["slug"] for c in data["categories"]], ["transport"])

    def test_empty_home_is_honest(self):
        data = self.client.get(f"{BASE}home/").json()["data"]
        self.assertIsNone(data["lead"])
        self.assertEqual(data["latest"], [])

    def test_queue_and_rejected_stories_never_appear(self):
        draft = self.story("Queued", publication="draft")
        self.story("Rejected", publication="archived")
        self.assertEqual(self.results(), [])
        self.assertEqual(self.client.get(f"{BASE}{draft.slug}/").status_code, 404)
        self.assertIsNone(self.client.get(f"{BASE}home/").json()["data"]["lead"])

    def test_filters_search_and_sorting(self):
        self.story("Bus timetable", days_ago=5, summary="Nothing else")
        self.story("Rail plan", summary="Bus links too", category=self.other)
        self.assertEqual([s["headline"] for s in self.results(q="bus")], ["Rail plan", "Bus timetable"])
        self.assertEqual([s["headline"] for s in self.results(q="bus", ordering="relevant")], ["Bus timetable", "Rail plan"])
        self.assertEqual([s["headline"] for s in self.results(category="dates")], ["Rail plan"])
        self.assertEqual(self.results(publisher="pib"), [])
        recent = (timezone.localdate() - timedelta(days=1)).isoformat()
        self.assertEqual([s["headline"] for s in self.results(date_from=recent)], ["Rail plan"])
        self.assertEqual(self.client.get(BASE, {"date_from": "soon"}).status_code, 400)
        self.assertEqual(self.client.get(BASE, {"ordering": "bad"}).status_code, 400)

    def test_translation_and_fallback(self):
        story = self.story("English headline", summary="English")
        models.NewsArticleTranslation.objects.create(parent=story, language="hi", headline="हिंदी शीर्षक", summary="सार")
        hindi = self.results(language="hi")[0]
        self.assertEqual((hindi["headline"], hindi["content_language"]), ("हिंदी शीर्षक", "hi"))
        self.assertEqual(hindi["category"]["name"], "परिवहन")
        self.assertEqual(self.results(language="mr")[0]["content_language"], "en")

    def test_detail_links_the_original_and_related_stories(self):
        story = self.story("One", url="https://example.org/original")
        self.story("Two")
        self.story("Elsewhere", category=self.other)
        data = self.client.get(f"{BASE}{story.slug}/").json()["data"]
        self.assertEqual(data["original_url"], "https://example.org/original")
        self.assertEqual([r["headline"] for r in data["related"]], ["Two"])

    def test_stories_without_an_image_use_the_labelled_category_image(self):
        self.category.image = "akhadas/x.jpg"
        self.category.image_usage = "licensed"
        self.category.image_credit = "Author"
        self.category.save()
        self.story("One")
        image = self.results()[0]["image"]
        self.assertTrue(image["representative"])

    def test_read_only(self):
        self.assertEqual(self.client.post(BASE, {}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(f"{BASE}home/").status_code, 405)

    def test_edits_show_straight_away(self):
        story = self.story("Before")
        self.assertEqual(self.results()[0]["headline"], "Before")
        story.headline = "After"
        story.save()
        self.assertEqual(self.results()[0]["headline"], "After")


class RulesTests(NewsTestCase):
    def test_only_official_publishers_can_issue_official_notices(self):
        story = self.story("Paper says", publication="draft", is_official_announcement=True)
        with self.assertRaises(ValidationError):
            story.clean()
        self.assertIn("an official notice needs an official publisher", story.publish_problems())
        notice = self.story("PIB says", publisher=self.official, is_official_announcement=True, publication="draft")
        notice.clean()
        self.assertEqual(notice.publish_problems(), [])

    def test_publishing_needs_our_own_summary_and_a_category(self):
        story = self.story("Queued", publication="draft", summary="", category=None)
        self.assertEqual(len(story.publish_problems()), 2)

    def test_the_same_url_cannot_be_stored_twice(self):
        self.story("One", url="https://example.org/s")
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.story("Two", url="https://EXAMPLE.org/s/?utm_source=x#top")

    def test_canonical_url_drops_tracking_only(self):
        self.assertEqual(canonical_url("https://A.org/x/?id=1&utm_medium=rss&fbclid=z#f"), "https://a.org/x?id=1")

    def test_devanagari_headlines_get_a_usable_slug(self):
        self.assertTrue(self.story("सिंहस्थाचे दरवाजे खुले").slug.startswith("story-"))


class SyncTests(NewsTestCase):
    def sync(self, fake=None, **kwargs):
        with mock.patch.object(adapters.requests, "get", return_value=fake or response()) as get:
            log = sync_source(self.paper, **kwargs)
        return log, get

    def test_only_relevant_https_stories_are_queued_as_drafts(self):
        log, _ = self.sync()
        self.assertEqual((log.fetched, log.relevant, log.created), (3, 2, 2))
        undated = NewsArticle.objects.get(headline__contains="no date")
        self.assertIn("gave no date", undated.editorial_notes)
        story = NewsArticle.objects.get(headline__contains="road works")
        self.assertEqual(story.publication_status, "draft")
        self.assertEqual(story.original_url, "https://example.org/a")
        self.assertEqual(story.summary, "", "publisher text is never stored")
        self.assertEqual(story.source_type, "rss")
        self.assertEqual(story.published_at, datetime(2026, 10, 30, 4, 30, tzinfo=dt_timezone.utc))

    def test_repeat_stories_are_skipped_by_url_and_headline(self):
        self.sync()
        log, _ = self.sync(force=True)
        self.assertEqual((log.created, log.duplicates), (0, 2))
        moved = RSS.replace("https://example.org/a?utm_source=rss", "https://example.org/moved")
        log, _ = self.sync(response(body=moved), force=True)
        self.assertEqual((log.created, log.duplicates), (0, 2))
        self.assertEqual(NewsArticle.objects.count(), 2)

    def test_respects_the_interval_and_conditional_requests(self):
        self.sync(response(headers={"ETag": '"abc"'}))
        self.assertIsNone(sync_source(self.paper))
        log, get = self.sync(response(status=304), force=True)
        self.assertEqual(log.status, "not_modified")
        self.assertEqual(get.call_args.kwargs["headers"]["If-None-Match"], '"abc"')

    def test_failures_are_logged_and_back_off(self):
        log, _ = self.sync(response(status=503))
        self.paper.refresh_from_db()
        self.assertEqual((log.status, self.paper.consecutive_failures), ("failed", 1))
        self.assertEqual(self.paper.last_error, "HTTP 503")
        self.assertEqual(self.paper.next_allowed_check() - self.paper.last_checked_at, timedelta(hours=12))
        with mock.patch.object(adapters.requests, "get", side_effect=requests.Timeout):
            log = sync_source(self.paper, force=True)
        self.assertEqual(log.error, "Timeout")

    def test_unsafe_or_broken_feeds_are_refused(self):
        bomb = '<!DOCTYPE x [<!ENTITY a "b">]><rss><channel/></rss>'
        for body in (bomb, "not xml"):
            log, _ = self.sync(response(body=body), force=True)
            self.assertEqual(log.status, "failed")

    def test_only_active_feeds_are_requested(self):
        self.paper.is_active = False
        self.paper.save()
        with mock.patch.object(adapters.requests, "get") as get:
            self.assertEqual(sync_all(), [])
        get.assert_not_called()

    def test_atom_feeds_parse(self):
        atom = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Kumbh note</title>
        <link href="https://example.org/atom"/><updated>2026-10-30T10:00:00Z</updated></entry></feed>"""
        entries = adapters.RssAdapter().parse(atom.encode())
        self.assertEqual(entries[0].url, "https://example.org/atom")

    def test_setup_schedules_the_task_once(self):
        from django_celery_beat.models import PeriodicTask

        call_command("setup_news_sync", stdout=StringIO())
        call_command("setup_news_sync", stdout=StringIO())
        task = PeriodicTask.objects.get(name="Sync Kumbh news feeds")
        self.assertEqual(task.task, "apps.news.tasks.sync_news_sources")


class SeedTests(TestCase):
    def test_seed_data_is_honest(self):
        self.assertEqual({s["slug"] for s in seed_content.SOURCES if s.get("is_active")}, {"pib"})
        publishers = {s["slug"] for s in seed_content.SOURCES}
        for story in seed_content.STORIES:
            self.assertIn(story["publisher"], publishers)
            self.assertNotIn("official", story)
            for language in ("en", "hi", "mr"):
                headline, summary = story[language]
                self.assertTrue(headline and summary)
                self.assertLess(len(summary), 420, "a short summary, not a copy")
