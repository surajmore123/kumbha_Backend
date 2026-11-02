from datetime import date, time, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from apps.authentication.models import User
from apps.events.models.EventModel import Event
from apps.journeys import planner
from apps.journeys.models import JourneyItem, JourneyPlan
from apps.temples.models import Temple

BASE = "/api/journeys/"
SOON = date.today() + timedelta(days=30)


def plan_body(**extra):
    body = {
        "title": "Family Simhastha trip",
        "origin_city": "Pune",
        "origin_state": "Maharashtra",
        "arrival_date": SOON.isoformat(),
        "departure_date": (SOON + timedelta(days=3)).isoformat(),
        "adults": 2,
        "children": 1,
        "seniors": 1,
        "transport_mode": "train",
        "budget_amount": "20000",
        "budget_basis": "total",
        "interests": ["bathing", "temples"],
    }
    body.update(extra)
    return body


class JourneyTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(phone_number="9100000001")
        self.other = User.objects.create_user(phone_number="9100000002")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.trimbak = Temple.objects.create(
            name="Trimbakeshwar Jyotirling Mandir", latitude=Decimal("19.93"), longitude=Decimal("73.53"), city="Nashik",
        )
        self.kalaram = Temple.objects.create(
            name="Sri Kala Rama Swamy Temple", latitude=Decimal("20.00"), longitude=Decimal("73.79"), city="Nashik",
        )

    def create(self, **extra):
        response = self.client.post(BASE, plan_body(**extra), format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def snan(self, on, name="Amrit Snan"):
        return Event.objects.create(
            event_name=name, event_category="SNAN", event_subtype="AMRIT", event_date=on,
            start_time=time(4, 0), location_type="NASHIK", location_name="Ramkund",
            data_source="GOVT", is_verified=True, status="PUBLISHED", show_in_app=True,
        )


class CrudTests(JourneyTestCase):
    def test_create_list_retrieve_update_delete(self):
        created = self.create()
        self.assertEqual(created["status"], "draft")
        self.assertEqual(created["travellers"], 4)
        self.assertEqual(created["day_count"], 4)

        listed = self.client.get(BASE).json()["data"]
        self.assertEqual(listed["count"], 1)
        self.assertEqual(listed["results"][0]["id"], created["id"])

        url = f"{BASE}{created['id']}/"
        self.assertEqual(self.client.get(url).json()["data"]["title"], "Family Simhastha trip")
        patched = self.client.patch(url, {"title": "Our Kumbh", "notes": "Carry shawls"}, format="json")
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.json()["data"]["title"], "Our Kumbh")

        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_owner_comes_from_the_token_not_the_body(self):
        created = self.create(user=str(self.other.pk))
        self.assertEqual(JourneyPlan.objects.get(pk=created["id"]).user, self.user)

    def test_draft_without_dates(self):
        response = self.client.post(BASE, {"title": "Someday", "duration_days": 2}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["data"]["day_count"], 2)

    def test_validation(self):
        cases = [
            ({"title": "  "}, "title"),
            ({"departure_date": (SOON - timedelta(days=1)).isoformat()}, "departure_date"),
            ({"departure_date": None}, "departure_date"),
            ({"arrival_date": (date.today() - timedelta(days=2)).isoformat(),
              "departure_date": date.today().isoformat()}, "arrival_date"),
            ({"departure_date": (SOON + timedelta(days=20)).isoformat()}, "departure_date"),
            ({"adults": 0}, "adults"),
            ({"adults": 40, "children": 20}, "adults"),
            ({"budget_amount": "-5"}, "budget_amount"),
            ({"budget_amount": "123.456"}, "budget_amount"),
            ({"interests": ["shopping"]}, "interests"),
            ({"transport_mode": "rocket"}, "transport_mode"),
            ({"language": "fr"}, "language"),
            ({"duration_days": 40, "arrival_date": None, "departure_date": None}, "duration_days"),
        ]
        for extra, field in cases:
            with self.subTest(extra=extra):
                response = self.client.post(BASE, plan_body(**extra), format="json")
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn(field, response.json()["errors"])

    def test_editing_a_plan_whose_arrival_has_passed(self):
        """The app sends the whole form on edit; an unchanged past arrival
        must not block other changes, but a new past arrival is refused."""
        created = self.create()
        JourneyPlan.objects.filter(pk=created["id"]).update(
            arrival_date=date.today() - timedelta(days=2), departure_date=date.today() + timedelta(days=1),
        )
        url = f"{BASE}{created['id']}/"
        same = {
            "title": "Renamed",
            "arrival_date": (date.today() - timedelta(days=2)).isoformat(),
            "departure_date": (date.today() + timedelta(days=1)).isoformat(),
        }
        self.assertEqual(self.client.patch(url, same, format="json").status_code, 200)
        moved = {**same, "arrival_date": (date.today() - timedelta(days=1)).isoformat()}
        response = self.client.patch(url, moved, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("arrival_date", response.json()["errors"])

    def test_database_constraints_back_up_validation(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            JourneyPlan.objects.create(
                user=self.user, title="x", arrival_date=SOON, departure_date=SOON - timedelta(days=1),
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            JourneyPlan.objects.create(user=self.user, title="x", adults=0)

    def test_pagination_filtering_and_limit(self):
        for i in range(12):
            JourneyPlan.objects.create(user=self.user, title=f"Plan {i}", status="draft" if i % 2 else "planned")
        page1 = self.client.get(BASE).json()["data"]
        self.assertEqual((page1["count"], len(page1["results"]), page1["has_next"]), (12, 10, True))
        page2 = self.client.get(BASE, {"page": 2}).json()["data"]
        self.assertEqual(len(page2["results"]), 2)
        drafts = self.client.get(BASE, {"status": "draft"}).json()["data"]
        self.assertEqual(drafts["count"], 6)
        self.assertEqual(self.client.get(BASE, {"status": "nonsense"}).status_code, 400)

        for i in range(JourneyPlan.MAX_PLANS_PER_USER - 12):
            JourneyPlan.objects.create(user=self.user, title=f"Extra {i}")
        response = self.client.post(BASE, plan_body(), format="json")
        self.assertEqual(response.status_code, 400)

    def test_requires_authentication(self):
        self.assertEqual(APIClient().get(BASE).status_code, 401)
        self.assertEqual(APIClient().get(f"{BASE}guide/").status_code, 401)


class OwnershipTests(JourneyTestCase):
    def test_other_users_cannot_see_or_change_a_journey(self):
        created = self.create()
        self.client.post(f"{BASE}{created['id']}/generate/")
        detail = self.client.get(f"{BASE}{created['id']}/").json()["data"]
        item_id = detail["days"][0]["items"][0]["id"]
        check_id = detail["checklist"][0]["id"]

        intruder = APIClient()
        intruder.force_authenticate(self.other)
        root = f"{BASE}{created['id']}/"
        requests = [
            ("get", root, None), ("patch", root, {"title": "x"}), ("delete", root, None),
            ("post", f"{root}generate/", None), ("post", f"{root}duplicate/", None),
            ("get", f"{root}export/", None),
            ("post", f"{root}items/", {"day_number": 1, "title": "x"}),
            ("patch", f"{root}items/{item_id}/", {"title": "x"}),
            ("delete", f"{root}items/{item_id}/", None),
            ("post", f"{root}days/1/reorder/", {"item_ids": []}),
            ("post", f"{root}checklist/", {"text": "x"}),
            ("patch", f"{root}checklist/{check_id}/", {"is_done": True}),
            ("post", f"{root}references/", {"kind": "transport", "title": "x"}),
        ]
        for method, url, body in requests:
            with self.subTest(method=method, url=url):
                response = getattr(intruder, method)(url, body, format="json")
                self.assertEqual(response.status_code, 404)
        self.assertEqual(intruder.get(BASE).json()["data"]["count"], 0)
        self.assertEqual(JourneyPlan.objects.get(pk=created["id"]).title, "Family Simhastha trip")

    def test_item_ids_from_another_journey_are_rejected(self):
        mine = self.create()
        theirs = JourneyPlan.objects.create(user=self.other, title="Theirs", duration_days=1)
        planner.generate(theirs)
        foreign_item = JourneyItem.objects.filter(day__journey=theirs).first()
        response = self.client.patch(
            f"{BASE}{mine['id']}/items/{foreign_item.pk}/", {"title": "hijack"}, format="json",
        )
        self.assertEqual(response.status_code, 404)


class ItineraryTests(JourneyTestCase):
    def generate(self, journey_id, **body):
        response = self.client.post(f"{BASE}{journey_id}/generate/", body, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["data"]

    def test_generated_plan_uses_real_temples_and_bathing_day(self):
        bath_day = SOON + timedelta(days=2)
        event = self.snan(bath_day, "Second Amrit Snan")
        created = self.create()
        data = self.generate(created["id"])

        self.assertEqual(data["status"], "planned")
        self.assertEqual([d["day_number"] for d in data["days"]], [1, 2, 3, 4])
        self.assertEqual(data["days"][0]["date"], SOON.isoformat())
        first_kinds = [i["kind"] for i in data["days"][0]["items"]]
        self.assertIn("travel", first_kinds)
        # Seniors and children: pace notes at the start.
        self.assertEqual(data["days"][0]["items"][0]["kind"], "note")

        bathing = data["days"][2]
        self.assertEqual(bathing["date"], bath_day.isoformat())
        snan_items = [i for i in bathing["items"] if i["kind"] == "bathing"]
        self.assertEqual(snan_items[0]["event"], str(event.event_id))
        self.assertEqual(snan_items[0]["event_name"], "Second Amrit Snan")

        temples = {i["temple"] for d in data["days"] for i in d["items"] if i["temple"]}
        self.assertTrue(temples & {str(self.kalaram.temple_id), str(self.trimbak.temple_id)})
        self.assertEqual(data["days"][-1]["items"][-1]["kind"], "travel")  # departure

        texts = [c["text"] for c in data["checklist"]]
        self.assertTrue(any("child" in t for t in texts))
        self.assertTrue(any("senior" in t for t in texts))
        self.assertEqual(data["generated"]["days"], 4)

    def test_suggestions_in_hindi_and_marathi(self):
        created = self.create(language="mr")
        data = self.generate(created["id"])
        self.assertEqual(data["days"][0]["title"], "नाशिक आगमन")
        data = self.generate(created["id"], language="hi")
        self.assertEqual(data["days"][-1]["title"], "प्रस्थान")

    def test_regenerating_keeps_user_items_and_edits(self):
        created = self.create()
        data = self.generate(created["id"])
        root = f"{BASE}{created['id']}/"
        suggested = data["days"][1]["items"][0]
        self.client.patch(f"{root}items/{suggested['id']}/", {"title": "Our own darshan time"}, format="json")
        added = self.client.post(f"{root}items/", {"day_number": 2, "title": "Meet cousins", "kind": "note"}, format="json")
        self.assertEqual(added.status_code, 201)
        tick = data["checklist"][0]
        self.client.patch(f"{root}checklist/{tick['id']}/", {"is_done": True}, format="json")
        mine = self.client.post(f"{root}checklist/", {"text": "Gift for priest"}, format="json")
        self.assertEqual(mine.status_code, 201)

        again = self.generate(created["id"])
        titles = [i["title"] for d in again["days"] for i in d["items"]]
        self.assertIn("Our own darshan time", titles)
        self.assertIn("Meet cousins", titles)
        checklist = {c["text"]: c["is_done"] for c in again["checklist"]}
        self.assertTrue(checklist[tick["text"]])
        self.assertIn("Gift for priest", checklist)
        self.assertEqual(again["generated"]["kept_items"], 2)

    def test_shorter_trip_moves_kept_items_to_the_last_day(self):
        created = self.create()
        self.generate(created["id"])
        root = f"{BASE}{created['id']}/"
        self.client.post(f"{root}items/", {"day_number": 4, "title": "Buy prasad"}, format="json")
        self.client.patch(root, {"departure_date": (SOON + timedelta(days=1)).isoformat()}, format="json")
        data = self.generate(created["id"])
        self.assertEqual(len(data["days"]), 2)
        self.assertIn("Buy prasad", [i["title"] for i in data["days"][-1]["items"]])

    def test_reorder_and_move_between_days(self):
        created = self.create()
        data = self.generate(created["id"])
        root = f"{BASE}{created['id']}/"
        ids = [i["id"] for i in data["days"][1]["items"]]
        reordered = self.client.post(f"{root}days/2/reorder/", {"item_ids": list(reversed(ids))}, format="json")
        self.assertEqual(reordered.status_code, 200)
        self.assertEqual([i["id"] for i in reordered.json()["data"]], list(reversed(ids)))
        bad = self.client.post(f"{root}days/2/reorder/", {"item_ids": ids[:-1]}, format="json")
        self.assertEqual(bad.status_code, 400)

        moved = self.client.patch(f"{root}items/{ids[0]}/", {"day_number": 3}, format="json")
        self.assertEqual(moved.status_code, 200)
        day3 = self.client.get(root).json()["data"]["days"][2]
        self.assertIn(ids[0], [i["id"] for i in day3["items"]])
        self.assertEqual(
            self.client.patch(f"{root}items/{ids[0]}/", {"day_number": 9}, format="json").status_code, 400,
        )

    def test_single_day_and_recommended_length(self):
        created = self.create(departure_date=SOON.isoformat())
        data = self.generate(created["id"])
        self.assertEqual(len(data["days"]), 1)
        self.assertEqual(data["recommended_days"], 4)  # seniors: slower pace


class ChecklistReferenceBudgetTests(JourneyTestCase):
    def test_checklist_crud(self):
        created = self.create()
        root = f"{BASE}{created['id']}/checklist/"
        item = self.client.post(root, {"text": "Shawl", "category": "packing"}, format="json").json()["data"]
        self.assertEqual(item["source"], "user")
        done = self.client.patch(f"{root}{item['id']}/", {"is_done": True}, format="json").json()["data"]
        self.assertTrue(done["is_done"])
        self.assertEqual(self.client.post(root, {"text": " "}, format="json").status_code, 400)
        self.assertEqual(self.client.delete(f"{root}{item['id']}/").status_code, 204)

    def test_references_are_user_entered_and_validated(self):
        created = self.create()
        root = f"{BASE}{created['id']}/references/"
        ok = self.client.post(root, {
            "kind": "transport", "title": "Train to Nashik Road", "provider": "IRCTC",
            "booking_reference": "PNR 1234567890", "url": "https://www.irctc.co.in/",
            "start_date": SOON.isoformat(),
        }, format="json")
        self.assertEqual(ok.status_code, 201)
        self.assertEqual(
            self.client.post(root, {"kind": "transport", "title": "x", "url": "http://insecure.example"}, format="json").status_code,
            400,
        )
        self.assertEqual(
            self.client.post(root, {
                "kind": "accommodation", "title": "x",
                "start_date": SOON.isoformat(), "end_date": (SOON - timedelta(days=1)).isoformat(),
            }, format="json").status_code,
            400,
        )

    def test_budget_split_is_labelled_as_an_assumption(self):
        data = self.create(budget_amount="5000", budget_basis="per_person")
        budget = data["budget_plan"]
        self.assertEqual(budget["total"], "20000")  # 4 travellers
        self.assertFalse(budget["is_estimate"])
        self.assertEqual(sum(line["percent"] for line in budget["lines"]), 100)
        self.assertIn("not a price estimate", budget["assumption"])
        self.assertIsNone(self.create(budget_amount=None)["budget_plan"])


class DuplicateExportGuideTests(JourneyTestCase):
    def test_duplicate_copies_plan_but_not_bookings(self):
        created = self.create()
        root = f"{BASE}{created['id']}/"
        self.client.post(f"{root}generate/")
        self.client.post(f"{root}references/", {"kind": "transport", "title": "Train"}, format="json")
        copy = self.client.post(f"{root}duplicate/").json()["data"]
        self.assertNotEqual(copy["id"], created["id"])
        self.assertEqual(copy["status"], "draft")
        self.assertTrue(copy["title"].endswith("(copy)"))
        self.assertEqual(len(copy["days"]), 4)
        self.assertEqual(copy["references"], [])
        self.assertFalse(any(c["is_done"] for c in copy["checklist"]))

    def test_export_text(self):
        created = self.create()
        self.client.post(f"{BASE}{created['id']}/generate/")
        text = self.client.get(f"{BASE}{created['id']}/export/").json()["data"]["text"]
        self.assertIn("Family Simhastha trip", text)
        self.assertIn("Day 1", text)
        self.assertIn("Suggestions only", text)

    def test_guide_has_sources_dates_and_no_fake_booking_api(self):
        self.snan(SOON, "First Amrit Snan")
        data = self.client.get(f"{BASE}guide/", {"language": "hi"}).json()["data"]
        self.assertEqual(data["checked_on"], "2026-10-29")
        modes = {t["mode"]: t for t in data["transport"]}
        self.assertEqual(set(modes), {"train", "bus", "flight", "private", "local"})
        self.assertFalse(any(t["booking_api"] for t in data["transport"]))
        self.assertIn("नाशिक रोड", modes["train"]["note"])
        for source in data["sources"]:
            self.assertTrue(source["url"].startswith("https://"))
            self.assertIn(source["status"], {"official", "official_announcement"})
        dates = data["important_dates"]["items"]
        self.assertEqual(dates[0]["name"], "First Amrit Snan")
        self.assertIsNotNone(dates[0]["last_checked"])
        self.assertIn("112", [c["phone"] for c in data["contacts"]["items"]])
