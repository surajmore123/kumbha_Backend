"""
The five journeys from the Phase 8 brief, end to end through the real APIs with
synthetic people. Only outside providers are replaced: push and Gemini.
"""

import uuid
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.conf import settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.aiChat.services.gemini_service import GeminiQuotaError
from apps.authentication.models import User
from apps.crowd.models.Zone import Zone
from apps.emergency.models import EmergencyRecipient, EmergencySOS
from apps.family.models import FamilyMember
from apps.familylocation.models import MemberLocation
from apps.lostfound.models import CaseExtraction, CaseMatch, CaseNotification, LostFoundCase
from apps.notifications.models import Notification
from apps.operations import services
from apps.safety.models import SafetyHelper

FAMILY = "/api/family/"
SAFETY = "/api/safety/"
LOC = "/api/location/"
REUNION = "/api/reunification/"
LF = "/api/lostfound/"
EM = "/api/emergency/"
OPS = "/api/operations/"
GEMINI = "apps.lostfound.ai.invoke_gemini_json"
PASSWORD = "Synthetic-Ghat-2027!"
SENT = {"status": "sent", "success": 1, "failure": 0, "deactivated": 0}
AT = {"latitude": 19.9975, "longitude": 73.7898}
EXTRACTED = {"fields": {
    "approx_age": {"value": 8, "evidence": "Eight year old"},
    "category": {"value": "child", "evidence": "Eight year old"},
    "clothing": {"value": ["blue shirt", "black shorts"], "evidence": "blue shirt and black shorts"},
    "last_known_location": {"value": "Ramkund", "evidence": "Ramkund"},
}}


@override_settings(
    SAFETY_REQUIRE_HTTPS=False, AI={**settings.AI, "GEMINI_API_KEY": "test", "LOST_FOUND_ENABLED": True},
)
class Scenario(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.zone = Zone.objects.create(
            code="SYN", name="Synthetic Ghat", city="Test", latitude="19.9975", longitude="73.7898", radius_m=2000,
        )
        self.admin = User.objects.create_superuser("synthetic@test.in", "+919330000001", PASSWORD)
        self.organizer = self.person("02")
        self.relative = self.person("03")
        self.stranger = self.person("04")
        for target in (
            "apps.emergency.services.send_localized", "apps.lostfound.notifications.send_localized",
            "apps.safety.notifications.send_localized", "apps.operations.services.send_localized",
        ):
            try:
                patch = mock.patch(target, return_value=SENT)
                patch.start()
                self.addCleanup(patch.stop)
            except AttributeError:
                pass

    def person(self, tail):
        return User.objects.create_user(phone_number=f"+9193300000{tail}", full_Name="Synthetic Person")

    def staff_account(self, tail, role):
        """The admin's steps, then the person's own first sign-in, on real tokens."""
        phone = f"+9193300001{tail}"
        helper, code = services.create_volunteer(
            phone_number=phone, full_name="Synthetic Helper", role=role, zones=[self.zone], by=self.admin,
        )
        services.set_status(helper, "active", self.admin)
        token = self.send("post", f"{OPS}auth/setup/", {"phone_number": phone, "code": code, "password": PASSWORD})
        return helper.user, token["access_token"]

    def login(self, user):
        self.client.credentials()
        self.client.force_authenticate(user)

    def bearer(self, token):
        self.client.force_authenticate(None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def send(self, method, url, body=None, code=200):
        with self.captureOnCommitCallbacks(execute=True):
            response = getattr(self.client, method)(url, body if body is not None else {}, format="json")
        self.assertEqual(response.status_code, code, f"{url}: {response.content[:400]}")
        return response.json().get("data")

    def code_of(self, url):
        return self.client.get(url).status_code

    def circle_with_relative(self):
        self.login(self.organizer)
        family = self.send("post", f"{FAMILY}circles/", {"name": "Synthetic Family"}, 201)["id"]
        invite = self.send("post", f"{FAMILY}circles/{family}/invitations/", {"relationship": "sibling"}, 201)
        self.login(self.relative)
        joined = self.send("post", f"{FAMILY}invitations/accept/", {"code": invite["code"]})
        return family, FamilyMember.objects.get(pk=joined["member_id"])


class ScenarioA_FamilySafety(Scenario):
    def test_the_whole_journey(self):
        family, relative = self.circle_with_relative()
        organizer = FamilyMember.objects.get(user=self.organizer)

        self.login(self.organizer)
        child = self.send("post", f"{FAMILY}circles/{family}/members/", {
            "full_name": "Synthetic Child", "kind": "dependent_child", "relationship": "son", "age_group": "6_12",
        }, 201)
        qr = self.send("post", f"{SAFETY}circles/{family}/members/{child['id']}/qr/", {}, 201)
        self.assertIn("#t=", qr["payload"])

        # The adult shares by their own choice, with one person, for a set time.
        self.login(self.relative)
        session = self.send("post", f"{LOC}circles/{family}/sessions/", {
            "recipient_ids": [str(organizer.pk)], "duration_minutes": 60, "consent": True,
        }, 201)
        self.send("post", f"{LOC}sessions/{session['id']}/update/", {
            "latitude": "19.997500", "longitude": "73.789800", "accuracy_m": 12,
            "captured_at": timezone.now().isoformat(),
        })

        self.login(self.organizer)
        people = self.send("get", f"{LOC}circles/{family}/feed/")["people"]
        shared = [person for person in people if person.get("latitude") is not None]
        self.assertEqual(len(shared), 1)
        self.send("get", f"{REUNION}overview/?family_id={family}")

        self.login(self.stranger)
        self.assertEqual(self.code_of(f"{LOC}circles/{family}/feed/"), 404)

        # Stopping ends it for the viewer straight away.
        self.login(self.relative)
        self.send("post", f"{LOC}sessions/{session['id']}/stop/")
        self.login(self.organizer)
        people = self.send("get", f"{LOC}circles/{family}/feed/")["people"]
        self.assertEqual([person for person in people if person.get("latitude") is not None], [])
        self.assertFalse(MemberLocation.objects.filter(session_id=session["id"]).exists())

        self.login(self.relative)
        self.send("post", f"{LOC}sessions/{session['id']}/update/", {
            "latitude": "19.997500", "longitude": "73.789800", "captured_at": timezone.now().isoformat(),
        }, 410)


class ScenarioB_MissingAndFound(Scenario):
    def test_the_whole_journey(self):
        family, _ = self.circle_with_relative()
        volunteer, _ = self.staff_account("01", "volunteer")
        coordinator, _ = self.staff_account("02", "safety_staff")
        now = timezone.now().isoformat()
        details = {
            "age_min": 8, "age_max": 9, "clothing_description": "blue shirt and black shorts",
            "physical_description": "Eight year old", "location_text": "Ramkund", "event_at": now, **AT,
        }

        self.login(self.organizer)
        lost = self.send("post", f"{LF}cases/", {**details, "relationship": "Parent"}, 201)
        self.login(volunteer)
        found = self.send("post", f"{LF}found/", {
            **details, "found_category": LostFoundCase.FoundCategory.CHILD.value, "safe_facility": "Synthetic help desk",
        }, 201)

        match = CaseMatch.objects.get(lost_case_id=lost["id"], found_case_id=found["id"])
        self.assertEqual(match.state, "suggested")
        stored = LostFoundCase.objects.get(pk=lost["id"])
        self.assertNotIn(stored.status, ("MATCH_CONFIRMED", "REUNITED", "CLOSED"))

        # Staff use AI on the report. It changes nothing on the case.
        self.login(coordinator)
        with mock.patch(GEMINI, return_value=EXTRACTED):
            extraction = self.send("post", f"{LF}ops/cases/{lost['id']}/ai/extract/")
        with mock.patch(GEMINI, return_value={"translated_text": "नीली शर्ट और काली निकर", "uncertain": False}):
            translation = self.send("post", f"{LF}ops/cases/{lost['id']}/ai/translate/", {
                "source_type": "field", "source_ref": "clothing_description", "target_language": "hi",
            })
        self.assertEqual(extraction["review"], "ai")
        self.assertTrue(translation["is_ai"])
        stored.refresh_from_db()
        self.assertEqual(stored.clothing_description, details["clothing_description"])
        self.send("post", f"{LF}ops/cases/{lost['id']}/ai/extract/review/", {"accept": True})
        self.assertEqual(CaseExtraction.objects.get().review, "accepted")

        rows = self.send("get", f"{LF}ops/matches/")["results"]
        self.assertEqual(rows[0]["explanation"]["confidence"], "high")
        self.assertIn("not proof of identity", rows[0]["explanation"]["notice"])

        # No score, and no family confirmation, can reunite anyone.
        reunion = {
            "method": "id_document", "remarks": "Synthetic check at the desk",
            "identity_checked": True, "person_recognised": True,
        }
        self.send("post", f"{LF}ops/cases/{lost['id']}/reunite/", reunion, 409)
        self.login(self.organizer)
        self.send("post", f"{LF}cases/{lost['id']}/confirm-reunion/")
        stored.refresh_from_db()
        self.assertNotEqual(stored.status, "REUNITED")
        self.assertNotIn(b"machine_fields", self.client.get(f"{LF}cases/{lost['id']}/").content)

        self.login(coordinator)
        self.send("post", f"{LF}ops/matches/{match.pk}/approve/", {"notify_family": True})
        self.assertTrue(CaseNotification.objects.filter(case_id=lost["id"]).exists())
        self.send("post", f"{LF}ops/matches/{match.pk}/confirm/", {
            "method": "family_in_person", "remarks": "Synthetic in-person check",
        })
        self.send("post", f"{LF}ops/cases/{lost['id']}/reunite/", reunion)
        stored.refresh_from_db()
        self.assertEqual(stored.status, "REUNITED")
        self.assertEqual(stored.audit.filter(action="reunion_recorded").exists(), True)


class ScenarioC_Sos(Scenario):
    def test_the_whole_journey(self):
        family, _ = self.circle_with_relative()
        coordinator, token = self.staff_account("03", "safety_staff")

        self.login(self.relative)
        sos = self.send("post", f"{EM}sos/", {
            "client_id": str(uuid.uuid4()), "category": "medical", "family_id": family, **AT,
        }, 201)
        row = EmergencySOS.objects.get(pk=sos["id"])
        self.assertEqual(row.user, self.relative)
        self.assertTrue(EmergencyRecipient.objects.filter(sos=row, member__user=self.organizer).exists())
        self.assertTrue(Notification.objects.filter(user=coordinator, category="emergency").exists())

        # A family acknowledgement isn't a responder's, and doesn't resolve anything.
        self.login(self.organizer)
        self.send("post", f"{EM}sos/{sos['id']}/acknowledge-family/")
        row.refresh_from_db()
        self.assertNotEqual(row.status, "ACKNOWLEDGED")

        self.bearer(token)
        self.send("post", f"{EM}ops/sos/{sos['id']}/resolve/", {"body": "Too soon"}, 409)
        self.send("post", f"{EM}ops/sos/{sos['id']}/acknowledge/")
        self.send("post", f"{EM}ops/sos/{sos['id']}/coordinate/", {"body": "Synthetic help on the way"})
        self.send("post", f"{EM}ops/sos/{sos['id']}/update/", {"body": "Synthetic update for the family"})
        row.refresh_from_db()
        self.assertEqual(row.status, "ASSISTANCE_COORDINATED")
        self.assertIsNone(row.resolved_at)

        self.send("post", f"{EM}ops/sos/{sos['id']}/resolve/", {"body": "Synthetic person safe with family"})
        row.refresh_from_db()
        self.assertEqual(row.status, "RESOLVED")
        self.assertIsNotNone(row.resolved_at)


class ScenarioD_VolunteerOperations(Scenario):
    def test_the_whole_journey(self):
        coordinator, coordinator_token = self.staff_account("04", "safety_staff")
        volunteer, token = self.staff_account("05", "volunteer")
        case = LostFoundCase.objects.create(
            case_type="lost", reporter=self.organizer, event_at=timezone.now(), location_text="Synthetic ghat",
            clothing_description="Blue shirt", zone=self.zone,
        )

        self.bearer(coordinator_token)
        self.assertEqual(self.send("get", f"{OPS}me/")["role"], "SAFETY_COORDINATOR")
        self.send("post", f"{OPS}cases/{case.pk}/assign/", {"volunteer_id": str(volunteer.pk)}, 201)

        self.bearer(token)
        me = self.send("get", f"{OPS}me/")
        self.assertEqual(me["role"], "VOLUNTEER")
        self.assertFalse(me["can"]["assign_cases"])
        self.assertEqual([row["id"] for row in self.send("get", f"{OPS}cases/")["results"]], [str(case.pk)])
        self.send("post", f"{OPS}cases/{case.pk}/progress/", {"status": "ACCEPTED"})
        self.send("post", f"{OPS}cases/{case.pk}/observation/", {"body": "Synthetic observation"}, 201)

        # A volunteer's task never changes the case, and staff actions are refused.
        case.refresh_from_db()
        self.assertEqual(case.status, "SUBMITTED")
        self.assertEqual(self.client.get(f"{OPS}team/").status_code, 403)
        self.assertEqual(self.client.post(f"{LF}ops/cases/{case.pk}/reunite/", {}, format="json").status_code, 403)
        self.assertEqual(self.client.get("/admin/").status_code, 302)
        volunteer.refresh_from_db()
        self.assertFalse(volunteer.is_staff or volunteer.is_superuser)

        services.set_status(SafetyHelper.objects.get(user=volunteer), "deactivated", self.admin)
        self.assertIn(self.client.get(f"{OPS}cases/").status_code, (401, 403))
        self.client.credentials()
        response = self.client.post(f"{OPS}auth/login/", {
            "phone_number": volunteer.phone_number, "password": PASSWORD,
        }, format="json")
        self.assertNotEqual(response.status_code, 200)


class ScenarioE_AiAndOfflineResilience(Scenario):
    def report(self, client_id):
        return {
            "client_id": client_id, "relationship": "Parent", "location_text": "Ramkund", "event_at": timezone.now().isoformat(),
            "clothing_description": "blue shirt and black shorts", "age_min": 8, "age_max": 9, **AT,
        }

    def test_the_whole_journey(self):
        coordinator, _ = self.staff_account("06", "safety_staff")
        self.login(self.organizer)
        draft = str(uuid.uuid4())
        case = self.send("post", f"{LF}cases/", self.report(draft), 201)

        with mock.patch(GEMINI, side_effect=GeminiQuotaError("quota")):
            self.login(coordinator)
            url = f"{LF}ops/cases/{case['id']}/ai/"
            self.send("post", f"{url}extract/", code=503)
            self.send("post", f"{url}translate/", {
                "source_type": "field", "source_ref": "clothing_description", "target_language": "mr",
            }, 503)

            # Everything people do without AI keeps working.
            self.send("post", f"{LF}ops/cases/{case['id']}/notes/", {"kind": "internal", "body": "Synthetic note"}, 201)
            self.send("post", f"{LF}ops/cases/{case['id']}/find-matches/")
            self.login(self.relative)
            other = self.send("post", f"{LF}cases/", self.report(str(uuid.uuid4())), 201)
            sos = self.send("post", f"{EM}sos/", {"client_id": str(uuid.uuid4()), "category": "medical"}, 201)
        self.assertTrue(other["id"])
        self.assertTrue(sos["id"])

        # A draft saved offline is sent again after a lost reply: it's still one case.
        self.login(self.organizer)
        repeat = self.client.post(f"{LF}cases/", self.report(draft), format="json")
        self.assertIn(repeat.status_code, (200, 201))
        self.assertEqual(repeat.json()["data"]["id"], case["id"])
        self.assertEqual(LostFoundCase.objects.filter(reporter=self.organizer).count(), 1)

        # The same is true of an SOS retried after a dropped connection.
        self.login(self.stranger)
        token = str(uuid.uuid4())
        first = self.send("post", f"{EM}sos/", {"client_id": token, "category": "medical"}, 201)
        again = self.client.post(f"{EM}sos/", {"client_id": token, "category": "medical"}, format="json")
        self.assertEqual(again.json()["data"]["id"], first["id"])
        self.assertEqual(EmergencySOS.objects.filter(user=self.stranger).count(), 1)

        with mock.patch(GEMINI, return_value=EXTRACTED):
            self.login(coordinator)
            LostFoundCase.objects.filter(pk=case["id"]).update(physical_description="Eight year old")
            self.send("post", f"{LF}ops/cases/{case['id']}/ai/extract/")
        self.assertEqual(CaseExtraction.objects.filter(case_id=case["id"]).count(), 1)
        self.assertLess(timezone.now() - LostFoundCase.objects.get(pk=case["id"]).created_at, timedelta(minutes=5))
