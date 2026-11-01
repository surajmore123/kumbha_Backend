import io
import logging
import uuid
from datetime import timedelta
from unittest import mock

from django.contrib.admin.sites import site
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from apps.authentication.models import User
from apps.family.models import FamilyMember, GuardianLink
from apps.lostfound import matching, models, notifications, policy
from apps.lostfound.models import (
    CaseAttachment,
    CaseAudit,
    CaseMatch,
    CaseNote,
    CaseNotification,
    CaseSighting,
    CaseStatusHistory,
    LostFoundCase,
    Status,
)
from apps.safety.models import SafetyHelper

FAMILY = "/api/family/"
SAFETY = "/api/safety/"
LF = "/api/lostfound/"
PUSH = "apps.lostfound.notifications.send_localized"
SENT = {"status": "sent", "success": 1, "failure": 0, "deactivated": 0}
SAFETY_PUSH = "apps.safety.notifications.send_localized"


def jpeg(size=(40, 40), exif=False):
    out = io.BytesIO()
    image = Image.new("RGB", size, (200, 30, 30))
    if exif:
        data = Image.Exif()
        data[0x010F] = "SecretCameraMaker"
        image.save(out, format="JPEG", exif=data)
    else:
        image.save(out, format="JPEG")
    return out.getvalue()


@override_settings(SAFETY_REQUIRE_HTTPS=False, SAFETY_QR_SECRET="test-key")
class LFTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.parent = self.user("61", "Suresh More")
        self.other_parent = self.user("62", "Asha More")
        self.relative = self.user("63", "Ravi More")
        self.outsider = self.user("64", "Stranger")
        self.volunteer = self.user("65", "Volunteer")
        self.desk = self.user("66", "Help Desk")
        self.staff = self.user("67", "Staff")
        SafetyHelper.objects.create(user=self.volunteer, role="volunteer")
        SafetyHelper.objects.create(user=self.desk, role="help_desk")
        SafetyHelper.objects.create(user=self.staff, role="safety_staff")
        self.client = APIClient()
        self.login(self.parent)
        self.family = self.post(f"{FAMILY}circles/", {"name": "More Family"}, 201)
        self.fid = self.family["id"]
        self.child = self.post(f"{FAMILY}circles/{self.fid}/members/", {
            "full_name": "Aarav More", "kind": "dependent_child", "relationship": "son", "age_group": "6_12",
        }, 201)
        for user in (self.other_parent, self.relative):
            self.login(self.parent)
            code = self.post(f"{FAMILY}circles/{self.fid}/invitations/", {"relationship": "sibling"}, 201)["code"]
            self.login(user)
            self.post(f"{FAMILY}invitations/accept/", {"code": code})
        self.login(self.parent)

    def user(self, tail, name):
        return User.objects.create_user(phone_number=f"+9191000000{tail}", full_Name=name)

    def login(self, user):
        self.client.force_authenticate(user)

    def post(self, url, body=None, code=200):
        with mock.patch(PUSH, return_value=SENT), mock.patch(SAFETY_PUSH, return_value=SENT):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(url, body or {}, format="json")
        self.assertEqual(response.status_code, code, response.content)
        return response.json().get("data") if response.content else None

    def get(self, url, code=200):
        response = self.client.get(url)
        self.assertEqual(response.status_code, code, response.content)
        return response.json().get("data")

    def lost_body(self, **extra):
        return {
            "person_name": "Aarav", "age_min": 8, "age_max": 10, "relationship": "Son",
            "clothing_description": "Blue kurta, white cap", "physical_description": "Short, thin, glasses",
            "location_text": "Ramkund east steps", "event_at": (timezone.now() - timedelta(hours=2)).isoformat(),
            "latitude": 19.9975, "longitude": 73.7898, **extra,
        }

    def found_body(self, **extra):
        return {
            "found_category": "separated", "age_min": 7, "age_max": 11,
            "clothing_description": "निळा कुर्ता and white cap", "physical_description": "Thin boy with glasses",
            "location_text": "Panchavati gate", "event_at": (timezone.now() - timedelta(hours=1)).isoformat(),
            "latitude": 20.0060, "longitude": 73.7910, "safe_facility": "Help desk 3", **extra,
        }

    def lost(self, **extra):
        self.login(self.parent)
        return self.post(f"{LF}cases/", self.lost_body(**extra), 201)

    def linked(self):
        return self.lost(member_id=self.child["id"], family_id=self.fid)

    def found(self, **extra):
        self.login(self.volunteer)
        return self.post(f"{LF}found/", self.found_body(**extra), 201)

    def as_staff(self):
        self.login(self.staff)

    def pair(self):
        lost, found = self.lost(), self.found()
        return lost, found, CaseMatch.objects.get(lost_case_id=lost["id"], found_case_id=found["id"])

    def confirmed(self):
        lost, found, match = self.pair()
        self.as_staff()
        self.post(f"{LF}ops/matches/{match.pk}/approve/")
        self.post(f"{LF}ops/matches/{match.pk}/confirm/", {"method": "family_in_person", "remarks": "Father identified him at desk 3"})
        return lost, found, match


class LostReportTests(LFTestCase):
    def test_creates_a_submitted_case_with_a_reference(self):
        body = self.lost()
        self.assertRegex(body["reference"], r"^LF-[A-Z2-9]{8}$")
        self.assertEqual(body["status"], "SUBMITTED")
        case = LostFoundCase.objects.get(pk=body["id"])
        self.assertEqual(case.reporter, self.parent)
        self.assertEqual(case.status_history.get().to_status, "SUBMITTED")

    def test_needs_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(f"{LF}cases/", {}, format="json").status_code, 401)
        self.assertEqual(self.client.get(f"{LF}cases/").status_code, 401)

    def test_validates(self):
        for change in (
            {"location_text": ""},
            {"relationship": ""},
            {"event_at": (timezone.now() + timedelta(days=1)).isoformat()},
            {"physical_description": "", "clothing_description": ""},
            {"age_min": 30, "age_max": 20},
            {"age_min": 200},
            {"latitude": 19.9, "longitude": None},
            {"vulnerabilities": ["bad"]},
        ):
            self.post(f"{LF}cases/", self.lost_body(**change), 400)

    def test_references_are_unique(self):
        self.assertEqual(len({self.lost()["reference"] for _ in range(5)}), 5)

    def test_a_retry_with_the_same_client_id_makes_no_second_case(self):
        cid = str(uuid.uuid4())
        first = self.lost(client_id=cid)
        again = self.post(f"{LF}cases/", self.lost_body(client_id=cid), 200)
        self.assertEqual(first["id"], again["id"])
        self.assertTrue(again["duplicate"])
        self.assertEqual(LostFoundCase.objects.count(), 1)

    def test_the_same_family_member_cant_be_reported_twice(self):
        first = self.linked()
        again = self.post(f"{LF}cases/", self.lost_body(member_id=self.child["id"], family_id=self.fid), 200)
        self.assertEqual(first["id"], again["id"])

    def test_the_database_blocks_duplicates_too(self):
        self.linked()
        case = LostFoundCase.objects.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            LostFoundCase.objects.create(
                case_type="lost", member=case.member, event_at=timezone.now(), location_text="x",
            )

    def test_a_dependent_is_marked_vulnerable_automatically(self):
        self.linked()
        case = LostFoundCase.objects.get()
        self.assertIn("child", case.vulnerabilities)
        self.assertTrue(case.is_vulnerable)

    def test_someone_elses_family_member_cant_be_used(self):
        self.login(self.outsider)
        self.post(f"{LF}cases/", self.lost_body(member_id=self.child["id"], family_id=self.fid), 400)

    def test_reports_are_rate_limited(self):
        self.login(self.outsider)
        with mock.patch("apps.lostfound.views.ReportThrottle.rate", "3/hour"):
            codes = [
                self.client.post(f"{LF}cases/", {}, format="json").status_code for _ in range(6)
            ]
        self.assertIn(429, codes)


class FoundReportTests(LFTestCase):
    def test_a_helper_reports_one(self):
        body = self.found()
        case = LostFoundCase.objects.get(pk=body["id"])
        self.assertEqual((case.case_type, case.reporter_role), ("found", "volunteer"))

    def test_an_ordinary_user_cant(self):
        self.login(self.outsider)
        self.post(f"{LF}found/", self.found_body(), 403)

    def test_a_lapsed_helper_cant(self):
        SafetyHelper.objects.filter(user=self.volunteer).update(is_active=False)
        self.login(self.volunteer)
        self.post(f"{LF}found/", self.found_body(), 403)

    def test_a_child_needs_a_safe_place_recorded(self):
        self.login(self.volunteer)
        self.post(f"{LF}found/", self.found_body(found_category="child_alone", safe_facility=""), 400)
        self.post(f"{LF}found/", self.found_body(found_category="child_alone"), 201)
        self.assertIn("child", LostFoundCase.objects.get().vulnerabilities)

    def test_a_retry_makes_no_second_case(self):
        cid = str(uuid.uuid4())
        self.found(client_id=cid)
        self.post(f"{LF}found/", self.found_body(client_id=cid), 200)
        self.assertEqual(LostFoundCase.objects.count(), 1)


class AccessTests(LFTestCase):
    def test_strangers_get_404_on_everything(self):
        case = self.lost()
        attachment = CaseAttachment.objects.create(
            case_id=case["id"], content_type="image/jpeg", data=b"x",
        )
        self.login(self.outsider)
        self.get(f"{LF}cases/{case['id']}/", 404)
        self.get(f"{LF}attachments/{attachment.pk}/", 404)
        for action in ("info", "correction", "cancel", "confirm-reunion", "sightings"):
            self.post(f"{LF}cases/{case['id']}/{action}/", {"body": "x"}, 404)
        self.assertEqual(self.get(f"{LF}cases/"), [])

    def test_unknown_and_forbidden_look_the_same(self):
        case = self.lost()
        self.login(self.outsider)
        real = self.client.get(f"{LF}cases/{case['id']}/")
        fake = self.client.get(f"{LF}cases/{uuid.uuid4()}/")
        self.assertEqual((real.status_code, fake.status_code), (404, 404))

    def test_ordinary_users_cant_reach_operations(self):
        case = self.lost()
        for user in (self.parent, self.outsider, self.volunteer):
            self.login(user)
            self.get(f"{LF}ops/cases/", 403)
            self.get(f"{LF}ops/cases/{case['id']}/", 403)
            self.get(f"{LF}ops/matches/", 403)
            self.post(f"{LF}ops/cases/{case['id']}/status/", {"status": "UNDER_REVIEW", "reason": "x"}, 403)
            self.post(f"{LF}ops/cases/{case['id']}/contact/", code=403)

    def test_a_help_desk_sees_only_assigned_cases(self):
        case = self.lost()
        self.login(self.desk)
        self.assertEqual(self.get(f"{LF}ops/cases/")["count"], 0)
        self.get(f"{LF}ops/cases/{case['id']}/", 404)
        LostFoundCase.objects.update(assigned_to=self.desk)
        self.assertEqual(self.get(f"{LF}ops/cases/")["count"], 1)
        self.get(f"{LF}ops/cases/{case['id']}/")

    def test_a_family_sees_a_linked_case(self):
        GuardianLink.objects.create(
            dependent_id=self.child["id"], guardian=FamilyMember.objects.get(user=self.other_parent),
        )
        case = self.linked()
        self.login(self.other_parent)
        self.get(f"{LF}cases/{case['id']}/")
        self.assertEqual(len(self.get(f"{LF}cases/")), 1)

    def test_a_relative_who_isnt_a_guardian_doesnt(self):
        case = self.linked()
        self.login(self.relative)
        self.get(f"{LF}cases/{case['id']}/", 404)
        self.assertEqual(self.get(f"{LF}cases/"), [])

    def test_a_helper_sees_their_report_not_the_family_view(self):
        found = self.found()
        seen = self.get(f"{LF}cases/{found['id']}/")
        self.assertNotIn("timeline", seen)
        self.assertNotIn("physical_description", seen)


class FamilyViewTests(LFTestCase):
    def test_internal_material_is_hidden(self):
        case = self.lost()
        self.as_staff()
        self.post(f"{LF}ops/cases/{case['id']}/notes/", {"kind": "internal", "body": "Internal secret"}, 201)
        self.post(f"{LF}ops/cases/{case['id']}/notes/", {"kind": "family_update", "body": "We are looking"}, 201)
        self.post(f"{LF}ops/cases/{case['id']}/status/", {"status": "UNDER_REVIEW", "reason": "Reason secret"})
        self.login(self.parent)
        seen = str(self.get(f"{LF}cases/{case['id']}/"))
        self.assertIn("We are looking", seen)
        self.assertNotIn("Internal secret", seen)
        self.assertNotIn("Reason secret", seen)
        self.assertNotIn("Staff", seen)

    def test_potential_matches_are_never_in_the_family_view(self):
        lost, _, _ = self.pair()
        self.login(self.parent)
        seen = self.get(f"{LF}cases/{lost['id']}/")
        self.assertNotIn("matches", seen)
        self.assertEqual(seen["status"], "SUBMITTED")

    def test_no_phone_number_in_any_case_response(self):
        case = self.lost()
        self.login(self.parent)
        self.assertNotIn("+9191", str(self.get(f"{LF}cases/{case['id']}/")))
        self.as_staff()
        self.assertNotIn("+9191", str(self.get(f"{LF}ops/cases/{case['id']}/")))

    def test_add_information_and_correction_reach_staff(self):
        case = self.lost()
        self.post(f"{LF}cases/{case['id']}/info/", {"body": "He has a red bag"})
        self.post(f"{LF}cases/{case['id']}/correction/", {"body": "He's 9"})
        self.assertEqual(CaseNote.objects.filter(kind="family_info").count(), 1)
        self.assertEqual(CaseNote.objects.filter(kind="correction").count(), 1)

    def test_cancelling(self):
        case = self.lost()
        self.post(f"{LF}cases/{case['id']}/cancel/", {"reason": "Found him"})
        self.assertEqual(LostFoundCase.objects.get().status, "CLOSED")
        self.post(f"{LF}cases/{case['id']}/cancel/", code=409)

    def test_only_the_reporter_can_cancel(self):
        case = self.linked()
        self.login(self.other_parent)
        self.post(f"{LF}cases/{case['id']}/cancel/", code=404)

    def test_a_confirmed_match_cant_be_cancelled(self):
        lost, _, _ = self.confirmed()
        self.login(self.parent)
        self.post(f"{LF}cases/{lost['id']}/cancel/", code=409)

    def test_a_family_confirmation_doesnt_reunite_anyone(self):
        case = self.lost()
        self.post(f"{LF}cases/{case['id']}/confirm-reunion/")
        stored = LostFoundCase.objects.get()
        self.assertIsNotNone(stored.family_confirmed_at)
        self.assertEqual(stored.status, "SUBMITTED")


class StatusTests(LFTestCase):
    def change(self, case, status, code=200, reason="Checked by staff"):
        return self.post(f"{LF}ops/cases/{case['id']}/status/", {"status": status, "reason": reason}, code)

    def test_a_change_records_everything(self):
        case = self.lost()
        self.as_staff()
        self.change(case, "UNDER_REVIEW")
        row = CaseStatusHistory.objects.filter(to_status="UNDER_REVIEW").get()
        self.assertEqual((row.from_status, row.updated_by, row.reason), ("SUBMITTED", self.staff, "Checked by staff"))
        self.assertIsNotNone(row.created_at)

    def test_a_reason_is_required(self):
        case = self.lost()
        self.as_staff()
        self.change(case, "UNDER_REVIEW", 400, reason="")

    def test_illegal_moves_are_refused(self):
        case = self.lost()
        self.as_staff()
        self.change(case, "REUNITED", 409)
        self.change(case, "MATCH_CONFIRMED", 409)
        self.change(case, "CLOSED")
        self.change(case, "POTENTIAL_MATCH_FOUND", 409)

    def test_a_closed_case_can_be_reopened(self):
        case = self.lost()
        self.as_staff()
        self.change(case, "CLOSED")
        self.change(case, "UNDER_REVIEW")

    def test_history_cant_be_edited_or_removed(self):
        self.lost()
        row = CaseStatusHistory.objects.first()
        row.reason = "changed"
        with self.assertRaises(PermissionDenied):
            row.save()
        with self.assertRaises(PermissionDenied):
            row.delete()
        audit = CaseAudit.objects.first()
        with self.assertRaises(PermissionDenied):
            audit.delete()

    def test_sensitive_actions_are_audited_without_details(self):
        case = self.lost()
        self.as_staff()
        self.get(f"{LF}ops/cases/{case['id']}/")
        self.post(f"{LF}ops/cases/{case['id']}/contact/")
        actions = set(CaseAudit.objects.values_list("action", flat=True))
        self.assertLessEqual({"case_created", "case_viewed", "contact_revealed"}, actions)
        self.assertNotIn("9100", str(list(CaseAudit.objects.values_list("details", flat=True))))

    def test_a_number_is_only_returned_through_its_logged_route(self):
        case = self.lost()
        self.as_staff()
        body = self.post(f"{LF}ops/cases/{case['id']}/contact/")
        self.assertEqual(body["phone"], "+919100000061")


class MatchingTests(LFTestCase):
    def test_similar_reports_are_suggested_with_reasons(self):
        _, _, match = self.pair()
        self.assertGreaterEqual(match.score, matching.MINIMUM_SCORE)
        attributes = {r["attribute"] for r in match.reasons}
        self.assertLessEqual({"age", "clothing", "location", "time"}, attributes)
        clothing = next(r for r in match.reasons if r["attribute"] == "clothing")
        self.assertIn("blue", clothing["detail"], "Marathi and English compare")

    def test_a_suggestion_changes_nothing(self):
        lost, found, match = self.pair()
        self.assertEqual(match.state, "suggested")
        self.assertEqual(LostFoundCase.objects.get(pk=lost["id"]).status, "SUBMITTED")
        self.assertEqual(LostFoundCase.objects.get(pk=found["id"]).status, "SUBMITTED")

    def test_dissimilar_reports_arent_suggested(self):
        self.lost()
        self.found(
            age_min=60, age_max=70, clothing_description="Saffron dhoti", physical_description="Tall with a beard",
            latitude=19.0, longitude=72.8,
        )
        self.assertFalse(CaseMatch.objects.exists())

    def test_gender_and_names_play_no_part(self):
        lost = LostFoundCase(
            case_type="lost", person_name="Aarav", gender="male", age_min=8, age_max=10,
            clothing_description="red", event_at=timezone.now(), location_text="x",
        )
        one = LostFoundCase(
            case_type="found", person_name="Aarav", gender="male", age_min=8, age_max=10,
            clothing_description="red", event_at=timezone.now(), location_text="x",
        )
        two = LostFoundCase(
            case_type="found", person_name="Other", gender="female", age_min=8, age_max=10,
            clothing_description="red", event_at=timezone.now(), location_text="x",
        )
        self.assertEqual(matching.score_pair(lost, one)[0], matching.score_pair(lost, two)[0])

    def test_reviewed_matches_arent_overwritten(self):
        _, _, match = self.pair()
        self.as_staff()
        self.post(f"{LF}ops/matches/{match.pk}/dismiss/", {"reason": "Different child"})
        matching.find_matches(match.lost_case)
        match.refresh_from_db()
        self.assertEqual(match.state, "dismissed")

    def test_a_pair_is_only_suggested_once(self):
        _, _, match = self.pair()
        matching.find_matches(match.lost_case)
        matching.find_matches(match.found_case)
        self.assertEqual(CaseMatch.objects.count(), 1)

    def test_matching_failure_doesnt_lose_a_report(self):
        with mock.patch("apps.lostfound.matching.find_matches", side_effect=RuntimeError("x")):
            self.lost()
        self.assertEqual(LostFoundCase.objects.count(), 1)

    def test_a_match_cant_be_confirmed_without_review(self):
        _, _, match = self.pair()
        self.as_staff()
        body = {"method": "family_in_person", "remarks": "Seen together at the desk"}
        self.post(f"{LF}ops/matches/{match.pk}/confirm/", body, 409)
        self.assertFalse(LostFoundCase.objects.filter(status="MATCH_CONFIRMED").exists())

    def test_confirming_needs_a_recorded_check(self):
        _, _, match = self.pair()
        self.as_staff()
        self.post(f"{LF}ops/matches/{match.pk}/approve/")
        self.post(f"{LF}ops/matches/{match.pk}/confirm/", {"method": "family_in_person", "remarks": "ok"}, 409)
        self.post(f"{LF}ops/matches/{match.pk}/confirm/", {"method": "guess", "remarks": "Looks similar to me"}, 400)
        self.post(f"{LF}ops/matches/{match.pk}/confirm/", {"method": "family_in_person", "remarks": "Father identified him"})
        self.assertEqual(LostFoundCase.objects.filter(status="MATCH_CONFIRMED").count(), 2)
        self.assertEqual(CaseNote.objects.filter(kind="verification").count(), 2)

    def test_only_staff_review_matches(self):
        _, _, match = self.pair()
        LostFoundCase.objects.update(assigned_to=self.desk)
        self.login(self.desk)
        self.post(f"{LF}ops/matches/{match.pk}/approve/", code=403)
        self.get(f"{LF}ops/matches/", 403)

    def test_dismissing_the_last_match_returns_the_case_to_review(self):
        lost, _, match = self.pair()
        self.as_staff()
        self.post(f"{LF}ops/matches/{match.pk}/approve/")
        self.assertEqual(LostFoundCase.objects.get(pk=lost["id"]).status, "POTENTIAL_MATCH_FOUND")
        self.post(f"{LF}ops/matches/{match.pk}/dismiss/", {"reason": "Different child"})
        self.assertEqual(LostFoundCase.objects.get(pk=lost["id"]).status, "UNDER_REVIEW")


class ReunionTests(LFTestCase):
    REUNION = {
        "method": "id_document", "remarks": "Checked Aadhaar and the boy knew him",
        "identity_checked": True, "person_recognised": True,
    }

    def test_similar_descriptions_alone_cant_reunite(self):
        lost, _, _ = self.pair()
        self.as_staff()
        self.post(f"{LF}ops/cases/{lost['id']}/reunite/", self.REUNION, 409)

    def test_needs_an_identity_check(self):
        lost, _, _ = self.confirmed()
        self.post(f"{LF}ops/cases/{lost['id']}/reunite/", {**self.REUNION, "identity_checked": False}, 409)

    def test_a_vulnerable_person_must_recognise_them(self):
        lost, _, _ = self.confirmed()
        LostFoundCase.objects.update(vulnerabilities=["child"])
        self.post(f"{LF}ops/cases/{lost['id']}/reunite/", {**self.REUNION, "person_recognised": False}, 409)

    def test_a_full_handover_closes_both_sides(self):
        lost, found, _ = self.confirmed()
        self.post(f"{LF}ops/cases/{lost['id']}/reunite/", self.REUNION)
        for pk in (lost["id"], found["id"]):
            case = LostFoundCase.objects.get(pk=pk)
            self.assertEqual(case.status, "REUNITED")
            self.assertEqual(case.reunited_by, self.staff)

    def test_a_wrong_match_can_be_undone_before_handover(self):
        lost, _, _ = self.confirmed()
        self.post(f"{LF}ops/cases/{lost['id']}/status/", {"status": "UNDER_REVIEW", "reason": "Wrong child"})


class SightingTests(LFTestCase):
    def sighting(self, case):
        return self.post(f"{LF}cases/{case['id']}/sightings/", {
            "description": "Near the temple gate", "location_text": "Kalaram gate",
            "seen_at": timezone.now().isoformat(),
        }, 201)

    def test_it_waits_for_review(self):
        case = self.lost()
        self.sighting(case)
        seen = self.get(f"{LF}cases/{case['id']}/")
        self.assertEqual(seen["sightings"], [])

    def test_approved_is_labelled_reported_and_verified_labelled_verified(self):
        case = self.lost()
        body = self.sighting(case)
        self.as_staff()
        self.post(f"{LF}ops/sightings/{body['id']}/review/", {"approve": True})
        self.login(self.parent)
        row = self.get(f"{LF}cases/{case['id']}/")["sightings"][0]
        self.assertEqual((row["location_label"], row["source"]), ("reported", "community"))
        CaseSighting.objects.update(verified=True)
        row = self.get(f"{LF}cases/{case['id']}/")["sightings"][0]
        self.assertEqual(row["location_label"], "verified")

    def test_a_stranger_cant_add_one(self):
        case = self.lost()
        self.login(self.outsider)
        self.post(f"{LF}cases/{case['id']}/sightings/", {
            "description": "x", "location_text": "y", "seen_at": timezone.now().isoformat(),
        }, 404)

    def test_rejected_never_appears(self):
        case = self.lost()
        body = self.sighting(case)
        self.as_staff()
        self.post(f"{LF}ops/sightings/{body['id']}/review/", {"approve": False})
        self.login(self.parent)
        self.assertEqual(self.get(f"{LF}cases/{case['id']}/")["sightings"], [])


class PhotoTests(LFTestCase):
    def upload(self, case, data, code=201, name="p.jpg", **extra):
        with mock.patch(PUSH, return_value=SENT):
            response = self.client.post(
                f"{LF}cases/{case['id']}/attachments/",
                {"photo": SimpleUploadedFile(name, data), **extra}, format="multipart",
            )
        self.assertEqual(response.status_code, code, response.content)
        return response.json().get("data")

    def test_a_photo_is_served_only_through_the_check(self):
        case = self.lost()
        self.login(self.parent)
        body = self.upload(case, jpeg())
        url = f"{LF}attachments/{body['id']}/"
        response = self.client.get(url)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertIn("no-store", response["Cache-Control"])
        self.login(self.outsider)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.login(self.volunteer)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(url).status_code, 401)

    def test_a_childs_photo_never_reaches_an_unrelated_family_member(self):
        case = self.linked()
        self.login(self.parent)
        body = self.upload(case, jpeg())
        self.login(self.relative)
        self.assertEqual(self.client.get(f"{LF}attachments/{body['id']}/").status_code, 404)

    def test_nothing_is_stored_in_public_media(self):
        field_names = [f.name for f in CaseAttachment._meta.get_fields()]
        self.assertIn("data", field_names)
        self.assertNotIn("file", field_names)
        self.assertNotIn("image", field_names)

    def test_hidden_data_is_stripped(self):
        case = self.lost()
        self.login(self.parent)
        raw = jpeg(exif=True)
        self.assertIn(b"SecretCameraMaker", raw)
        body = self.upload(case, raw)
        stored = bytes(CaseAttachment.objects.get(pk=body["id"]).data)
        self.assertNotIn(b"SecretCameraMaker", stored)

    def test_bad_files_are_refused(self):
        case = self.lost()
        self.login(self.parent)
        self.upload(case, b"<svg onload=alert(1)>", 409)
        self.upload(case, b"\xff\xd8\xff not really a jpeg", 409)
        self.upload(case, b"GIF89a....", 409)

    def test_a_retried_upload_isnt_stored_twice(self):
        case = self.lost()
        self.login(self.parent)
        cid = str(uuid.uuid4())
        self.upload(case, jpeg(), client_id=cid)
        self.upload(case, jpeg(), client_id=cid)
        self.assertEqual(CaseAttachment.objects.count(), 1)

    def test_a_case_has_a_limit(self):
        case = self.lost()
        self.login(self.parent)
        for _ in range(CaseAttachment.MAX_PER_CASE):
            self.upload(case, jpeg())
        self.upload(case, jpeg(), 409)

    def test_viewing_by_staff_is_audited(self):
        case = self.lost()
        self.login(self.parent)
        body = self.upload(case, jpeg())
        self.as_staff()
        self.client.get(f"{LF}attachments/{body['id']}/")
        self.assertTrue(CaseAudit.objects.filter(action="attachment_viewed").exists())


class LocationPrivacyTests(LFTestCase):
    def test_adult_consent_controls_their_familys_view(self):
        self.login(self.other_parent)
        mother = FamilyMember.objects.get(user=self.other_parent)
        self.login(self.parent)
        case = self.post(
            f"{LF}cases/", self.lost_body(member_id=str(mother.pk), family_id=self.fid), 201,
        )
        self.login(self.relative)
        self.assertIsNone(self.get(f"{LF}cases/{case['id']}/")["latitude"])
        FamilyMember.objects.filter(pk=mother.pk).update(location_sharing_consent=True)
        self.assertIsNotNone(self.get(f"{LF}cases/{case['id']}/")["latitude"])

    def test_the_reporter_sees_what_they_sent(self):
        case = self.lost()
        self.assertEqual(self.get(f"{LF}cases/{case['id']}/")["latitude"], 19.9975)


class QrIntegrationTests(LFTestCase):
    def scan_confirm(self, situation="separated"):
        self.login(self.parent)
        response = self.client.post(f"{SAFETY}circles/{self.fid}/members/{self.child['id']}/qr/", {}, format="json")
        token = response.json()["data"]["payload"].partition("#t=")[2]
        self.login(self.volunteer)
        scan = self.post(f"{SAFETY}scan/resolve/", {"token": token})
        return scan, situation

    def confirm(self, situation="separated", expect=201):
        scan, situation = self.scan_confirm(situation)
        self.post(
            f"{SAFETY}scan/{scan['scan_id']}/confirm/",
            {"situation": situation, "confirmed": True, "note": "Help desk 3"}, expect,
        )

    def test_a_scan_alone_creates_nothing(self):
        self.scan_confirm()
        self.assertFalse(LostFoundCase.objects.exists())

    def test_a_confirmed_scan_opens_a_linked_case(self):
        self.confirm()
        case = LostFoundCase.objects.get()
        self.assertEqual((case.case_type, str(case.member_id), str(case.family_id)), ("found", self.child["id"], self.fid))
        self.assertEqual(case.reporter, self.volunteer)
        self.assertEqual(case.person_name, "Aarav")

    def test_a_suspicious_scan_opens_nothing(self):
        self.confirm("suspicious", 200)
        self.assertFalse(LostFoundCase.objects.exists())

    def test_repeated_scans_dont_duplicate_cases(self):
        self.confirm()
        self.confirm(expect=200)
        self.assertEqual(LostFoundCase.objects.count(), 1)

    def test_a_different_situation_adds_to_the_same_case(self):
        self.confirm()
        self.confirm("medical")
        self.assertEqual(LostFoundCase.objects.count(), 1)
        self.assertEqual(CaseSighting.objects.count(), 1)

    def test_an_open_lost_report_gets_a_suggestion_not_a_confirmation(self):
        lost = self.linked()
        self.confirm()
        match = CaseMatch.objects.get()
        self.assertEqual(str(match.lost_case_id), lost["id"])
        self.assertEqual(match.state, "suggested")
        self.assertIn("doesn't prove", match.reasons[0]["detail"])
        self.assertEqual(LostFoundCase.objects.get(pk=lost["id"]).status, "SUBMITTED")

    def test_the_family_can_see_it_and_a_stranger_cant(self):
        self.confirm()
        case = LostFoundCase.objects.get()
        self.login(self.parent)
        self.get(f"{LF}cases/{case.pk}/")
        self.login(self.outsider)
        self.get(f"{LF}cases/{case.pk}/", 404)

    def test_a_failure_here_doesnt_lose_the_alert(self):
        with mock.patch("apps.lostfound.receivers.services.case_from_alert", side_effect=RuntimeError("x")):
            self.confirm()
        self.assertFalse(LostFoundCase.objects.exists())
        from apps.safety.models import SafetyAlert
        self.assertTrue(SafetyAlert.objects.exists())

    def test_a_verified_qr_case_can_be_reunited(self):
        self.confirm()
        case = LostFoundCase.objects.get()
        self.as_staff()
        url = f"{LF}ops/cases/{case.pk}/"
        self.post(f"{url}status/", {"status": "VERIFICATION_REQUIRED", "reason": "Checking the family"})
        self.post(f"{url}verify/", {"method": "family_in_person", "remarks": "Mother identified him at desk"})
        self.post(f"{url}reunite/", {
            "method": "id_document", "remarks": "Checked ID and the boy knew her",
            "identity_checked": True, "person_recognised": True,
        })
        self.assertEqual(LostFoundCase.objects.get().status, "REUNITED")


class NotificationTests(LFTestCase):
    def setUp(self):
        super().setUp()
        self.lf_push = mock.patch(PUSH, return_value=SENT)

    def test_a_report_tells_the_reporter_and_staff(self):
        self.lost()
        events = set(CaseNotification.objects.values_list("event", flat=True))
        self.assertEqual(events, {"submitted", "staff_new"})
        users = set(CaseNotification.objects.values_list("user", flat=True))
        self.assertEqual(users, {self.parent.pk, self.staff.pk})

    def test_text_never_holds_personal_details(self):
        calls = []

        def capture(category, build, **kwargs):
            calls.append((category, build("en"), build("hi"), build("mr"), kwargs))
            return SENT

        with mock.patch(PUSH, side_effect=capture):
            self.login(self.parent)
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(f"{LF}cases/", self.lost_body(), format="json")
        self.assertTrue(calls)
        text = str([c[1:4] for c in calls])
        for private in ("Aarav", "Ramkund", "Blue", "Son"):
            self.assertNotIn(private, text)
        self.assertEqual(calls[0][0], "safety_alerts", "existing preferences apply")
        self.assertEqual(calls[0][4]["data"]["type"], "lostfound_case")

    def test_the_same_event_isnt_sent_twice(self):
        case = self.lost()
        self.as_staff()
        stored = LostFoundCase.objects.get(pk=case["id"])
        notifications.notify_family(stored, "reviewed")
        notifications.notify_family(stored, "reviewed")
        self.assertEqual(CaseNotification.objects.filter(event="reviewed").count(), 1)

    def test_each_lifecycle_step_notifies(self):
        lost, _, match = self.confirmed()
        self.post(f"{LF}ops/cases/{lost['id']}/reunite/", ReunionTests.REUNION)
        events = set(CaseNotification.objects.filter(for_staff=False).values_list("event", flat=True))
        self.assertLessEqual({"submitted", "confirmed", "reunited"}, events)

    def test_a_match_tells_the_family_only_if_staff_approve_that(self):
        _, _, match = self.pair()
        self.as_staff()
        self.post(f"{LF}ops/matches/{match.pk}/approve/", {"notify_family": False})
        self.assertFalse(CaseNotification.objects.filter(event="match").exists())

    def test_an_approved_notice_goes_out(self):
        _, _, match = self.pair()
        self.as_staff()
        self.post(f"{LF}ops/matches/{match.pk}/approve/", {"notify_family": True})
        self.assertTrue(CaseNotification.objects.filter(event="match").exists())

    def test_an_info_request_notifies(self):
        case = self.lost()
        self.as_staff()
        self.post(f"{LF}ops/cases/{case['id']}/notes/", {"kind": "info_request", "body": "Any photo?"}, 201)
        self.assertTrue(CaseNotification.objects.filter(event="info_needed").exists())

    def test_a_failed_send_is_kept_and_retried(self):
        self.login(self.parent)
        down = {"status": "disabled", "success": 0, "failure": 1, "deactivated": 0}
        with mock.patch(PUSH, return_value=down):
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(f"{LF}cases/", self.lost_body(), format="json")
        row = CaseNotification.objects.filter(user=self.parent).get()
        self.assertEqual((row.state, row.attempts), ("pending", 1))
        CaseNotification.objects.update(next_attempt_at=timezone.now() - timedelta(minutes=1))
        with mock.patch(PUSH, return_value=SENT):
            self.assertEqual(notifications.retry_pending(), 2)
        row.refresh_from_db()
        self.assertEqual(row.state, "sent")

    def test_it_gives_up_eventually(self):
        self.lost()
        row = CaseNotification.objects.filter(user=self.parent).get()
        CaseNotification.objects.update(
            state="pending", attempts=4, next_attempt_at=timezone.now() - timedelta(minutes=1),
        )
        with mock.patch(PUSH, side_effect=RuntimeError("down")):
            notifications.retry_pending()
        row.refresh_from_db()
        self.assertEqual(row.state, "failed")

    def test_no_device_isnt_retried(self):
        self.login(self.parent)
        empty = {"status": "no_devices", "success": 0, "failure": 0, "deactivated": 0}
        with mock.patch(PUSH, return_value=empty):
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(f"{LF}cases/", self.lost_body(), format="json")
        self.assertEqual(CaseNotification.objects.filter(user=self.parent).get().state, "no_device")

    def test_a_push_failure_never_loses_a_report(self):
        self.login(self.parent)
        with mock.patch(PUSH, side_effect=RuntimeError("down")):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(f"{LF}cases/", self.lost_body(), format="json")
        self.assertEqual(response.status_code, 201)

    def test_logs_hold_no_details(self):
        with self.assertLogs("apps.lostfound", level=logging.DEBUG) as logs, mock.patch(
            PUSH, side_effect=RuntimeError("down"),
        ):
            self.login(self.parent)
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(f"{LF}cases/", self.lost_body(), format="json")
        text = "\n".join(logs.output)
        for private in ("Aarav", "Ramkund", "9100"):
            self.assertNotIn(private, text)


class OpsTests(LFTestCase):
    def test_filter_and_search(self):
        lost = self.lost()
        self.found()
        self.as_staff()
        self.assertEqual(self.get(f"{LF}ops/cases/")["count"], 2)
        self.assertEqual(self.get(f"{LF}ops/cases/?type=lost")["count"], 1)
        self.assertEqual(self.get(f"{LF}ops/cases/?status=CLOSED")["count"], 0)
        self.assertEqual(self.get(f"{LF}ops/cases/?q={lost['reference']}")["count"], 1)
        self.assertEqual(self.get(f"{LF}ops/cases/?q=LF-NOPE")["count"], 0)

    def test_search_is_exact_so_it_cant_browse(self):
        lost = self.lost()
        self.as_staff()
        self.assertEqual(self.get(f"{LF}ops/cases/?q={lost['reference'][:5]}")["count"], 0)

    def test_results_are_paged(self):
        for _ in range(27):
            LostFoundCase.objects.create(case_type="lost", event_at=timezone.now(), location_text="x")
        self.as_staff()
        page = self.get(f"{LF}ops/cases/")
        self.assertEqual((len(page["results"]), page["has_next"]), (25, True))

    def test_assignment(self):
        case = self.lost()
        self.as_staff()
        self.post(f"{LF}ops/cases/{case['id']}/assign/")
        self.assertEqual(self.get(f"{LF}ops/cases/?mine=true")["count"], 1)

    def test_the_guarded_statuses_are_never_offered(self):
        case = self.lost()
        self.as_staff()
        allowed = self.get(f"{LF}ops/cases/{case['id']}/")["allowed_statuses"]
        self.assertNotIn("REUNITED", allowed)
        self.assertNotIn("MATCH_CONFIRMED", allowed)

    def test_a_found_child_is_flagged(self):
        self.login(self.volunteer)
        self.post(f"{LF}found/", self.found_body(found_category="child_alone"), 201)
        self.as_staff()
        self.assertTrue(self.get(f"{LF}ops/cases/")["results"][0]["is_vulnerable"])


class CapabilityTests(LFTestCase):
    def test_roles(self):
        for user, expected in (
            (self.parent, (None, False, False, False)),
            (self.volunteer, ("volunteer", True, False, False)),
            (self.desk, ("help_desk", True, True, False)),
            (self.staff, ("safety_staff", True, True, True)),
        ):
            self.login(user)
            me = self.get(f"{LF}me/")
            self.assertEqual((me["role"], me["can_report_found"], me["can_operate"], me["is_staff"]), expected)


class AdminTests(LFTestCase):
    def test_nothing_private_is_shown_and_nothing_can_be_edited(self):
        case = self.lost()
        admin_user = User.objects.create_superuser("lf-admin@example.org", "+919100000068", "pw-for-tests")
        client = self.client_class()
        client.force_login(admin_user)
        pk = case["id"]
        for url in ("/admin/lostfound/lostfoundcase/", f"/admin/lostfound/lostfoundcase/{pk}/change/"):
            response = client.get(url)
            self.assertEqual(response.status_code, 200, url)
            self.assertNotContains(response, "Ramkund")
            self.assertNotContains(response, "Blue kurta")
        self.assertNotIn(models.CaseAttachment, site._registry)
        self.assertNotIn(models.CaseNote, site._registry)
        self.assertFalse(site._registry[models.LostFoundCase].has_change_permission(None))


class PolicyTests(LFTestCase):
    def test_a_found_report_tells_no_helper_as_family(self):
        self.found()
        case = LostFoundCase.objects.get()
        self.assertEqual(policy.family_recipients(case), [])

    def test_status_enum_has_every_required_state(self):
        self.assertEqual(set(Status.values), {
            "SUBMITTED", "UNDER_REVIEW", "VERIFICATION_REQUIRED", "POTENTIAL_MATCH_FOUND",
            "MATCH_CONFIRMED", "REUNITED", "CLOSED", "REJECTED",
        })
