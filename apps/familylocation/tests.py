import logging
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.authentication.models import User
from apps.family.models import FamilyAuditLog, FamilyMember, GuardianLink
from apps.familylocation import services
from apps.familylocation.models import LocationRecipient, LocationSession, MemberLocation
from apps.safety.models import SafetyHelper

FAMILY = "/api/family/"
LOC = "/api/location/"
PUSH = "apps.familylocation.services.send_localized"
SENT = {"status": "sent", "success": 1, "failure": 0, "deactivated": 0}


@override_settings(
    SAFETY_REQUIRE_HTTPS=False, LOCATION_MAX_SHARE_HOURS=12, LOCATION_LIVE_SECONDS=120,
    LOCATION_RECENT_SECONDS=600, LOCATION_POLL_SECONDS=20, LOCATION_UPDATE_SECONDS=30,
    LOCATION_DISTANCE_METRES=25, LOCATION_STALE_NOTICE_MINUTES=30, LOCATION_SESSION_RETENTION_DAYS=7,
)
class LocTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.organizer = self.user("71", "Suresh More")
        self.adult = self.user("72", "Asha More")
        self.relative = self.user("73", "Ravi More")
        self.outsider = self.user("74", "Stranger")
        self.client = APIClient()
        self.login(self.organizer)
        self.family = self.post(f"{FAMILY}circles/", {"name": "More Family"}, 201)
        self.fid = self.family["id"]
        self.child = self.post(f"{FAMILY}circles/{self.fid}/members/", {
            "full_name": "Aarav More", "kind": "dependent_child", "relationship": "son", "age_group": "6_12",
        }, 201)
        self.adult_member = self.join(self.adult)
        self.relative_member = self.join(self.relative)
        self.org_member = FamilyMember.objects.get(user=self.organizer)

    def user(self, tail, name):
        return User.objects.create_user(phone_number=f"+9191000000{tail}", full_Name=name)

    def login(self, user):
        self.client.force_authenticate(user)

    def join(self, user):
        self.login(self.organizer)
        code = self.post(f"{FAMILY}circles/{self.fid}/invitations/", {"relationship": "sibling"}, 201)["code"]
        self.login(user)
        joined = self.post(f"{FAMILY}invitations/accept/", {"code": code})
        return FamilyMember.objects.get(pk=joined["member_id"])

    def post(self, url, body=None, code=200):
        with mock.patch(PUSH, return_value=SENT), self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url, body or {}, format="json")
        self.assertEqual(response.status_code, code, response.content)
        return response.json().get("data") if response.content else None

    def get(self, url, code=200):
        response = self.client.get(url)
        self.assertEqual(response.status_code, code, response.content)
        return response.json().get("data")

    def start(self, user=None, viewers=None, member=None, code=201, **extra):
        self.login(user or self.adult)
        ids = viewers if viewers is not None else [self.org_member.pk]
        body = {
            "recipient_ids": [str(i) for i in ids], "duration_minutes": 60, "consent": True, **extra,
        }
        if member:
            body["member_id"] = str(member)
        return self.post(f"{LOC}circles/{self.fid}/sessions/", body, code)

    def fix(self, session, code=200, age=0, **extra):
        body = {
            "latitude": "19.997500", "longitude": "73.789800", "accuracy_m": 12,
            "captured_at": (timezone.now() - timedelta(seconds=age)).isoformat(), **extra,
        }
        return self.post(f"{LOC}sessions/{session['id']}/update/", body, code)

    def feed(self, user):
        self.login(user)
        return self.get(f"{LOC}circles/{self.fid}/feed/")

    def person(self, user, member_id):
        people = self.feed(user)["people"]
        return next((p for p in people if p["member_id"] == str(member_id)), None)


class StartTests(LocTestCase):
    def test_an_adult_starts_their_own(self):
        session = self.start()
        self.assertEqual(session["status"], "active")
        self.assertEqual([r["name"] for r in session["recipients"]], ["Suresh More"])
        self.assertAlmostEqual(session["remaining_seconds"], 3600, delta=5)

    def test_needs_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f"{LOC}circles/{self.fid}/feed/").status_code, 401)

    def test_needs_explicit_consent(self):
        self.start(consent=False, code=400)
        self.login(self.adult)
        self.post(f"{LOC}circles/{self.fid}/sessions/", {
            "recipient_ids": [str(self.org_member.pk)], "duration_minutes": 60,
        }, 400)
        self.assertFalse(LocationSession.objects.exists())

    def test_an_organizer_cant_start_an_adults_sharing(self):
        self.start(self.organizer, viewers=[self.org_member.pk], member=self.adult_member.pk, code=403)
        self.assertFalse(LocationSession.objects.exists())

    def test_a_guardian_can_start_a_dependents(self):
        GuardianLink.objects.create(dependent_id=self.child["id"], guardian=self.adult_member)
        session = self.start(self.adult, viewers=[self.org_member.pk], member=self.child["id"])
        self.assertEqual(session["member_id"], self.child["id"])

    def test_someone_unrelated_to_a_dependent_cant(self):
        self.start(self.relative, viewers=[self.org_member.pk], member=self.child["id"], code=403)

    def test_a_dependents_location_only_goes_to_those_responsible(self):
        self.start(self.organizer, viewers=[self.relative_member.pk], member=self.child["id"], code=400)

    def test_viewers_must_be_in_the_family(self):
        self.login(self.outsider)
        other = self.post(f"{FAMILY}circles/", {"name": "Other"}, 201)
        me = FamilyMember.objects.get(user=self.outsider)
        self.start(viewers=[me.pk], code=400)
        self.assertTrue(other)

    def test_someone_must_be_chosen(self):
        self.start(viewers=[], code=400)

    def test_a_person_cant_choose_themselves_as_a_viewer(self):
        self.start(viewers=[self.adult_member.pk], code=400)

    def test_durations(self):
        for minutes in (30, 60, 180, 360):
            session = self.start(duration_minutes=minutes)
            self.assertAlmostEqual(session["remaining_seconds"], minutes * 60, delta=5)
            self.post(f"{LOC}sessions/{session['id']}/stop/")
        self.start(duration_minutes=5, code=409)

    def test_until_stopped_still_has_a_limit(self):
        session = self.start(until_stopped=True, duration_minutes=None)
        self.assertAlmostEqual(session["remaining_seconds"], 12 * 3600, delta=5)

    def test_a_person_has_one_session_at_a_time(self):
        self.start()
        self.start(code=409)

    def test_one_phone_reports_one_session(self):
        self.login(self.organizer)
        self.start(self.organizer, viewers=[self.adult_member.pk])
        self.start(self.organizer, viewers=[self.org_member.pk], member=self.child["id"], code=409)

    def test_the_session_says_which_phone_reports(self):
        GuardianLink.objects.create(dependent_id=self.child["id"], guardian=self.adult_member)
        session = self.start(self.organizer, viewers=[self.adult_member.pk], member=self.child["id"])
        self.assertTrue(session["reports_from_me"])
        self.login(self.adult)
        self.assertFalse(self.get(f"{LOC}sessions/{session['id']}/")["reports_from_me"])

    def test_the_database_allows_only_one(self):
        self.start()
        with self.assertRaises(IntegrityError), transaction.atomic():
            LocationSession.objects.create(
                family_id=self.fid, member=self.adult_member, started_by=self.adult, expires_at=timezone.now(),
            )

    def test_a_qr_scan_cant_start_sharing(self):
        helper = self.user("75", "Helper")
        SafetyHelper.objects.create(user=helper, role="volunteer")
        self.start(helper, code=404)

    def test_eligible_lists(self):
        self.login(self.adult)
        names = {m["name"] for m in self.get(f"{LOC}circles/{self.fid}/eligible/")["people"]}
        self.assertEqual(names, {"Suresh More", "Ravi More"})
        self.login(self.organizer)
        names = {m["name"] for m in self.get(f"{LOC}circles/{self.fid}/eligible/?member_id={self.child['id']}")["people"]}
        self.assertEqual(names, {"Suresh More"}, "only those responsible for the child")
        self.login(self.relative)
        self.get(f"{LOC}circles/{self.fid}/eligible/?member_id={self.child['id']}", 403)


class UpdateTests(LocTestCase):
    def test_stores_one_position(self):
        session = self.start()
        self.assertTrue(self.fix(session)["accepted"])
        self.fix(session)
        self.assertEqual(MemberLocation.objects.count(), 1, "no history")

    def test_an_older_fix_cant_replace_a_newer_one(self):
        session = self.start()
        self.fix(session)
        stored = MemberLocation.objects.get().captured_at
        self.assertFalse(self.fix(session, age=300, latitude="20.100000")["accepted"])
        location = MemberLocation.objects.get()
        self.assertEqual(location.captured_at, stored)
        self.assertEqual(str(location.latitude), "19.997500")

    def test_a_delayed_fix_keeps_its_own_time(self):
        session = self.start()
        self.fix(session, age=900)
        self.assertEqual(self.person(self.organizer, self.adult_member.pk)["state"], "last_known")

    def test_only_the_session_owner_can_report(self):
        session = self.start()
        self.login(self.organizer)
        self.fix(session, code=404)
        self.login(self.outsider)
        self.fix(session, code=404)

    def test_bad_positions_are_refused(self):
        session = self.start()
        for change in (
            {"latitude": "91"}, {"longitude": "181"}, {"latitude": "0", "longitude": "0"},
            {"accuracy_m": -1}, {"heading": 400},
            {"captured_at": (timezone.now() + timedelta(hours=1)).isoformat()},
        ):
            self.fix(session, code=400, **change)

    def test_a_paused_session_refuses_updates(self):
        session = self.start()
        self.post(f"{LOC}sessions/{session['id']}/pause/")
        self.fix(session, code=410)

    def test_a_stopped_session_refuses_updates(self):
        session = self.start()
        self.post(f"{LOC}sessions/{session['id']}/stop/")
        self.fix(session, code=410)

    def test_an_expired_session_refuses_updates(self):
        session = self.start()
        LocationSession.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.fix(session, code=410)
        self.assertEqual(LocationSession.objects.get().status, "expired")

    def test_updates_are_rate_limited(self):
        session = self.start()
        with mock.patch("apps.familylocation.views.UpdateThrottle.rate", "3/hour"):
            codes = [
                self.client.post(f"{LOC}sessions/{session['id']}/update/", {}, format="json").status_code
                for _ in range(6)
            ]
        self.assertIn(429, codes)


class FeedTests(LocTestCase):
    def test_a_chosen_viewer_sees_it(self):
        session = self.start()
        self.fix(session)
        seen = self.person(self.organizer, self.adult_member.pk)
        self.assertEqual(seen["state"], "live")
        self.assertEqual(seen["latitude"], 19.9975)
        self.assertEqual(seen["accuracy_m"], 12)

    def test_someone_not_chosen_sees_nothing(self):
        session = self.start()
        self.fix(session)
        self.assertIsNone(self.person(self.relative, self.adult_member.pk))
        self.assertEqual(self.feed(self.relative)["ended"], [])

    def test_being_organizer_isnt_enough(self):
        session = self.start(viewers=[self.relative_member.pk])
        self.fix(session)
        self.assertIsNone(self.person(self.organizer, self.adult_member.pk))

    def test_outsiders_get_404(self):
        session = self.start()
        self.login(self.outsider)
        self.get(f"{LOC}circles/{self.fid}/feed/", 404)
        self.get(f"{LOC}sessions/{session['id']}/", 404)
        self.get(f"{LOC}circles/{self.fid}/sessions/", 404)

    def test_a_viewer_cant_control_someone_elses_session(self):
        session = self.start()
        self.login(self.organizer)
        for action in ("pause", "resume", "stop", "recipients", "duration"):
            self.post(f"{LOC}sessions/{session['id']}/{action}/", {}, 404)
        self.get(f"{LOC}sessions/{session['id']}/", 404)

    def test_freshness_follows_the_fix_time(self):
        session = self.start()
        for age, state in ((10, "live"), (300, "recent"), (1200, "last_known")):
            MemberLocation.objects.all().delete()
            self.login(self.adult)
            self.fix(session, age=age)
            self.assertEqual(self.person(self.organizer, self.adult_member.pk)["state"], state)

    def test_ages_come_from_the_server_clock(self):
        session = self.start()
        self.fix(session, age=300)
        seen = self.person(self.organizer, self.adult_member.pk)
        self.assertAlmostEqual(seen["age_seconds"], 300, delta=5)
        self.assertAlmostEqual(seen["remaining_seconds"], 3600, delta=5)

    def test_no_fix_yet_is_unavailable(self):
        self.start()
        seen = self.person(self.organizer, self.adult_member.pk)
        self.assertEqual(seen["state"], "unavailable")
        self.assertIsNone(seen["latitude"])

    def test_paused_shows_no_position(self):
        session = self.start()
        self.fix(session)
        self.post(f"{LOC}sessions/{session['id']}/pause/")
        seen = self.person(self.organizer, self.adult_member.pk)
        self.assertEqual(seen["state"], "paused")
        self.assertIsNone(seen["latitude"])

    def test_resuming_brings_it_back(self):
        session = self.start()
        self.fix(session)
        self.post(f"{LOC}sessions/{session['id']}/pause/")
        self.login(self.adult)
        self.post(f"{LOC}sessions/{session['id']}/resume/")
        self.fix(session)
        self.assertEqual(self.person(self.organizer, self.adult_member.pk)["state"], "live")

    def test_stopping_deletes_the_position_immediately(self):
        session = self.start()
        self.fix(session)
        self.post(f"{LOC}sessions/{session['id']}/stop/")
        self.assertFalse(MemberLocation.objects.exists())
        self.assertIsNone(self.person(self.organizer, self.adult_member.pk))
        ended = self.feed(self.organizer)["ended"]
        self.assertEqual(ended[0]["state"], "stopped")
        self.assertNotIn("latitude", ended[0])

    def test_expiry_stops_exposure_without_any_sweep(self):
        session = self.start()
        self.fix(session)
        LocationSession.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertIsNone(self.person(self.organizer, self.adult_member.pk))
        self.assertFalse(MemberLocation.objects.exists())

    def test_removing_a_viewer_takes_effect_immediately(self):
        session = self.start(viewers=[self.org_member.pk, self.relative_member.pk])
        self.fix(session)
        self.post(f"{LOC}sessions/{session['id']}/recipients/", {"recipient_ids": [str(self.relative_member.pk)]})
        self.assertIsNone(self.person(self.organizer, self.adult_member.pk))
        self.assertIsNotNone(self.person(self.relative, self.adult_member.pk))

    def test_a_guardian_removed_later_loses_access(self):
        link = GuardianLink.objects.create(dependent_id=self.child["id"], guardian=self.adult_member)
        session = self.start(self.organizer, viewers=[self.adult_member.pk], member=self.child["id"])
        self.fix(session)
        self.assertIsNotNone(self.person(self.adult, self.child["id"]))
        link.delete()
        self.assertIsNone(self.person(self.adult, self.child["id"]))

    def test_a_viewer_who_leaves_loses_access(self):
        session = self.start(viewers=[self.relative_member.pk])
        self.fix(session)
        self.login(self.relative)
        self.post(f"{FAMILY}circles/{self.fid}/leave/", code=204)
        self.get(f"{LOC}circles/{self.fid}/feed/", 404)

    def test_the_owner_sees_themselves(self):
        session = self.start()
        self.fix(session)
        me = self.person(self.adult, self.adult_member.pk)
        self.assertTrue(me["is_me"])

    def test_responses_arent_cached_and_set_the_polling_rate(self):
        self.login(self.adult)
        response = self.client.get(f"{LOC}circles/{self.fid}/feed/")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response.json()["data"]["poll_seconds"], 20)

    def test_views_are_recorded_at_most_hourly_without_coordinates(self):
        session = self.start()
        self.fix(session)
        for _ in range(3):
            self.feed(self.organizer)
        logs = FamilyAuditLog.objects.filter(action="location_viewed")
        self.assertEqual(logs.count(), 1)
        self.assertIsNotNone(LocationRecipient.objects.get().last_viewed_at)
        self.assertNotIn("19.99", str(list(FamilyAuditLog.objects.values_list("details", flat=True))))

    @override_settings(SAFETY_REQUIRE_HTTPS=True)
    def test_plain_http_is_refused_when_required(self):
        self.login(self.adult)
        self.get(f"{LOC}circles/{self.fid}/feed/", 400)


class ManagementTests(LocTestCase):
    def test_changing_duration(self):
        session = self.start()
        changed = self.post(f"{LOC}sessions/{session['id']}/duration/", {"duration_minutes": 180})
        self.assertAlmostEqual(changed["remaining_seconds"], 180 * 60, delta=5)

    def test_recipients_are_checked(self):
        session = self.start()
        self.post(f"{LOC}sessions/{session['id']}/recipients/", {"recipient_ids": []}, 400)
        self.post(f"{LOC}sessions/{session['id']}/recipients/", {"recipient_ids": ["bad"]}, 400)
        self.post(f"{LOC}sessions/{session['id']}/recipients/", {"recipient_ids": [str(self.adult_member.pk)]}, 400)

    def test_lists_only_your_own(self):
        self.start()
        self.login(self.relative)
        self.assertEqual(self.get(f"{LOC}circles/{self.fid}/sessions/"), [])
        self.login(self.adult)
        self.assertEqual(len(self.get(f"{LOC}circles/{self.fid}/sessions/")), 1)

    def test_an_ended_session_cant_be_resumed(self):
        session = self.start()
        self.post(f"{LOC}sessions/{session['id']}/stop/")
        self.post(f"{LOC}sessions/{session['id']}/resume/", code=409)

    def test_changes_are_audited(self):
        session = self.start()
        self.post(f"{LOC}sessions/{session['id']}/pause/")
        self.post(f"{LOC}sessions/{session['id']}/stop/")
        actions = set(FamilyAuditLog.objects.values_list("action", flat=True))
        self.assertLessEqual({"location_started", "location_paused", "location_stopped"}, actions)


class NotificationTests(LocTestCase):
    def texts(self, push):
        return str([push.call_args.args[1](lang) for lang in ("en", "hi", "mr")])

    def test_starting_and_stopping_tell_only_chosen_viewers(self):
        self.login(self.adult)
        with mock.patch(PUSH, return_value=SENT) as push, self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f"{LOC}circles/{self.fid}/sessions/", {
                "recipient_ids": [str(self.org_member.pk)], "duration_minutes": 60, "consent": True,
            }, format="json")
        self.assertEqual(push.call_args.kwargs["users"], [self.organizer.pk])
        session = response.json()["data"]
        with mock.patch(PUSH, return_value=SENT) as push, self.captureOnCommitCallbacks(execute=True):
            self.client.post(f"{LOC}sessions/{session['id']}/stop/", {}, format="json")
        self.assertEqual(push.call_count, 1)

    def test_an_update_never_notifies(self):
        session = self.start()
        with mock.patch(PUSH) as push:
            self.fix_without_patch(session)
        push.assert_not_called()

    def fix_without_patch(self, session):
        self.client.post(f"{LOC}sessions/{session['id']}/update/", {
            "latitude": "19.9975", "longitude": "73.7898", "captured_at": timezone.now().isoformat(),
        }, format="json")

    def test_notices_hold_no_coordinates_or_names(self):
        session = self.start()
        self.fix(session)
        with mock.patch(PUSH, return_value=SENT) as push, self.captureOnCommitCallbacks(execute=True):
            self.client.post(f"{LOC}sessions/{session['id']}/stop/", {}, format="json")
        text = self.texts(push)
        for private in ("19.99", "73.78", "Asha"):
            self.assertNotIn(private, text)

    def test_expiry_notifies_once(self):
        self.start()
        LocationSession.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        with mock.patch(PUSH, return_value=SENT) as push, self.captureOnCommitCallbacks(execute=True):
            services.sweep()
            services.sweep()
        self.assertEqual(push.call_count, 1)

    def test_a_long_silence_tells_the_owner_once(self):
        session = self.start()
        self.fix(session, age=3600)
        LocationSession.objects.update(created_at=timezone.now() - timedelta(hours=2))
        with mock.patch(PUSH, return_value=SENT) as push:
            services.sweep()
            services.sweep()
        self.assertEqual(push.call_count, 1)
        self.assertEqual(push.call_args.kwargs["users"], [self.adult.pk])

    def test_a_push_failure_changes_nothing(self):
        self.login(self.adult)
        with mock.patch(PUSH, side_effect=RuntimeError("down")), self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f"{LOC}circles/{self.fid}/sessions/", {
                "recipient_ids": [str(self.org_member.pk)], "duration_minutes": 60, "consent": True,
            }, format="json")
        self.assertEqual(response.status_code, 201)

    def test_logs_hold_no_coordinates(self):
        with self.assertLogs("apps.familylocation", level=logging.DEBUG) as logs:
            with mock.patch(PUSH, side_effect=RuntimeError("down")), self.captureOnCommitCallbacks(execute=True):
                self.login(self.adult)
                self.client.post(f"{LOC}circles/{self.fid}/sessions/", {
                    "recipient_ids": [str(self.org_member.pk)], "duration_minutes": 60, "consent": True,
                }, format="json")
        self.assertNotIn("19.99", "\n".join(logs.output))


class SweepTests(LocTestCase):
    def test_old_ended_sessions_are_removed(self):
        session = self.start()
        self.post(f"{LOC}sessions/{session['id']}/stop/")
        LocationSession.objects.update(ended_at=timezone.now() - timedelta(days=8))
        services.sweep()
        self.assertFalse(LocationSession.objects.exists())

    def test_recent_ones_stay(self):
        session = self.start()
        self.post(f"{LOC}sessions/{session['id']}/stop/")
        services.sweep()
        self.assertTrue(LocationSession.objects.exists())


class LostFoundTests(LocTestCase):
    def report(self):
        self.login(self.organizer)
        with mock.patch("apps.lostfound.notifications.send_localized", return_value=SENT):
            response = self.client.post("/api/lostfound/cases/", {
                "relationship": "Sister", "clothing_description": "Green saree", "location_text": "Ramkund",
                "event_at": timezone.now().isoformat(), "member_id": str(self.adult_member.pk), "family_id": self.fid,
            }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def url(self, case):
        return f"{LOC}cases/{case['id']}/"

    def test_a_chosen_viewer_sees_the_shared_position(self):
        session = self.start()
        self.fix(session)
        case = self.report()
        seen = self.get(self.url(case))
        self.assertEqual(seen["state"], "live")
        self.assertEqual(seen["latitude"], 19.9975)

    def test_a_report_doesnt_override_consent(self):
        self.start(viewers=[self.relative_member.pk])
        case = self.report()
        self.login(self.organizer)
        seen = self.get(self.url(case))
        self.assertEqual(seen, {"state": "not_shared"})

    def test_no_session_means_no_location(self):
        case = self.report()
        self.assertEqual(self.get(self.url(case)), {"state": "not_shared"})

    def test_a_report_cant_revive_an_ended_session(self):
        session = self.start()
        self.fix(session)
        self.post(f"{LOC}sessions/{session['id']}/stop/")
        case = self.report()
        self.assertEqual(self.get(self.url(case)), {"state": "not_shared"})

    def test_a_stale_position_says_so(self):
        session = self.start()
        self.fix(session, age=1200)
        case = self.report()
        self.assertEqual(self.get(self.url(case))["state"], "last_known")

    def test_staff_get_no_family_location(self):
        session = self.start()
        self.fix(session)
        case = self.report()
        staff = self.user("76", "Staff")
        SafetyHelper.objects.create(user=staff, role="safety_staff")
        self.login(staff)
        self.assertEqual(self.get(self.url(case)), {"state": "not_shared"})

    def test_strangers_get_404(self):
        case = self.report()
        self.login(self.outsider)
        self.get(self.url(case), 404)

    def test_the_map_links_the_case(self):
        session = self.start()
        self.fix(session)
        case = self.report()
        seen = self.person(self.organizer, self.adult_member.pk)
        self.assertEqual(seen["case"]["reference"], case["reference"])

    def test_the_link_needs_case_access(self):
        session = self.start(viewers=[self.org_member.pk, self.relative_member.pk])
        self.fix(session)
        self.report()
        self.assertIsNotNone(self.person(self.relative, self.adult_member.pk)["case"])
