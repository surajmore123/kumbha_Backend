from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from tempfile import TemporaryDirectory
from unittest import mock

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.authentication.models import User
from apps.bookings import adapters, models
from apps.journeys.models import JourneyPlan
from apps.website.models import Listing

BASE = "/api/bookings/"
SOON = date.today() + timedelta(days=30)


class BookingTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(phone_number="9100000011")
        self.other = User.objects.create_user(phone_number="9100000012")
        self.ramkund = models.StayArea.objects.create(
            slug="ramkund", name="Ramkund", name_hi="रामकुंड", name_mr="रामकुंड",
            latitude=Decimal("19.9975"), longitude=Decimal("73.7910"), position=1,
        )
        self.trimbak = models.StayArea.objects.create(
            slug="trimbak", name="Trimbak", name_hi="त्र्यंबक", name_mr="त्र्यंबक",
            latitude=Decimal("19.9320"), longitude=Decimal("73.5310"), position=2,
        )
        self.parking = models.Amenity.objects.create(slug="parking", name="Parking", name_hi="पार्किंग", name_mr="पार्किंग")
        self.food = models.Amenity.objects.create(slug="food", name="Food", name_hi="भोजन", name_mr="जेवण")

    def stay(self, name, price=1000, listing_status="published", area=None, sample=False, **extra):
        listing = Listing.objects.create(
            category="hotels", name=name, type="Hotel", town="Nashik", area="Road", price_from=price,
            unit="per night", status=listing_status, is_sample=sample,
        )
        extra.setdefault("verification_status", "verified")
        extra.setdefault("last_verified_on", date(2026, 10, 30))
        return models.StayProfile.objects.create(
            listing=listing, stay_type=extra.pop("stay_type", "hotel"), area=area or self.ramkund, **extra,
        )

    def names(self, **params):
        response = self.client.get(f"{BASE}stays/", params)
        self.assertEqual(response.status_code, 200, response.content)
        return [s["name"] for s in response.json()["data"]["results"]]

    def login(self, user=None):
        self.client.force_authenticate(user or self.user)

    def booking(self, **extra):
        body = {"category": "train", "title": "Train to Nashik", "start_date": SOON.isoformat(), **extra}
        response = self.client.post(f"{BASE}saved/", body, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]


class StayTests(BookingTestCase):
    def test_only_real_published_unexpired_stays_appear(self):
        self.stay("Live")
        self.stay("Draft", listing_status="draft")
        self.stay("Sample", sample=True)
        self.stay("Expired", verification_status="expired")
        self.stay("Past", expires_on=date.today() - timedelta(days=1))
        self.assertEqual(self.names(), ["Live"])
        hidden = models.StayProfile.objects.get(listing__name="Draft")
        self.assertEqual(self.client.get(f"{BASE}stays/{hidden.listing_id}/").status_code, 404)

    def test_filters(self):
        cheap = self.stay("Cheap", price=500, stay_type="dharamshala", family_friendly=True)
        cheap.amenities.add(self.parking, self.food)
        rich = self.stay("Rich", price=5000, area=self.trimbak, senior_friendly=True)
        rich.amenities.add(self.parking)
        self.assertEqual(self.names(type="dharamshala"), ["Cheap"])
        self.assertEqual(self.names(area="trimbak"), ["Rich"])
        self.assertEqual(self.names(max_price=1000), ["Cheap"])
        self.assertEqual(self.names(min_price=1000), ["Rich"])
        self.assertEqual(self.names(family="true"), ["Cheap"])
        self.assertEqual(self.names(seniors="true"), ["Rich"])
        response = self.client.get(f"{BASE}stays/", {"amenity": ["parking", "food"]})
        self.assertEqual([s["name"] for s in response.json()["data"]["results"]], ["Cheap"])
        self.assertEqual(self.names(q="ric"), ["Rich"])

    def test_a_stay_with_no_published_price_never_matches_a_budget(self):
        self.stay("Unknown", price=0)
        self.assertEqual(self.names(max_price=100000), [])
        self.assertEqual(self.names(), ["Unknown"])
        data = self.client.get(f"{BASE}stays/").json()["data"]["results"][0]
        self.assertIsNone(data["price_from"])

    def test_availability_filter_needs_provider_confirmation(self):
        self.stay("Unconfirmed")
        self.stay("Confirmed", availability_verified=True)
        self.assertEqual(self.names(available="true"), ["Confirmed"])

    def test_distance_near_area_and_sort(self):
        self.stay("Far", latitude=Decimal("19.9320"), longitude=Decimal("73.5310"))
        self.stay("Close", latitude=Decimal("19.9980"), longitude=Decimal("73.7900"))
        self.stay("Unmapped")
        ordered = self.names(near="ramkund", sort="distance")
        self.assertEqual(ordered, ["Close", "Far", "Unmapped"])
        self.assertEqual(self.names(near="ramkund", radius_km=5), ["Close"])
        data = self.client.get(f"{BASE}stays/", {"lat": "19.9975", "lng": "73.7910", "sort": "distance"}).json()
        self.assertLess(data["data"]["results"][0]["distance_km"], 1)

    def test_price_sort_puts_unknown_prices_last(self):
        self.stay("Unknown", price=0)
        self.stay("Two", price=200)
        self.stay("One", price=100)
        self.assertEqual(self.names(sort="price"), ["One", "Two", "Unknown"])

    def test_bad_input_is_a_clear_error(self):
        for params in ({"min_price": "x"}, {"lat": "999", "lng": "1"}, {"min_price": 9, "max_price": 1}, {"sort": "x"}):
            self.assertEqual(self.client.get(f"{BASE}stays/", params).status_code, 400, params)

    def test_detail_shows_rooms_landmarks_and_language(self):
        stay = self.stay("One", latitude=Decimal("19.9980"), longitude=Decimal("73.7900"))
        models.StayRoom.objects.create(stay=stay, name="AC", name_hi="एसी", price=1714)
        models.StayText.objects.create(parent=stay, language="en", overview="English")
        models.StayText.objects.create(parent=stay, language="hi", overview="हिंदी")
        data = self.client.get(f"{BASE}stays/{stay.listing_id}/", {"language": "hi"}).json()["data"]
        self.assertEqual(data["rooms"][0], {"name": "एसी", "price": 1714})
        self.assertEqual(data["text"]["overview"], "हिंदी")
        self.assertEqual(data["landmarks"][0]["name"], "रामकुंड")
        fallback = self.client.get(f"{BASE}stays/{stay.listing_id}/", {"language": "mr"}).json()["data"]
        self.assertEqual(fallback["text"]["content_language"], "en")

    def test_unlicensed_images_are_withheld_and_area_photos_are_labelled(self):
        stay = self.stay("One")
        models.StayImage.objects.create(stay=stay, image="stay/x.jpg")
        self.ramkund.image = "akhadas/r.jpg"
        self.ramkund.image_usage = "licensed"
        self.ramkund.image_credit = "Author"
        self.ramkund.save()
        data = self.client.get(f"{BASE}stays/{stay.listing_id}/").json()["data"]
        self.assertTrue(data["image"]["representative"])
        self.assertEqual(data["images"], [])

    def test_public_endpoints_are_read_only(self):
        self.assertEqual(self.client.post(f"{BASE}stays/", {}, format="json").status_code, 405)
        self.assertEqual(self.client.get(f"{BASE}stays/filters/").status_code, 200)


class ModelRuleTests(BookingTestCase):
    def test_verified_needs_a_date_and_availability_needs_verification(self):
        stay = self.stay("One", last_verified_on=None)
        with self.assertRaises(ValidationError):
            stay.clean()
        stay.last_verified_on = date.today()
        stay.verification_status = "unverified"
        stay.availability_verified = True
        with self.assertRaises(ValidationError):
            stay.clean()

    def test_coordinates_come_as_a_pair(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.stay("Half", latitude=Decimal("19.9"))

    def test_booking_dates_constraint(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            models.SavedBooking.objects.create(
                user=self.user, category="bus", title="x", start_date=SOON, end_date=SOON - timedelta(days=1),
            )


class TransportTests(BookingTestCase):
    def setUp(self):
        super().setUp()
        models.TransportProvider.objects.create(
            slug="irctc", mode="train", name="IRCTC", website_url="https://www.irctc.co.in/",
            action_url="https://www.irctc.co.in/nget/train-search", can_book=True, note="Book", note_hi="बुक",
        )
        models.TransportProvider.objects.create(
            slug="msrtc", mode="bus", name="MSRTC", website_url="https://msrtc.maharashtra.gov.in/",
        )
        models.TransportProvider.objects.create(
            slug="old", mode="bus", name="Old", website_url="https://example.org/", is_active=False,
        )

    def test_list_and_detail(self):
        data = self.client.get(f"{BASE}transport/", {"mode": "bus"}).json()["data"]
        self.assertEqual([p["slug"] for p in data], ["msrtc"])
        detail = self.client.get(f"{BASE}transport/irctc/", {"language": "hi"}).json()["data"]
        self.assertEqual((detail["url"], detail["note"]), ("https://www.irctc.co.in/nget/train-search", "बुक"))

    def test_search_without_an_integration_returns_nothing_invented(self):
        data = self.client.get(f"{BASE}transport/search/", {"from": "Pune", "to": "Nashik", "mode": "train"}).json()["data"]
        self.assertFalse(data["live"])
        self.assertEqual(data["results"], [])
        self.assertEqual([p["slug"] for p in data["providers"]], ["irctc"])

    def test_search_validation(self):
        url = f"{BASE}transport/search/"
        self.assertEqual(self.client.get(url, {"from": "Pune"}).status_code, 400)
        self.assertEqual(self.client.get(url, {"from": "a", "to": "b", "date": "soon"}).status_code, 400)
        self.assertEqual(self.client.get(url, {"from": "a", "to": "b", "mode": "boat"}).status_code, 400)
        self.assertEqual(self.client.get(url, {"from": "a", "to": "b", "passengers": 0}).status_code, 400)

    def test_a_failing_provider_is_skipped(self):
        class Broken(adapters.TransportAdapter):
            slug = "broken"

            def search(self, query):
                raise TimeoutError

        class Working(adapters.TransportAdapter):
            slug = "working"

            def search(self, query):
                return [{"provider": "Working", "price": 100}]

        with mock.patch.object(adapters, "ADAPTERS", [Broken(), Working()]):
            data = self.client.get(f"{BASE}transport/search/", {"from": "a", "to": "b"}).json()["data"]
        self.assertTrue(data["live"])
        self.assertEqual(data["failed_providers"], ["broken"])
        self.assertEqual(data["results"], [{"provider": "Working", "price": 100}])


class SavedBookingTests(BookingTestCase):
    def test_needs_login(self):
        self.assertEqual(self.client.get(f"{BASE}saved/").status_code, 401)
        self.assertEqual(self.client.post(f"{BASE}saved/", {}, format="json").status_code, 401)

    def test_create_read_update_delete(self):
        self.login()
        created = self.booking(reference="PNR1234567", amount_paid="1500.00", status="pending")
        url = f"{BASE}saved/{created['id']}/"
        self.assertEqual(self.client.get(url).json()["data"]["reference"], "PNR1234567")
        patched = self.client.patch(url, {"status": "confirmed"}, format="json").json()["data"]
        self.assertEqual(patched["status"], "confirmed")
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_owner_comes_from_the_token(self):
        self.login()
        created = self.booking(user=str(self.other.pk))
        self.assertEqual(models.SavedBooking.objects.get(pk=created["id"]).user, self.user)

    def test_other_people_cannot_reach_a_booking(self):
        self.login()
        created = self.booking()
        self.login(self.other)
        url = f"{BASE}saved/{created['id']}/"
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.patch(url, {"title": "x"}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)
        self.assertEqual(self.client.get(f"{BASE}saved/").json()["data"]["count"], 0)

    def test_a_journey_can_only_be_linked_by_its_owner(self):
        mine = JourneyPlan.objects.create(user=self.user, title="Mine")
        theirs = JourneyPlan.objects.create(user=self.other, title="Theirs")
        self.login()
        self.assertEqual(self.booking(journey=str(mine.pk))["journey"], mine.pk.__str__())
        response = self.client.post(
            f"{BASE}saved/", {"category": "bus", "title": "x", "journey": str(theirs.pk)}, format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_card_numbers_are_refused(self):
        self.login()
        for field in ("reference", "notes"):
            response = self.client.post(
                f"{BASE}saved/", {"category": "bus", "title": "x", field: "4111 1111 1111 1111"}, format="json",
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn(field, response.json()["errors"])
        self.booking(reference="4111111111111112")  # fails Luhn: an ordinary reference

    def test_validation(self):
        self.login()
        cases = [
            {"title": "  "},
            {"booking_url": "http://insecure.example"},
            {"start_date": None, "end_date": SOON.isoformat()},
            {"end_date": (SOON - timedelta(days=1)).isoformat()},
            {"amount_paid": "-1"},
            {"amount_paid": "20000000"},
            {"people": 0},
            {"category": "boat"},
            {"status": "guaranteed"},
        ]
        for extra in cases:
            body = {"category": "bus", "title": "x", "start_date": SOON.isoformat(), **extra}
            self.assertEqual(self.client.post(f"{BASE}saved/", body, format="json").status_code, 400, extra)

    def test_upcoming_past_and_filters(self):
        self.login()
        self.booking(title="Soon")
        self.booking(title="Gone", start_date=(date.today() - timedelta(days=5)).isoformat())
        self.booking(title="Off", status="cancelled")
        self.booking(title="Stay", category="stay", status="saved")
        names = lambda **p: [b["title"] for b in self.client.get(f"{BASE}saved/", p).json()["data"]["results"]]
        self.assertEqual(set(names(when="upcoming")), {"Soon", "Stay"})
        self.assertEqual(set(names(when="past")), {"Gone", "Off"})
        self.assertEqual(names(category="stay"), ["Stay"])

    def test_limit(self):
        self.login()
        models.SavedBooking.objects.bulk_create(
            models.SavedBooking(user=self.user, category="bus", title=f"{i}") for i in range(100)
        )
        response = self.client.post(f"{BASE}saved/", {"category": "bus", "title": "x"}, format="json")
        self.assertEqual(response.status_code, 400)


class SeedTests(TestCase):
    def test_seed(self):
        cache.clear()
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            call_command("seed_bookings", "--publish", stdout=StringIO())
            call_command("seed_bookings", "--publish", stdout=StringIO())
            self.assertEqual(models.StayProfile.objects.count(), 2)
            client = APIClient()
            results = client.get(f"{BASE}stays/").json()["data"]["results"]
            trust = next(s for s in results if s["name"] == "Shivprasad Bhaktniwas")
            self.assertEqual((trust["price_from"], trust["price_status"]), (1333, "verified"))
            self.assertTrue(trust["image"]["representative"], "no property photo has confirmed rights")
            mtdc = next(s for s in results if s["name"] == "MTDC Grape Park")
            self.assertIsNone(mtdc["price_from"])
            self.assertEqual(mtdc["verification_status"], "unverified")
            modes = set(models.TransportProvider.objects.values_list("mode", flat=True))
            self.assertEqual(modes, {"train", "bus", "flight", "taxi", "local"})
            self.assertFalse(models.TransportProvider.objects.filter(integration="api").exists())
