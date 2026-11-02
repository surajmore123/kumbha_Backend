import logging
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.conf import settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.aiChat.services.gemini_service import (
    GeminiQuotaError,
    GeminiServiceError,
    GeminiTimeoutError,
)
from apps.authentication.models import User
from apps.crowd.models.Zone import Zone
from apps.lostfound import ai, matching
from apps.lostfound.models import CaseExtraction, CaseMatch, CaseNote, CaseTranslation, LostFoundCase, Status
from apps.operations import services as operations
from apps.safety.models import SafetyHelper

LF = "/api/lostfound/"
GEMINI = "apps.lostfound.ai.invoke_gemini_json"
ON = {**settings.AI, "GEMINI_API_KEY": "test", "LOST_FOUND_ENABLED": True}
REPORT = "Eight year old in a blue shirt and black shorts, last seen at Ramkund."


def field(value, evidence):
    return {"value": value, "evidence": evidence}


GOOD = {"fields": {
    "category": field("child", "Eight year old"),
    "approx_age": field(8, "Eight year old"),
    "clothing": field(["blue shirt", "black shorts"], "blue shirt and black shorts"),
    "last_known_location": field("Ramkund", "Ramkund"),
}}


@override_settings(AI=ON)
class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.zone = Zone.objects.create(
            code="T1", name="Test", city="Test", latitude="19.99", longitude="73.79", radius_m=900,
        )
        self.other_zone = Zone.objects.create(
            code="T2", name="Other", city="Test", latitude="20.5", longitude="74.5", radius_m=900,
        )
        self.parent = self.user("9990000101")
        self.stranger = self.user("9990000102")
        self.staff = self.helper("9990000103", "safety_staff", self.zone)
        self.far_staff = self.helper("9990000104", "safety_staff", self.other_zone)
        self.volunteer = self.helper("9990000105", "volunteer", self.zone)
        self.other_volunteer = self.helper("9990000106", "volunteer", self.zone)
        self.case = self.make_case()
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def user(self, phone):
        return User.objects.create_user(phone_number=phone, full_Name="Synthetic Tester")

    def helper(self, phone, role, zone):
        user = self.user(phone)
        SafetyHelper.objects.create(user=user, role=role).zones.add(zone)
        return user

    def make_case(self, case_type="lost", **extra):
        values = {
            "case_type": case_type, "reporter": self.parent, "event_at": timezone.now(),
            "location_text": "Ramkund", "clothing_description": "blue shirt and black shorts",
            "physical_description": "Eight year old", "zone": self.zone, "status": Status.SUBMITTED,
            **extra,
        }
        return LostFoundCase.objects.create(**values)

    def url(self, suffix=""):
        return f"{LF}ops/cases/{self.case.pk}/ai/{suffix}"

    def translate(self, ref="clothing_description", language="hi", source_type="field"):
        return self.client.post(
            self.url("translate/"),
            {"source_type": source_type, "source_ref": ref, "target_language": language},
            format="json",
        )

    def data(self, response, code=200):
        self.assertEqual(response.status_code, code, response.content)
        return response.json().get("data")


class TranslationTests(Base):
    @mock.patch(GEMINI, return_value={"translated_text": "नीली कमीज और काली निकर", "source_language": "en", "uncertain": False})
    def test_keeps_the_original_and_records_the_languages(self, gemini):
        row = self.data(self.translate())
        self.assertEqual(row["text"], "नीली कमीज और काली निकर")
        self.assertEqual((row["source_language"], row["target_language"]), ("en", "hi"))
        self.assertEqual(row["source_text"], self.case.clothing_description)
        self.assertTrue(row["is_ai"])
        self.assertFalse(row["is_uncertain"])
        self.case.refresh_from_db()
        self.assertEqual(self.case.clothing_description, "blue shirt and black shorts")

    @mock.patch(GEMINI, return_value={"translated_text": "x", "source_language": "en", "uncertain": False})
    def test_the_same_text_is_not_sent_twice(self, gemini):
        self.data(self.translate())
        self.data(self.translate())
        self.assertEqual(gemini.call_count, 1)

    @mock.patch(GEMINI, return_value={"translated_text": "x", "source_language": "en", "uncertain": False})
    def test_an_edited_report_gets_a_new_translation_and_loses_its_review(self, gemini):
        row = self.data(self.translate())
        self.data(self.client.post(f"{LF}ops/translations/{row['id']}/review/", {"text": "सही"}, format="json"))
        LostFoundCase.objects.filter(pk=self.case.pk).update(clothing_description="red kurta")
        self.assertTrue(self.data(self.client.get(self.url()))["translations"][0]["is_stale"])
        again = self.data(self.translate())
        self.assertEqual(gemini.call_count, 2)
        self.assertEqual(again["review"], "ai")
        self.assertEqual(CaseTranslation.objects.count(), 1)

    def test_a_person_can_correct_or_accept_and_the_machine_text_is_kept(self):
        with mock.patch(GEMINI, return_value={"translated_text": "गलत", "source_language": "en", "uncertain": True}):
            row = self.data(self.translate())
        corrected = self.data(
            self.client.post(f"{LF}ops/translations/{row['id']}/review/", {"text": "सही"}, format="json"),
        )
        self.assertEqual((corrected["text"], corrected["machine_text"]), ("सही", "गलत"))
        self.assertEqual(corrected["review"], "corrected")
        self.assertFalse(corrected["is_ai"])
        accepted = self.data(self.client.post(f"{LF}ops/translations/{row['id']}/review/", {}, format="json"))
        self.assertEqual(accepted["review"], "accepted")
        self.assertTrue(accepted["is_ai"])

    def test_doubtful_results_are_marked_uncertain(self):
        LostFoundCase.objects.filter(pk=self.case.pk).update(clothing_description="Tent 14 near gate 7")
        for reply, expected in (
            ({"translated_text": "टेंट 14 गेट 7", "uncertain": False}, False),
            ({"translated_text": "टेंट १४ गेट ७", "uncertain": False}, False),
            ({"translated_text": "टेंट 41 गेट 7", "uncertain": False}, True),
            ({"translated_text": "टेंट 14 गेट 7", "uncertain": True}, True),
            ({"translated_text": "टेंट 14 गेट 7"}, True),
        ):
            CaseTranslation.objects.all().delete()
            with mock.patch(GEMINI, return_value=reply):
                self.assertEqual(self.data(self.translate())["is_uncertain"], expected, reply)

    def test_a_translation_that_lost_content_is_marked_uncertain(self):
        LostFoundCase.objects.filter(pk=self.case.pk).update(
            clothing_description="Blue shirt, has asthma and needs an inhaler. Call 9876543210 at the desk.",
        )
        for reply in (
            {"translated_text": "नीली कमीज", "uncertain": False},
            {"translated_text": "नीली कमीज, उसे दमा है और इनहेलर चाहिए। डेस्क पर कॉल करें।", "uncertain": False},
        ):
            CaseTranslation.objects.all().delete()
            with mock.patch(GEMINI, return_value=reply):
                self.assertTrue(self.data(self.translate())["is_uncertain"], reply)

    def test_the_translator_is_told_to_keep_stated_safety_details(self):
        with mock.patch(GEMINI, return_value={"translated_text": "x", "uncertain": False}) as gemini:
            self.translate()
        system = gemini.call_args.kwargs["system"]
        self.assertIn("health or safety detail", system)
        self.assertNotIn("Never infer", system)

    @mock.patch(GEMINI, return_value={"source_language": "en"})
    def test_an_empty_reply_stores_nothing(self, gemini):
        self.data(self.translate(), 503)
        self.assertFalse(CaseTranslation.objects.exists())

    @mock.patch(GEMINI, return_value={"translated_text": "x", "uncertain": False})
    def test_contact_details_are_removed_before_sending(self, gemini):
        LostFoundCase.objects.filter(pk=self.case.pk).update(
            clothing_description="Call +91 98765 43210 or synthetic@example.test about the blue shirt",
        )
        self.data(self.translate())
        sent = gemini.call_args.args[0]
        self.assertNotIn("98765", sent)
        self.assertNotIn("example.test", sent)
        self.assertIn("blue shirt", sent)

    @mock.patch(GEMINI, return_value={"translated_text": "x", "uncertain": False})
    def test_notes_can_be_translated_but_only_from_this_case(self, gemini):
        note = CaseNote.objects.create(case=self.case, kind="internal", body="Check the east gate")
        other = self.make_case()
        foreign = CaseNote.objects.create(case=other, kind="internal", body="Private note")
        self.data(self.translate(str(note.pk), source_type="note"))
        self.data(self.translate(str(foreign.pk), source_type="note"), 400)
        self.data(self.translate("not-a-uuid", source_type="note"), 400)
        self.data(self.translate("reporter_phone"), 400)
        self.assertEqual(gemini.call_count, 1)


class ExtractionTests(Base):
    def extract(self, reply):
        with mock.patch(GEMINI, return_value=reply) as gemini:
            self.gemini = gemini
            return self.data(self.client.post(self.url("extract/")))

    def test_gets_the_details_and_leaves_the_case_alone(self):
        LostFoundCase.objects.filter(pk=self.case.pk).update(
            physical_description="", clothing_description="", circumstances=REPORT,
        )
        row = self.extract({"fields": {
            "approx_age": field(8, "Eight year old"),
            "clothing": field(["blue shirt", "black shorts"], "blue shirt and black shorts"),
            "last_known_location": field("Ramkund", "Ramkund"),
            "category": field("child", "Eight year old"),
        }})
        self.assertEqual(row["machine_fields"]["approx_age"]["value"], 8)
        self.assertEqual(row["machine_fields"]["category"]["value"], "child")
        self.assertEqual(row["missing"], ["belongings"])
        self.assertEqual(row["review"], "ai")
        self.case.refresh_from_db()
        self.assertIsNone(self.case.age_min)
        self.assertEqual(self.case.circumstances, REPORT)

    def test_anything_the_report_does_not_say_is_dropped(self):
        row = self.extract({"fields": {
            "approx_age": field(30, "thirty years old"),
            "clothing": field(["green saree"], ""),
            "belongings": {"value": ["bag"]},
            "last_known_location": field("Ramkund", "Ramkund"),
        }})
        self.assertEqual(list(row["machine_fields"]), ["last_known_location"])

    def test_sensitive_and_unknown_fields_are_never_kept(self):
        row = self.extract({"fields": {
            "religion": field("Hindu", "Ramkund"),
            "caste": field("x", "Ramkund"),
            "medical_condition": field("asthma", "Ramkund"),
            "clothing": field(["blue shirt", "Hindu dress"], "blue shirt"),
            "last_known_location": field("Muslim area", "Ramkund"),
        }})
        self.assertEqual(row["machine_fields"]["clothing"]["value"], ["blue shirt"])
        self.assertEqual(set(row["machine_fields"]), {"clothing"})

    def test_values_of_the_wrong_shape_are_dropped(self):
        row = self.extract({"fields": {
            "approx_age": field("eight", "Eight year old"),
            "category": field("toddler", "Eight year old"),
            "clothing": field("blue shirt", "blue shirt"),
        }})
        self.assertEqual(row["machine_fields"], {})

    def test_a_category_that_contradicts_the_age_is_dropped(self):
        row = self.extract({"fields": {
            "approx_age": field(8, "Eight year old"), "category": field("adult", "Eight year old"),
        }})
        self.assertNotIn("category", row["machine_fields"])

    def test_a_reply_without_fields_is_a_failure(self):
        with mock.patch(GEMINI, return_value={"answer": "no"}):
            self.data(self.client.post(self.url("extract/")), 503)
        self.assertFalse(CaseExtraction.objects.exists())

    def test_only_text_is_sent_and_no_name(self):
        LostFoundCase.objects.filter(pk=self.case.pk).update(person_name="Synthetic Name")
        self.extract(GOOD)
        sent = self.gemini.call_args.args[0]
        self.assertIsInstance(sent, str)
        self.assertNotIn("Synthetic Name", sent)

    def test_a_person_can_correct_it_and_only_allowed_fields_stay(self):
        self.extract(GOOD)
        reviewed = self.data(self.client.post(
            self.url("extract/review/"),
            {"accept": True, "corrections": {"approx_age": 9, "clothing": None, "religion": "x"}},
            format="json",
        ))
        self.assertEqual(reviewed["review"], "accepted")
        self.assertEqual(reviewed["reviewed_fields"]["approx_age"], 9)
        self.assertNotIn("clothing", reviewed["reviewed_fields"])
        self.assertNotIn("religion", reviewed["reviewed_fields"])
        self.assertEqual(reviewed["machine_fields"]["approx_age"]["value"], 8)


class ExplainableMatchingTests(Base):
    def pair(self, lost=None, found=None):
        return self.make_case(**(lost or {})), self.make_case("found", **(found or {}))

    def test_reports_what_agrees_differs_and_is_missing(self):
        lost, found = self.pair(
            {"age_min": 8, "age_max": 9, "clothing_description": "blue shirt"},
            {"age_min": 40, "age_max": 45, "clothing_description": "blue shirt", "physical_description": ""},
        )
        result = matching.explain(lost, found)
        self.assertIn("clothing", result["matching"])
        self.assertEqual(result["conflicting"], ["age"])
        self.assertIn("description", result["missing"])
        self.assertIn("location", result["missing"])
        self.assertEqual(result["confidence"], "low")
        self.assertIn("not proof of identity", result["notice"])

    def test_confidence_comes_from_the_score_and_conflicts_lower_it(self):
        lost, found = self.pair(
            {"age_min": 8, "age_max": 8, "latitude": "19.99", "longitude": "73.79"},
            {"age_min": 8, "age_max": 8, "latitude": "19.99", "longitude": "73.79"},
        )
        result = matching.explain(lost, found)
        self.assertEqual(result["confidence"], "high")
        self.assertEqual(result["conflicting"], [])

    def test_different_clothing_is_a_conflict_but_different_scripts_are_not(self):
        lost, found = self.pair({"clothing_description": "green saree"}, {"clothing_description": "white dhoti kurta"})
        self.assertIn("clothing", matching.explain(lost, found)["conflicting"])
        lost, found = self.pair({"clothing_description": "green saree"}, {"clothing_description": "बनियान"})
        result = matching.explain(lost, found)
        self.assertNotIn("clothing", result["conflicting"])
        self.assertIn("clothing", result["missing"])

    def test_scores_are_unchanged_for_reports_without_ai(self):
        lost, found = self.pair({"clothing_description": "red kurta"}, {"clothing_description": "red kurta"})
        before = matching.score_pair(lost, found)
        self.assertEqual(before[0], sum(reason["points"] for reason in before[1]))
        self.assertFalse(matching.explain(lost, found)["uses_reviewed_ai"])

    def _accepted(self, case, fields, review="accepted"):
        return CaseExtraction.objects.create(
            case=case, source_text="x", machine_fields={}, reviewed_fields=fields, review=review,
        )

    def test_only_details_a_person_accepted_affect_the_score(self):
        lost, found = self.pair(
            {"clothing_description": "चांदी कपडे", "physical_description": ""},
            {"clothing_description": "silver robe", "physical_description": ""},
        )
        CaseExtraction.objects.create(
            case=lost, source_text="x", machine_fields={"clothing": {"value": ["silver robe"]}},
        )
        lost = LostFoundCase.objects.get(pk=lost.pk)
        unreviewed = matching.score_pair(lost, found)[0]
        self._accepted(found, {})
        CaseExtraction.objects.filter(case=lost).update(review="accepted", reviewed_fields={"clothing": ["silver robe"]})
        lost = LostFoundCase.objects.get(pk=lost.pk)
        found = LostFoundCase.objects.get(pk=found.pk)
        self.assertEqual(matching.score_pair(lost, found)[0], unreviewed + 30)
        self.assertTrue(matching.explain(lost, found)["uses_reviewed_ai"])

    def test_nothing_is_confirmed_or_closed_however_high_the_score(self):
        lost, found = self.pair(
            {"age_min": 8, "age_max": 8, "latitude": "19.99", "longitude": "73.79"},
            {"age_min": 8, "age_max": 8, "latitude": "19.99", "longitude": "73.79"},
        )
        match = matching.find_matches(lost)[0]
        self.assertEqual(match.state, CaseMatch.State.SUGGESTED)
        for case in (lost, found):
            case.refresh_from_db()
            self.assertEqual(case.status, Status.SUBMITTED)

    def test_staff_see_the_explanation_without_contact_details(self):
        self.case.delete()
        lost, found = self.pair({"zone": self.zone}, {"zone": self.zone})
        matching.find_matches(lost)
        rows = self.data(self.client.get(f"{LF}ops/matches/"))["results"]
        self.assertIn("confidence", rows[0]["explanation"])
        self.assertNotIn("reporter", str(rows[0]))
        self.assertNotIn("phone", str(rows[0]))
        self.assertNotIn("person_name", str(rows[0]))

    def test_the_review_step_is_still_needed_after_ai_review(self):
        lost, found = self.pair()
        with mock.patch(GEMINI, return_value=GOOD):
            self.case = lost
            self.data(self.client.post(self.url("extract/")))
        self.data(self.client.post(self.url("extract/review/"), {"accept": True}, format="json"))
        self.assertTrue(CaseMatch.objects.filter(state=CaseMatch.State.SUGGESTED).exists())
        self.assertFalse(CaseMatch.objects.exclude(state=CaseMatch.State.SUGGESTED).exists())


class FailureTests(Base):
    def test_every_provider_failure_gives_a_clear_503_and_changes_nothing(self):
        for failure in (GeminiServiceError, GeminiTimeoutError, GeminiQuotaError):
            with mock.patch(GEMINI, side_effect=failure("provider text with a report in it")):
                with self.assertLogs("apps.lostfound.ai", logging.WARNING) as logs:
                    response = self.translate()
                self.data(response, 503)
                self.assertEqual(response.json()["errors"]["code"], "ai_unavailable")
                self.assertNotIn("report in it", "".join(logs.output))
                self.data(self.client.post(self.url("extract/")), 503)
        self.assertFalse(CaseTranslation.objects.exists())
        self.assertFalse(CaseExtraction.objects.exists())

    def test_it_can_be_switched_off(self):
        for overrides in ({"LOST_FOUND_ENABLED": False}, {"GEMINI_API_KEY": ""}):
            with override_settings(AI={**ON, **overrides}), mock.patch(GEMINI) as gemini:
                self.assertFalse(self.data(self.client.get(self.url()))["available"])
                self.data(self.translate(), 503)
                gemini.assert_not_called()

    def test_retrying_after_a_failure_works(self):
        with mock.patch(GEMINI, side_effect=GeminiTimeoutError("x")):
            self.data(self.translate(), 503)
        with mock.patch(GEMINI, return_value={"translated_text": "x", "uncertain": False}):
            self.data(self.translate())

    @mock.patch(GEMINI, side_effect=GeminiServiceError("down"))
    @mock.patch("apps.lostfound.notifications.send_localized", return_value={"status": "sent"})
    def test_reporting_and_matching_work_with_ai_down(self, push, gemini):
        CaseMatch.objects.all().delete()
        self.case.delete()
        place = {
            "location_text": "Ramkund", "event_at": timezone.now().isoformat(), "age_min": 8, "age_max": 9,
            "clothing_description": "Blue shirt", "latitude": 19.99, "longitude": 73.79,
        }
        self.client.force_authenticate(self.parent)
        self.data(self.client.post(f"{LF}cases/", {**place, "relationship": "Parent"}, format="json"), 201)
        self.client.force_authenticate(self.volunteer)
        with self.captureOnCommitCallbacks(execute=True):
            self.data(self.client.post(f"{LF}found/", {**place, "found_category": "separated"}, format="json"), 201)
        self.assertEqual(CaseMatch.objects.count(), 1)
        gemini.assert_not_called()

    @mock.patch("apps.lostfound.views.AIThrottle.rate", "2/hour")
    @mock.patch(GEMINI, return_value={"translated_text": "x", "uncertain": False})
    def test_requests_are_limited(self, gemini):
        cache.clear()
        for code in (200, 200, 429):
            self.assertEqual(self.translate().status_code, code)


class AccessTests(Base):
    def test_outsiders_get_nothing(self):
        for user in (self.parent, self.stranger, self.far_staff, self.other_volunteer):
            self.client.force_authenticate(user)
            with mock.patch(GEMINI) as gemini:
                self.assertEqual(self.client.get(self.url()).status_code, 404)
                self.assertEqual(self.translate().status_code, 404)
                self.assertIn(self.client.post(self.url("extract/")).status_code, (404,))
                gemini.assert_not_called()

    def test_no_token_is_refused(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url()).status_code, 401)

    def test_the_assigned_volunteer_sees_only_what_their_case_view_shows(self):
        LostFoundCase.objects.filter(pk=self.case.pk).update(assigned_to=self.volunteer, circumstances="Private")
        note = CaseNote.objects.create(case=self.case, kind="internal", body="Staff only")
        with mock.patch(GEMINI, return_value={"translated_text": "x", "uncertain": False}) as gemini:
            self.data(self.translate(str(note.pk), source_type="note"))
            self.data(self.translate("circumstances"))
            self.client.force_authenticate(self.volunteer)
            self.data(self.translate("clothing_description"))
            self.assertEqual(self.translate("circumstances").status_code, 404)
            self.assertEqual(self.translate("location_text").status_code, 404)
            self.assertEqual(self.translate(str(note.pk), source_type="note").status_code, 404)
            self.assertEqual(self.client.post(self.url("extract/")).status_code, 404)
            self.assertEqual(gemini.call_count, 3)
        rows = self.data(self.client.get(self.url()))["translations"]
        self.assertEqual([row["source_ref"] for row in rows], ["clothing_description"])

    def test_only_staff_review(self):
        with mock.patch(GEMINI, return_value={"translated_text": "x", "uncertain": False}):
            row = self.data(self.translate())
        with mock.patch(GEMINI, return_value=GOOD):
            self.data(self.client.post(self.url("extract/")))
        LostFoundCase.objects.filter(pk=self.case.pk).update(assigned_to=self.volunteer)
        for user in (self.volunteer, self.far_staff, self.stranger):
            self.client.force_authenticate(user)
            self.assertEqual(
                self.client.post(f"{LF}ops/translations/{row['id']}/review/", {"text": "y"}, format="json").status_code,
                404,
            )
            self.assertEqual(
                self.client.post(self.url("extract/review/"), {"accept": True}, format="json").status_code, 404,
            )
        self.assertEqual(CaseTranslation.objects.get().review, "ai")
        self.assertEqual(CaseExtraction.objects.get().review, "ai")

    def test_a_deactivated_volunteer_loses_access_at_once(self):
        LostFoundCase.objects.filter(pk=self.case.pk).update(assigned_to=self.volunteer)
        admin = User.objects.create_superuser("synthetic-admin@test.in", "9990000199", "Synthetic-Pass-2027!")
        operations.set_status(SafetyHelper.objects.get(user=self.volunteer), "deactivated", admin)
        self.client.force_authenticate(User.objects.get(pk=self.volunteer.pk))
        self.assertEqual(self.client.get(self.url()).status_code, 404)

    def test_family_views_show_no_ai_output(self):
        with mock.patch(GEMINI, return_value=GOOD):
            self.data(self.client.post(self.url("extract/")))
        self.client.force_authenticate(self.parent)
        body = self.client.get(f"{LF}cases/{self.case.pk}/").content.decode()
        self.assertNotIn("machine_fields", body)
        self.assertNotIn("ai_extraction", body)

    def test_the_audit_holds_no_report_text(self):
        with mock.patch(GEMINI, return_value={"translated_text": "गुप्त", "uncertain": False}):
            self.data(self.translate())
        details = str(list(self.case.audit.values_list("action", "details")))
        self.assertIn("ai_translated", details)
        self.assertNotIn("गुप्त", details)
        self.assertNotIn("blue shirt", details)
        self.assertIs(ai.is_available(), True)
