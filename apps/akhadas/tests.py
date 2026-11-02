from datetime import date, timedelta
from io import StringIO
from tempfile import TemporaryDirectory

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase, override_settings
from rest_framework.test import APIClient

from apps.akhadas import admin as akhada_admin, models, seed_articles, seed_directory
from apps.akhadas.models import Publishable

BASE = "/api/akhadas/"
PUBLISHED = Publishable.Publication.PUBLISHED
DRAFT = Publishable.Publication.DRAFT


class AkhadaTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.source = models.ContentSource.objects.create(
            title="Gazette", url="https://example.gov.in/a", source_type="government",
        )
        self.shaiva = models.Tradition.objects.create(slug="shaiva", position=1)
        models.TraditionTranslation.objects.create(parent=self.shaiva, language="en", name="Shaiva", summary="Shiva")
        self.vaishnava = models.Tradition.objects.create(slug="vaishnava", position=2)
        models.TraditionTranslation.objects.create(parent=self.vaishnava, language="en", name="Vaishnava", summary="Vishnu")
        self.juna = self.akhada("juna", "Juna Akhara", hi="जूना अखाड़ा", headquarters="Varanasi")
        self.nirmohi = self.akhada("nirmohi", "Nirmohi Akhada", tradition=self.vaishnava)

    def akhada(self, slug, name, tradition=None, publication=PUBLISHED, hi=None, **extra):
        obj = models.Akhada.objects.create(
            slug=slug, tradition=tradition or self.shaiva, publication_status=publication,
            verification_status="sourced", last_verified_on=date(2026, 10, 30), **extra,
        )
        models.AkhadaTranslation.objects.create(parent=obj, language="en", name=name, summary=f"About {name}")
        if hi:
            models.AkhadaTranslation.objects.create(parent=obj, language="hi", name=hi, summary="हिंदी सार")
        obj.sources.add(self.source)
        return obj

    def saint(self, slug, name, akhada=None, publication=PUBLISHED, **extra):
        obj = models.SadhuProfile.objects.create(
            slug=slug, era="contemporary", akhada=akhada, publication_status=publication, **extra,
        )
        models.SadhuProfileTranslation.objects.create(parent=obj, language="en", name=name, biography="Bio")
        obj.sources.add(self.source)
        return obj

    def article(self, slug, title, category="basics", publication=PUBLISHED):
        obj = models.SpiritualArticle.objects.create(slug=slug, category=category, publication_status=publication)
        models.SpiritualArticleTranslation.objects.create(parent=obj, language="en", title=title, intro="I", body="B")
        obj.sources.add(self.source)
        return obj

    def activity(self, slug, title, publication=PUBLISHED, **extra):
        obj = models.AkhadaActivity.objects.create(
            slug=slug, kind="ceremony", publication_status=publication, **extra,
        )
        models.AkhadaActivityTranslation.objects.create(parent=obj, language="en", title=title, description="D")
        obj.sources.add(self.source)
        return obj

    def results(self, path="", **params):
        response = self.client.get(f"{BASE}{path}", params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["data"]["results"]


class DirectoryTests(AkhadaTestCase):
    def test_public_list_without_login(self):
        data = self.client.get(BASE).json()["data"]
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["results"][0]["name"], "Juna Akhara")
        self.assertEqual(data["results"][0]["tradition"]["slug"], "shaiva")
        self.assertIsNone(data["results"][0]["image"])

    def test_drafts_and_archived_are_hidden_everywhere(self):
        draft = self.akhada("hidden", "Hidden", publication=DRAFT)
        self.akhada("old", "Old", publication=Publishable.Publication.ARCHIVED)
        self.assertEqual([a["slug"] for a in self.results()], ["juna", "nirmohi"])
        self.assertEqual(self.client.get(f"{BASE}hidden/").status_code, 404)
        self.saint("sant", "Sant", publication=DRAFT)
        self.article("draft", "Draft", publication=DRAFT)
        self.activity("draft", "Draft", publication=DRAFT)
        self.assertEqual(self.client.get(f"{BASE}saints/sant/").status_code, 404)
        self.assertEqual(self.client.get(f"{BASE}articles/draft/").status_code, 404)
        self.assertEqual(self.results("activities/"), [])
        # A published profile doesn't reveal the draft Akhada it names.
        self.saint("named", "Named", akhada=draft)
        self.assertIsNone(self.results("saints/")[0]["akhada"])

    def test_published_without_english_stays_hidden(self):
        obj = models.Akhada.objects.create(slug="bare", tradition=self.shaiva, publication_status=PUBLISHED)
        models.AkhadaTranslation.objects.create(parent=obj, language="hi", name="केवल हिंदी", summary="x")
        self.assertEqual(self.client.get(f"{BASE}bare/").status_code, 404)

    def test_language_and_fallback(self):
        hindi = self.results(language="hi")
        self.assertEqual(hindi[0]["name"], "जूना अखाड़ा")
        self.assertEqual(hindi[0]["content_language"], "hi")
        self.assertEqual(hindi[1]["name"], "Nirmohi Akhada")
        self.assertEqual(hindi[1]["content_language"], "en")
        self.assertEqual(self.results(language="fr")[0]["content_language"], "en")

    def test_search_filters_and_ordering(self):
        self.assertEqual([a["slug"] for a in self.results(q="जूना")], ["juna"])
        self.assertEqual([a["slug"] for a in self.results(q="nirmo")], ["nirmohi"])
        self.assertEqual([a["slug"] for a in self.results(tradition="vaishnava")], ["nirmohi"])
        self.assertEqual([a["slug"] for a in self.results(location="Varanasi")], ["juna"])
        self.assertEqual(self.results(classification="other"), [])
        self.assertEqual(self.client.get(BASE, {"ordering": "bad"}).status_code, 400)

    def test_pagination(self):
        for i in range(3):
            self.akhada(f"extra-{i}", f"Extra {i}")
        data = self.client.get(BASE, {"page_size": 2, "page": 2}).json()["data"]
        self.assertEqual((data["count"], data["page"], data["has_next"]), (5, 2, True))
        self.assertEqual(self.client.get(BASE, {"page": 99}).status_code, 404)

    def test_detail_collects_related_content(self):
        saint = self.saint("sant", "Sant", akhada=self.juna)
        article = self.article("basics", "Basics")
        article.related_akhadas.add(self.juna)
        activity = self.activity("camp", "Camp")
        activity.akhadas.add(self.juna)
        title = models.SpiritualTitle.objects.create(slug="mahant")
        models.SpiritualTitleTranslation.objects.create(parent=title, language="en", name="Mahant", meaning="Head")
        vaishnava_only = models.SpiritualTitle.objects.create(slug="other")
        models.SpiritualTitleTranslation.objects.create(parent=vaishnava_only, language="en", name="Other", meaning="x")
        vaishnava_only.traditions.add(self.vaishnava)
        data = self.client.get(f"{BASE}juna/").json()["data"]
        self.assertEqual([s["slug"] for s in data["saints"]], [saint.slug])
        self.assertEqual([a["slug"] for a in data["articles"]], ["basics"])
        self.assertEqual([a["slug"] for a in data["activities"]], ["camp"])
        self.assertEqual([t["slug"] for t in data["titles"]], ["mahant"])
        self.assertEqual(data["sources"][0]["title"], "Gazette")
        self.assertNotIn("verification_notes", data["sources"][0])

    def test_filters_endpoint_lists_only_what_exists(self):
        title = models.SpiritualTitle.objects.create(slug="mahant")
        models.SpiritualTitleTranslation.objects.create(parent=title, language="en", name="Mahant", meaning="Head")
        self.saint("sant", "Sant", title=title)
        data = self.client.get(f"{BASE}filters/").json()["data"]
        self.assertEqual([t["slug"] for t in data["traditions"]], ["shaiva", "vaishnava"])
        self.assertEqual(data["locations"], ["Varanasi"])
        self.assertEqual([t["slug"] for t in data["titles"]], ["mahant"])

    def test_filters_list_akhadas_that_have_published_profiles(self):
        self.saint("sant", "Sant", akhada=self.juna)
        self.saint("hidden", "Hidden", akhada=self.nirmohi, publication=DRAFT)
        data = self.client.get(f"{BASE}filters/").json()["data"]
        self.assertEqual([a["slug"] for a in data["saint_akhadas"]], ["juna"])

    def test_akhada_without_an_image_uses_its_traditions_labelled_as_representative(self):
        self.shaiva.image = "akhadas/place.jpg"
        self.shaiva.image_usage = "licensed"
        self.shaiva.image_credit = "A. Author, CC BY 4.0"
        self.shaiva.image_source_url = "https://example.org/file"
        self.shaiva.save()
        image = self.results()[0]["image"]
        self.assertTrue(image["representative"])
        self.assertEqual(image["source_url"], "https://example.org/file")
        self.assertIsNone(self.results()[1]["image"])
        self.juna.image = "akhadas/juna.jpg"
        self.juna.image_usage = "official"
        self.juna.image_credit = "Juna Akhara"
        self.juna.save()
        self.assertFalse(self.results()[0]["image"]["representative"])

    def test_the_api_is_read_only(self):
        body = {"slug": "x"}
        self.assertEqual(self.client.post(BASE, body, format="json").status_code, 405)
        self.assertEqual(self.client.patch(f"{BASE}juna/", body, format="json").status_code, 405)
        self.assertEqual(self.client.delete(f"{BASE}juna/").status_code, 405)
        self.assertEqual(self.client.post(f"{BASE}saints/", body, format="json").status_code, 405)


class SaintArticleActivityTests(AkhadaTestCase):
    def test_saint_filters(self):
        self.saint("a", "Avdhesh", akhada=self.juna)
        self.saint("b", "Bala", akhada=self.nirmohi)
        self.assertEqual([s["slug"] for s in self.results("saints/", akhada="juna")], ["a"])
        self.assertEqual([s["slug"] for s in self.results("saints/", q="bal")], ["b"])
        self.assertEqual(self.results("saints/", era="historical"), [])

    def test_saint_exposes_no_contact_details(self):
        self.saint("a", "A")
        data = self.client.get(f"{BASE}saints/a/").json()["data"]
        self.assertFalse({"phone", "contact_phone", "contact_email", "address"} & set(data))

    def test_article_filters_and_languages(self):
        one = self.article("one", "One", category="basics")
        self.article("two", "Two", category="kumbh")
        models.SpiritualArticleTranslation.objects.create(parent=one, language="mr", title="एक", intro="I", body="B")
        self.assertEqual([a["slug"] for a in self.results("articles/", category="kumbh")], ["two"])
        self.assertEqual([a["slug"] for a in self.results("articles/", language="mr", translated="true")], ["one"])
        detail = self.client.get(f"{BASE}articles/one/", {"language": "mr"}).json()["data"]
        self.assertEqual(detail["title"], "एक")
        self.assertEqual(detail["available_languages"], ["en", "mr"])

    def test_activity_filters_and_upcoming(self):
        today = date.today()
        self.activity("past", "Past", start_date=today - timedelta(days=3))
        self.activity("soon", "Soon", start_date=today + timedelta(days=3), confirmation="announced")
        self.activity("undated", "Undated", confirmation="awaiting")
        self.activity("history", "History", confirmation="historical")
        upcoming = {a["slug"] for a in self.results("activities/", upcoming="true")}
        self.assertEqual(upcoming, {"soon", "undated"})
        self.assertEqual([a["slug"] for a in self.results("activities/", confirmation="announced")], ["soon"])

    def test_activity_links_an_existing_event_rather_than_copying_it(self):
        self.activity("a", "A")
        self.assertIn("event", self.results("activities/")[0])
        self.assertIsNone(self.results("activities/")[0]["event"])


class CacheTests(AkhadaTestCase):
    def test_edits_show_at_once_despite_the_cache(self):
        self.assertEqual(self.results()[0]["name"], "Juna Akhara")
        row = self.juna.translations.get(language="en")
        row.name = "Corrected name"
        row.save()
        self.assertEqual(self.results()[0]["name"], "Corrected name")
        self.juna.publication_status = DRAFT
        self.juna.save()
        self.assertEqual([a["slug"] for a in self.results()], ["nirmohi"])

    def test_languages_are_cached_separately(self):
        self.assertEqual(self.results()[0]["content_language"], "en")
        self.assertEqual(self.results(language="hi")[0]["content_language"], "hi")


@override_settings(MEDIA_ROOT="/tmp/akhadas-tests")
class ImageRightsTests(AkhadaTestCase):
    GIF = (
        b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00"
        b"\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
    )

    def test_an_image_without_a_usage_basis_never_reaches_the_api(self):
        self.juna.image = SimpleUploadedFile("a.gif", self.GIF, content_type="image/gif")
        self.juna.save()
        self.assertIsNone(self.results()[0]["image"])
        with self.assertRaises(ValidationError):
            self.juna.full_clean()
        self.juna.image_usage = "official"
        self.juna.image_credit = "Juna Akhara"
        self.juna.save()
        image = self.results()[0]["image"]
        self.assertEqual(image["credit"], "Juna Akhara")
        self.assertTrue(image["url"].startswith("http"))


class ModelRuleTests(AkhadaTestCase):
    def test_one_row_per_language(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            models.AkhadaTranslation.objects.create(parent=self.juna, language="en", name="x", summary="y")

    def test_activity_dates(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            models.AkhadaActivity.objects.create(
                slug="bad", kind="camp", start_date=date(2027, 1, 2), end_date=date(2027, 1, 1),
            )

    def test_links_must_be_https(self):
        self.juna.website_url = "http://example.org"
        with self.assertRaises(ValidationError):
            self.juna.full_clean()

    def test_tradition_in_use_cannot_be_deleted_but_a_saint_survives_their_akhada(self):
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            self.shaiva.delete()
        saint = self.saint("a", "A", akhada=self.nirmohi)
        self.nirmohi.delete()
        saint.refresh_from_db()
        self.assertIsNone(saint.akhada)


class EditorialWorkflowTests(AkhadaTestCase):
    def setUp(self):
        super().setUp()
        self.staff = get_user_model().objects.create_superuser("admin@example.org", "9100000099", password="x")
        self.site = AdminSite()

    def request(self):
        request = RequestFactory().post("/admin/")
        request.user = self.staff
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def test_publish_refuses_records_missing_english_or_sources(self):
        admin = akhada_admin.AkhadaAdmin(models.Akhada, self.site)
        draft = self.akhada("draft", "Draft", publication=DRAFT)
        draft.sources.clear()
        admin.publish(self.request(), models.Akhada.objects.filter(pk=draft.pk))
        draft.refresh_from_db()
        self.assertEqual(draft.publication_status, DRAFT)
        draft.sources.add(self.source)
        admin.publish(self.request(), models.Akhada.objects.filter(pk=draft.pk))
        draft.refresh_from_db()
        self.assertEqual(draft.publication_status, PUBLISHED)

    def test_saving_as_published_without_a_source_stays_draft(self):
        draft = self.akhada("draft", "Draft", publication=DRAFT)
        draft.sources.clear()
        client = self.client_class()
        client.force_login(self.staff)
        form = client.get(f"/admin/akhadas/akhada/{draft.pk}/change/").context["adminform"].form
        data = {
            name: ("" if form.initial.get(name) is None else form.initial.get(name))
            for name in form.fields if name not in ("image", "sources")
        }
        data["publication_status"] = PUBLISHED
        row = draft.translations.get()
        data.update({
            "translations-TOTAL_FORMS": 1, "translations-INITIAL_FORMS": 1,
            "translations-MIN_NUM_FORMS": 0, "translations-MAX_NUM_FORMS": 3,
            "translations-0-id": row.pk, "translations-0-parent": draft.pk,
            "translations-0-language": "en", "translations-0-name": row.name,
            "translations-0-summary": row.summary,
        })
        response = client.post(f"/admin/akhadas/akhada/{draft.pk}/change/", data)
        self.assertEqual(response.status_code, 302, getattr(response, "context", None))
        draft.refresh_from_db()
        self.assertEqual(draft.publication_status, DRAFT)
        self.assertEqual(self.client.get(f"{BASE}draft/").status_code, 404)

    def test_licensed_images_need_a_link_to_check_the_licence(self):
        self.juna.image = "akhadas/juna.jpg"
        self.juna.image_usage = "licensed"
        self.juna.image_credit = "Author"
        with self.assertRaises(ValidationError):
            self.juna.full_clean()

    def test_verified_records_need_a_date(self):
        self.juna.last_verified_on = None
        self.juna.save()
        self.assertIn("set the last verified date", self.juna.publish_problems())

    def test_confirmed_activity_needs_an_official_source(self):
        news = models.ContentSource.objects.create(title="Paper", source_type="news")
        activity = self.activity("a", "A", confirmation="confirmed", publication=DRAFT)
        activity.sources.set([news])
        self.assertTrue(activity.publish_problems())
        activity.sources.add(self.source)
        self.assertEqual(activity.publish_problems(), [])

    def test_mark_verified_sets_todays_date(self):
        admin = akhada_admin.AkhadaAdmin(models.Akhada, self.site)
        self.juna.last_verified_on = None
        self.juna.save()
        admin.mark_verified_today(self.request(), models.Akhada.objects.filter(pk=self.juna.pk))
        self.juna.refresh_from_db()
        self.assertEqual(self.juna.last_verified_on, date.today())

    def test_admin_pages_load(self):
        client = self.client_class()
        client.force_login(self.staff)
        for path in ("akhada", "sadhuprofile", "spiritualarticle", "akhadaactivity", "contentsource", "tradition", "spiritualtitle"):
            self.assertEqual(client.get(f"/admin/akhadas/{path}/").status_code, 200, path)
            self.assertEqual(client.get(f"/admin/akhadas/{path}/add/").status_code, 200, path)


class SeedTests(TestCase):
    def setUp(self):
        cache.clear()

    def seed(self, *args):
        call_command("seed_akhadas", *args, stdout=StringIO())

    def test_every_item_has_three_languages_and_known_sources(self):
        groups = [
            seed_directory.TRADITIONS, seed_directory.TITLES, seed_directory.AKHADAS,
            seed_directory.SAINTS, seed_articles.ARTICLES, seed_articles.ACTIVITIES,
        ]
        for group in groups:
            for item in group:
                self.assertTrue(item["sources"], item["slug"])
                self.assertLessEqual(set(item["sources"]), set(seed_directory.SOURCES), item["slug"])
                for language in ("en", "hi", "mr"):
                    self.assertTrue(item[language], (item["slug"], language))

    def test_loads_as_drafts_by_default_then_publishes(self):
        self.seed()
        self.assertEqual(models.Akhada.objects.count(), 13)
        self.assertFalse(models.Akhada.objects.published().exists())
        self.assertEqual(APIClient().get(BASE).json()["data"]["count"], 0)

    def test_published_content_meets_the_publishing_rules(self):
        self.seed("--publish")
        counts = {
            t.slug: t.akhadas.count() for t in models.Tradition.objects.all()
        }
        self.assertEqual(counts, {"shaiva": 7, "vaishnava": 3, "udasin": 2, "nirmal": 1})
        for model in (models.Akhada, models.SadhuProfile, models.SpiritualArticle, models.AkhadaActivity):
            for obj in model.objects.all():
                self.assertEqual(obj.publish_problems(), [], obj.slug)

    def test_no_activity_is_seeded_as_officially_confirmed(self):
        self.seed("--publish")
        self.assertFalse(models.AkhadaActivity.objects.filter(confirmation="confirmed").exists())
        third = models.AkhadaActivity.objects.get(slug="amrit-snan-3-trimbak-2027")
        self.assertEqual(third.start_date, date(2027, 9, 12))
        self.assertEqual(third.translations.get(language="hi").title, "तीसरा अमृत स्नान")

    def test_running_again_keeps_editor_changes(self):
        self.seed("--publish")
        row = models.AkhadaTranslation.objects.get(parent__slug="juna", language="en")
        row.summary = "Edited by an editor"
        row.save()
        self.seed("--publish")
        row.refresh_from_db()
        self.assertEqual(row.summary, "Edited by an editor")
        self.assertEqual(models.Akhada.objects.count(), 13)

    def test_images_follow_their_subject(self):
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            self.seed("--publish")
            client = APIClient()
            nirmal = client.get(f"{BASE}nirmal/").json()["data"]["image"]
            self.assertFalse(nirmal["representative"])
            self.assertIn("commons.wikimedia.org", nirmal["source_url"])
            juna = client.get(f"{BASE}juna/").json()["data"]["image"]
            self.assertTrue(juna["representative"], "a place image, never Juna's own")
            for slug in ("swami-avdheshanand-giri", "swami-kailashanand-giri", "mahant-gopal-giri"):
                self.assertIsNone(client.get(f"{BASE}saints/{slug}/").json()["data"]["image"], slug)
            self.assertIsNotNone(client.get(f"{BASE}saints/adi-shankaracharya/").json()["data"]["image"])
            for model in (models.Tradition, models.Akhada, models.SadhuProfile, models.SpiritualArticle):
                for obj in model.objects.exclude(image=""):
                    obj.full_clean()
            # Running again doesn't replace or duplicate images.
            before = models.Akhada.objects.get(slug="nirmal").image.name
            self.seed("--publish")
            self.assertEqual(models.Akhada.objects.get(slug="nirmal").image.name, before)

    def test_seeded_api_responses(self):
        self.seed("--publish")
        client = APIClient()
        marathi = client.get(f"{BASE}juna/", {"language": "mr"}).json()["data"]
        self.assertEqual(marathi["common_name"], "जुना आखाडा")
        self.assertEqual([s["slug"] for s in marathi["saints"]], ["swami-avdheshanand-giri"])
        self.assertEqual(client.get(f"{BASE}articles/").json()["data"]["count"], 10)
