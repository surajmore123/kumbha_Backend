import logging
from datetime import timedelta
from unittest import mock

import requests
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.authentication.models import User
from apps.family.models import FamilyAuditLog, FamilyMember, GuardianLink
from apps.familylocation.models import LocationSession, MemberLocation
from apps.lostfound.models import CaseAudit, CaseNote, CaseSighting, LostFoundCase, Status
from apps.lostfound.services import record_reunion, verify_case
from apps.reunification import policy, routing, services
from apps.reunification.models import MeetingPoint, ReunificationPlan
from apps.safety.models import SafetyHelper

FAMILY = "/api/family/"
LOC = "/api/location/"
RE = "/api/reunification/"
PUSH = "apps.familylocation.services.send_localized"
LF_PUSH = "apps.lostfound.notifications.send_localized"
RE_PUSH = "apps.reunification.services.send_localized"
SENT = {"status": "sent", "success": 1, "failure": 0, "deactivated": 0}
ORIGIN = {"latitude": 19.99, "longitude": 73.78}
ROUTE = {"distance_m": 840, "duration_s": 660, "polyline": "abc"}
Cat = MeetingPoint.Category
St = MeetingPoint.Status


@override_settings(
    SAFETY_REQUIRE_HTTPS=False, GOOGLE_ROUTES_API_KEY="test-key", LOCATION_MAX_SHARE_HOURS=12,
    LOCATION_LIVE_SECONDS=120, LOCATION_RECENT_SECONDS=600,
)
class ReTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.organizer = self.user("91", "Suresh More")
        self.adult = self.user("92", "Asha More")
        self.relative = self.user("93", "Ravi More")
        self.outsider = self.user("94", "Stranger")
        self.client = APIClient()
        self.login(self.organizer)
        self.family = self.call("post", f"{FAMILY}circles/", {"name": "More Family"}, 201)
        self.fid = self.family["id"]
        self.child = self.call("post", f"{FAMILY}circles/{self.fid}/members/", {
            "full_name": "Aarav More", "kind": "dependent_child", "relationship": "son", "age_group": "6_12",
        }, 201)
        self.adult_member = self.join(self.adult)
        self.relative_member = self.join(self.relative)
        self.org_member = FamilyMember.objects.get(user=self.organizer)
        self.login(self.outsider)
        self.other_family = self.call("post", f"{FAMILY}circles/", {"name": "Other"}, 201)
        self.staff = self.user("95", "Staff")
        SafetyHelper.objects.create(user=self.staff, role="safety_staff")

    def user(self, tail, name):
        return User.objects.create_user(phone_number=f"+9191100000{tail}", full_Name=name)

    def login(self, user):
        self.client.force_authenticate(user)

    def join(self, user):
        self.login(self.organizer)
        code = self.call("post", f"{FAMILY}circles/{self.fid}/invitations/", {"relationship": "sibling"}, 201)["code"]
        self.login(user)
        joined = self.call("post", f"{FAMILY}invitations/accept/", {"code": code})
        return FamilyMember.objects.get(pk=joined["member_id"])

    def call(self, method, url, body=None, code=200):
        with mock.patch(PUSH, return_value=SENT), mock.patch(LF_PUSH, return_value=SENT), \
                mock.patch(RE_PUSH, return_value=SENT), self.captureOnCommitCallbacks(execute=True):
            response = getattr(self.client, method)(url, body or {}, format="json")
        self.assertEqual(response.status_code, code, response.content)
        return response.json().get("data") if response.content else None

    def point(self, name="Ramkund Help Desk", category=Cat.HELP_DESK, status=St.VERIFIED, lat="19.9975", **extra):
        defaults = {
            "source_detail": "Checked in person on 3 Jan" if status == St.VERIFIED else "",
            "source_type": MeetingPoint.Source.FIELD_CHECK if status == St.VERIFIED else MeetingPoint.Source.COMMUNITY,
        }
        return MeetingPoint.objects.create(
            name=name, category=category, status=status, latitude=lat, longitude="73.7898", **{**defaults, **extra},
        )

    def case(self, member=None, reporter=None, vulnerabilities=None, lat="19.9900", status=Status.SUBMITTED, **extra):
        return LostFoundCase.objects.create(
            case_type="lost", reporter=reporter or self.organizer, family_id=self.fid, member=member,
            event_at=timezone.now(), location_text="Near Ramkund", latitude=lat, longitude="73.7800",
            vulnerabilities=vulnerabilities or [], status=status, **extra,
        )

    def child_case(self, **extra):
        return self.case(member=FamilyMember.objects.get(pk=self.child["id"]), vulnerabilities=["child"], **extra)

    def share(self, user, viewers, age=0):
        self.login(user)
        session = self.call("post", f"{LOC}circles/{self.fid}/sessions/", {
            "recipient_ids": [str(v) for v in viewers], "duration_minutes": 60, "consent": True,
        }, 201)
        self.call("post", f"{LOC}sessions/{session['id']}/update/", {
            "latitude": "19.997500", "longitude": "73.789800", "accuracy_m": 12,
            "captured_at": (timezone.now() - timedelta(seconds=age)).isoformat(),
        })
        return session

    def route(self, kind, target, code=200, **extra):
        with mock.patch("apps.reunification.routing.walking_route", return_value=ROUTE) as walk:
            data = self.call("post", f"{RE}route/", {
                "origin": ORIGIN, "kind": kind, "target_id": str(target), **extra,
            }, code)
        self.walk = walk
        return data

    def choose(self, case, point, code=200):
        return self.call("post", f"{RE}cases/{case.pk}/meeting-point/", {"meeting_point_id": str(point.pk)}, code)


class PointTests(ReTestCase):
    def names(self, query=""):
        self.login(self.adult)
        return [p["name"] for p in self.call("get", f"{RE}points/{query}")["results"]]

    def test_there_is_no_seed_data(self):
        self.assertEqual(MeetingPoint.objects.count(), 0)

    def test_needs_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f"{RE}points/").status_code, 401)

    def test_verified_and_community_are_told_apart(self):
        self.point("Desk")
        self.point("Banyan tree", Cat.FAMILY_MEETING, St.COMMUNITY)
        self.login(self.adult)
        rows = {p["name"]: p for p in self.call("get", f"{RE}points/")["results"]}
        self.assertTrue(rows["Desk"]["is_verified"])
        self.assertFalse(rows["Banyan tree"]["is_verified"])
        self.assertFalse(rows["Banyan tree"]["is_official"])

    def test_official_needs_a_verified_official_source(self):
        self.assertFalse(self.point("Checked").is_official)
        self.assertTrue(self.point("Desk", source_type=MeetingPoint.Source.OFFICIAL).is_official)
        self.assertFalse(self.point("X", status=St.COMMUNITY, source_type=MeetingPoint.Source.OFFICIAL).is_official)

    def test_verified_needs_a_source_in_the_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.point(source_detail="")

    def test_filters_by_category_and_verification(self):
        self.point("Desk")
        self.point("Camp", Cat.MEDICAL)
        self.point("Tree", Cat.FAMILY_MEETING, St.COMMUNITY)
        self.assertEqual(self.names("?category=medical"), ["Camp"])
        self.assertEqual(self.names("?verified=true"), ["Camp", "Desk"])
        self.login(self.adult)
        self.call("get", f"{RE}points/?category=nonsense", code=400)

    def test_retired_points_disappear(self):
        self.point("Gone", status=St.RETIRED)
        self.assertEqual(self.names(), [])

    def test_private_points_stay_in_the_family(self):
        self.login(self.adult)
        point = self.call("post", f"{RE}circles/{self.fid}/points/", {"name": "By the tea stall", **ORIGIN}, 201)
        self.assertEqual(point["category"], "family_meeting")
        self.assertTrue(point["is_private"])
        self.assertEqual(self.names(), ["By the tea stall"])
        self.login(self.outsider)
        self.assertEqual(self.call("get", f"{RE}points/")["results"], [])

    def test_outsiders_cant_add_to_a_family(self):
        self.login(self.outsider)
        self.call("post", f"{RE}circles/{self.fid}/points/", {"name": "X", **ORIGIN}, code=404)

    def test_a_family_cant_claim_a_category(self):
        self.login(self.adult)
        point = self.call("post", f"{RE}circles/{self.fid}/points/", {
            "name": "Fake police", "category": "police", "status": "verified", **ORIGIN,
        }, 201)
        self.assertEqual(point["category"], "family_meeting")
        self.assertFalse(point["is_verified"])

    def test_suggesting_keeps_it_private_until_staff_decide(self):
        self.login(self.adult)
        point = self.call("post", f"{RE}circles/{self.fid}/points/", {"name": "Tree", **ORIGIN}, 201)
        self.call("post", f"{RE}points/{point['id']}/suggest/")
        self.login(self.outsider)
        self.assertEqual(self.call("get", f"{RE}points/")["results"], [])
        row = MeetingPoint.objects.get()
        services.review_point(row, self.staff, St.COMMUNITY)
        self.assertEqual(len(self.call("get", f"{RE}points/")["results"]), 1)

    def test_only_a_creator_or_organizer_can_change_it(self):
        self.login(self.adult)
        point = self.call("post", f"{RE}circles/{self.fid}/points/", {"name": "Tree", **ORIGIN}, 201)
        self.login(self.relative)
        self.call("delete", f"{RE}points/{point['id']}/", code=403)
        self.login(self.organizer)
        self.call("delete", f"{RE}points/{point['id']}/")
        self.assertEqual(MeetingPoint.objects.get().status, St.RETIRED)

    def test_public_points_cant_be_changed_through_the_api(self):
        point = self.point()
        self.login(self.adult)
        self.call("delete", f"{RE}points/{point.pk}/", code=403)

    def test_verifying_requires_a_source_and_records_who(self):
        point = self.point("Tree", Cat.HELP_DESK, St.COMMUNITY)
        with self.assertRaises(services.ReunionError):
            services.review_point(point, self.staff, St.VERIFIED)
        services.review_point(point, self.staff, St.VERIFIED, source_detail="Visited 3 Jan")
        point.refresh_from_db()
        self.assertEqual(point.verified_by, self.staff)
        self.assertIsNotNone(point.verified_at)

    def test_pages(self):
        for i in range(3):
            self.point(f"Desk {i}")
        with mock.patch("apps.reunification.views.PointListAPI.PAGE_SIZE", 2):
            self.login(self.adult)
            first = self.call("get", f"{RE}points/")
            second = self.call("get", f"{RE}points/?page=2")
        self.assertTrue(first["has_next"])
        self.assertEqual(first["count"], 3)
        self.assertEqual(len(second["results"]), 1)


class ProtectionTests(ReTestCase):
    def test_who_counts_as_protected(self):
        self.assertTrue(policy.is_protected(self.child_case()))
        self.assertTrue(policy.is_protected(self.case(vulnerabilities=["elderly"])))
        self.assertTrue(policy.is_protected(self.case(age_max=15)))
        self.assertFalse(policy.is_protected(self.case(member=self.adult_member, age_min=30)))

    def test_a_child_is_sent_to_staff_not_a_nearer_family_spot(self):
        case = self.child_case()
        self.point("Far desk", lat="20.100000")
        self.point("Near tree", Cat.FAMILY_MEETING, St.COMMUNITY, lat="19.9901")
        self.login(self.organizer)
        points = self.call("post", f"{RE}cases/{case.pk}/guidance/")["points"]
        self.assertEqual([p["name"] for p in points], ["Far desk"])

    def test_kind_of_place_beats_distance(self):
        case = self.child_case()
        self.point("Police near", Cat.POLICE, lat="19.9901")
        self.point("Lost and found far", Cat.LOST_FOUND, lat="20.2000")
        self.login(self.organizer)
        points = self.call("post", f"{RE}cases/{case.pk}/guidance/")["points"]
        self.assertEqual(points[0]["name"], "Lost and found far")

    def test_distance_decides_within_a_kind(self):
        case = self.child_case()
        self.point("Far", lat="20.2000")
        self.point("Near", lat="19.9950")
        self.login(self.organizer)
        points = self.call("post", f"{RE}cases/{case.pk}/guidance/", {"origin": ORIGIN})["points"]
        self.assertEqual([p["name"] for p in points], ["Near", "Far"])
        self.assertIsNotNone(points[0]["straight_line_km"])

    def test_a_medical_need_puts_medical_first(self):
        case = self.case(vulnerabilities=["medical"])
        self.point("Desk")
        self.point("Camp", Cat.MEDICAL)
        self.login(self.organizer)
        points = self.call("post", f"{RE}cases/{case.pk}/guidance/")["points"]
        self.assertEqual(points[0]["name"], "Camp")

    def test_no_verified_points_means_none_are_invented(self):
        case = self.child_case()
        self.login(self.organizer)
        self.assertEqual(self.call("post", f"{RE}cases/{case.pk}/guidance/")["points"], [])

    def test_a_childs_case_cant_use_a_community_point(self):
        case = self.child_case()
        self.login(self.organizer)
        data = self.call("post", f"{RE}cases/{case.pk}/meeting-point/", {
            "meeting_point_id": str(self.point("Tree", Cat.FAMILY_MEETING, St.COMMUNITY).pk),
        }, 409)
        self.assertIsNone(data)
        self.assertFalse(ReunificationPlan.objects.exists())

    def test_a_childs_case_cant_route_to_an_unverified_point(self):
        case = self.child_case()
        self.login(self.organizer)
        self.route("point", self.point("Tree", Cat.FAMILY_MEETING, St.COMMUNITY).pk, 409, case_id=str(case.pk))

    def test_a_childs_own_account_gets_no_route_to_family(self):
        self.share(self.organizer, [self.adult_member.pk])
        FamilyMember.objects.filter(pk=self.adult_member.pk).update(age_group="13_17")
        self.login(self.adult)
        self.route("member", self.org_member.pk, 409)
        self.walk.assert_not_called()

    def test_a_protected_person_with_an_account_gets_no_route_to_family(self):
        self.share(self.organizer, [self.adult_member.pk])
        self.case(member=self.adult_member, vulnerabilities=["elderly"])
        self.login(self.adult)
        self.route("member", self.org_member.pk, 409)

    def test_a_phone_with_a_missing_dependent_gets_no_route_to_family(self):
        self.share(self.adult, [self.org_member.pk])
        self.login(self.organizer)
        session = self.call("post", f"{LOC}circles/{self.fid}/sessions/", {
            "member_id": self.child["id"], "recipient_ids": [str(self.org_member.pk)],
            "duration_minutes": 60, "consent": True,
        }, 201)
        self.assertTrue(session["reports_from_me"])
        self.child_case()
        self.route("member", self.adult_member.pk, 409)

    def test_overview_says_so(self):
        FamilyMember.objects.filter(pk=self.adult_member.pk).update(age_group="13_17")
        self.login(self.adult)
        self.assertTrue(self.call("get", f"{RE}overview/?family_id={self.fid}")["self_protected"])
        self.login(self.organizer)
        self.assertFalse(self.call("get", f"{RE}overview/?family_id={self.fid}")["self_protected"])

    def test_going_to_a_vulnerable_relative_comes_with_a_caution(self):
        self.share(self.adult, [self.org_member.pk])
        self.case(member=self.adult_member, vulnerabilities=["elderly"])
        self.login(self.organizer)
        self.assertEqual(self.route("member", self.adult_member.pk)["caution"], "stay_put")


class RouteTests(ReTestCase):
    def test_to_a_verified_point(self):
        self.login(self.adult)
        data = self.route("point", self.point().pk)
        self.assertEqual(data["distance_m"], 840)
        self.assertEqual(data["duration_s"], 660)
        self.assertEqual(data["name"], "Ramkund Help Desk")

    def test_to_a_chosen_viewers_family_member(self):
        self.share(self.adult, [self.org_member.pk])
        self.login(self.organizer)
        data = self.route("member", self.adult_member.pk)
        self.assertEqual(data["state"], "live")
        self.assertEqual(float(self.walk.call_args.args[1][0]), 19.9975)

    def test_a_stale_destination_says_so(self):
        self.share(self.adult, [self.org_member.pk], age=1800)
        self.login(self.organizer)
        self.assertEqual(self.route("member", self.adult_member.pk)["state"], "last_known")

    def test_not_chosen_gets_nothing(self):
        self.share(self.adult, [self.org_member.pk])
        self.login(self.relative)
        self.route("member", self.adult_member.pk, 404)
        self.walk.assert_not_called()

    def test_outsider_gets_nothing(self):
        self.share(self.adult, [self.org_member.pk])
        self.login(self.outsider)
        self.route("member", self.adult_member.pk, 404)

    def test_paused_gives_no_route(self):
        session = self.share(self.adult, [self.org_member.pk])
        self.call("post", f"{LOC}sessions/{session['id']}/pause/")
        self.login(self.organizer)
        self.route("member", self.adult_member.pk, 404)

    def test_stopped_gives_no_route(self):
        session = self.share(self.adult, [self.org_member.pk])
        self.call("post", f"{LOC}sessions/{session['id']}/stop/")
        self.login(self.organizer)
        self.route("member", self.adult_member.pk, 404)

    def test_expired_gives_no_route(self):
        self.share(self.adult, [self.org_member.pk])
        LocationSession.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.login(self.organizer)
        self.route("member", self.adult_member.pk, 404)
        self.assertFalse(MemberLocation.objects.exists())

    def test_revoked_gives_no_route(self):
        session = self.share(self.adult, [self.org_member.pk, self.relative_member.pk])
        self.call("post", f"{LOC}sessions/{session['id']}/recipients/", {"recipient_ids": [str(self.relative_member.pk)]})
        self.login(self.organizer)
        self.route("member", self.adult_member.pk, 404)

    def test_someone_elses_private_point_is_refused(self):
        self.login(self.adult)
        point = self.call("post", f"{RE}circles/{self.fid}/points/", {"name": "Tree", **ORIGIN}, 201)
        self.login(self.outsider)
        self.route("point", point["id"], 404)

    def test_provider_down_is_reported_not_invented(self):
        self.login(self.adult)
        point = self.point()
        with mock.patch("apps.reunification.routing.walking_route", side_effect=routing.RoutingUnavailable):
            response = self.client.post(f"{RE}route/", {
                "origin": ORIGIN, "kind": "point", "target_id": str(point.pk),
            }, format="json")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("distance_m", str(response.content))
        self.assertEqual(response.json()["errors"]["code"], "routing_unavailable")

    def test_bad_origin_is_refused(self):
        self.login(self.adult)
        self.route("point", self.point().pk, 400, origin={"latitude": 95, "longitude": 0})

    def test_routes_are_rate_limited(self):
        self.login(self.adult)
        with mock.patch("apps.reunification.views.RouteThrottle.rate", "2/hour"):
            codes = [self.client.post(f"{RE}route/", {}, format="json").status_code for _ in range(4)]
        self.assertIn(429, codes)

    def test_never_cached(self):
        self.login(self.adult)
        point = self.point()
        with mock.patch("apps.reunification.routing.walking_route", return_value=ROUTE):
            response = self.client.post(f"{RE}route/", {
                "origin": ORIGIN, "kind": "point", "target_id": str(point.pk),
            }, format="json")
        self.assertIn("no-store", response["Cache-Control"])


class ProviderTests(TestCase):
    def post(self, **kw):
        return mock.patch("apps.reunification.routing.requests.post", **kw)

    @override_settings(GOOGLE_ROUTES_API_KEY="")
    def test_no_key_means_unavailable_without_a_call(self):
        with self.post() as post, self.assertRaises(routing.RoutingUnavailable):
            routing.walking_route((1, 2), (3, 4))
        post.assert_not_called()

    @override_settings(GOOGLE_ROUTES_API_KEY="k")
    def test_reads_the_providers_values(self):
        reply = mock.Mock()
        reply.json.return_value = {"routes": [{
            "distanceMeters": 1234, "duration": "900s", "polyline": {"encodedPolyline": "xyz"},
        }]}
        with self.post(return_value=reply) as post:
            route = routing.walking_route((1, 2), (3, 4))
        self.assertEqual(route, {"distance_m": 1234, "duration_s": 900, "polyline": "xyz"})
        self.assertEqual(post.call_args.kwargs["json"]["travelMode"], "WALK")

    @override_settings(GOOGLE_ROUTES_API_KEY="k")
    def test_an_empty_answer_is_unavailable(self):
        reply = mock.Mock()
        reply.json.return_value = {}
        with self.post(return_value=reply), self.assertRaises(routing.RoutingUnavailable):
            routing.walking_route((1, 2), (3, 4))

    @override_settings(GOOGLE_ROUTES_API_KEY="k")
    def test_a_failure_logs_no_coordinates(self):
        with self.post(side_effect=requests.ConnectionError("19.9975,73.7898")), \
                self.assertLogs("apps.reunification", logging.WARNING) as logs, \
                self.assertRaises(routing.RoutingUnavailable):
            routing.walking_route((19.9975, 73.7898), (3, 4))
        self.assertNotIn("19.99", "\n".join(logs.output))


class CaseTests(ReTestCase):
    def overview(self, user):
        self.login(user)
        return self.call("get", f"{RE}overview/?family_id={self.fid}")["cases"]

    def test_family_see_their_case(self):
        case = self.case(member=self.adult_member)
        rows = self.overview(self.relative)
        self.assertEqual(rows[0]["reference"], case.reference)
        self.assertEqual(rows[0]["plan"]["stage"], "reported")

    def test_strangers_see_nothing(self):
        case = self.case(member=self.adult_member)
        self.login(self.outsider)
        self.assertEqual(self.call("get", f"{RE}overview/")["cases"], [])
        self.call("get", f"{RE}cases/{case.pk}/", code=404)
        self.call("post", f"{RE}cases/{case.pk}/guidance/", code=404)

    def test_a_childs_case_isnt_shown_to_relatives_who_dont_manage_them(self):
        self.child_case()
        self.assertEqual(self.overview(self.relative), [])

    def test_an_adults_location_needs_their_consent(self):
        self.case(member=self.adult_member)
        self.assertIsNone(self.overview(self.relative)[0]["latitude"])
        FamilyMember.objects.filter(pk=self.adult_member.pk).update(location_sharing_consent=True)
        self.assertEqual(self.overview(self.relative)[0]["latitude"], 19.99)

    def test_sightings_are_reviewed_and_labelled(self):
        case = self.case(member=self.adult_member, reporter=self.relative)
        base = {"case": case, "description": "x", "location_text": "Ghat", "seen_at": timezone.now(),
                "latitude": "19.99", "longitude": "73.78"}
        CaseSighting.objects.create(**base, review="pending")
        CaseSighting.objects.create(**base, review="approved")
        CaseSighting.objects.create(**base, review="approved", verified=True)
        CaseSighting.objects.create(**base, review="rejected")
        rows = self.overview(self.relative)[0]["sightings"]
        self.assertEqual(sorted(s["location_label"] for s in rows), ["reported", "verified"])

    def test_internal_notes_never_appear(self):
        case = self.case(member=self.adult_member)
        CaseNote.objects.create(case=case, kind="internal", body="Private investigation note")
        CaseNote.objects.create(case=case, kind="verification", body="id_document: secret check")
        CaseNote.objects.create(case=case, kind="family_update", body="Staff are at the ghat")
        self.login(self.organizer)
        text = str(self.call("get", f"{RE}cases/{case.pk}/"))
        self.assertIn("Staff are at the ghat", text)
        self.assertNotIn("Private investigation", text)
        self.assertNotIn("secret check", text)

    def test_a_helper_who_isnt_assigned_gets_404(self):
        case = self.case(member=self.adult_member)
        desk = self.user("96", "Desk")
        SafetyHelper.objects.create(user=desk, role="help_desk")
        self.login(desk)
        self.call("get", f"{RE}cases/{case.pk}/", code=404)
        LostFoundCase.objects.filter(pk=case.pk).update(assigned_to=desk)
        self.assertTrue(self.call("get", f"{RE}cases/{case.pk}/")["can_operate"])

    def test_staff_can_coordinate_but_arent_shown_as_family(self):
        self.case(member=self.adult_member)
        self.login(self.staff)
        self.assertEqual(self.call("get", f"{RE}overview/")["cases"], [])


class WorkflowTests(ReTestCase):
    def setUp(self):
        super().setUp()
        self.subject = self.case(member=self.adult_member)
        self.desk = self.point()

    def stage(self):
        self.login(self.staff)
        return self.call("get", f"{RE}cases/{self.subject.pk}/")["plan"]["stage"]

    def status(self):
        self.subject.refresh_from_db()
        return self.subject.status

    def test_family_choose_a_point_and_it_tells_people(self):
        self.login(self.organizer)
        with mock.patch(LF_PUSH, return_value=SENT) as push, self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f"{RE}cases/{self.subject.pk}/meeting-point/", {
                "meeting_point_id": str(self.desk.pk),
            }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(push.call_count, 2)
        self.assertEqual(response.json()["data"]["stage"], "point_chosen")
        self.assertTrue(CaseAudit.objects.filter(action="meeting_point_selected").exists())

    def test_notices_name_no_place(self):
        self.login(self.organizer)
        with mock.patch(LF_PUSH, return_value=SENT) as push, self.captureOnCommitCallbacks(execute=True):
            self.client.post(f"{RE}cases/{self.subject.pk}/meeting-point/", {
                "meeting_point_id": str(self.desk.pk),
            }, format="json")
        text = str([call.args[1]("en") for call in push.call_args_list])
        self.assertNotIn("Ramkund", text)
        self.assertNotIn("19.99", str(push.call_args_list))

    def test_a_point_that_isnt_visible_is_refused(self):
        self.login(self.adult)
        private = self.call("post", f"{RE}circles/{self.fid}/points/", {"name": "Tree", **ORIGIN}, 201)
        self.login(self.staff)
        self.call("post", f"{RE}cases/{self.subject.pk}/meeting-point/", {"meeting_point_id": private["id"]}, 400)
        self.call("post", f"{RE}cases/{self.subject.pk}/meeting-point/", {"meeting_point_id": "nonsense"}, 400)

    def test_arrival_moves_the_plan_but_never_the_case(self):
        self.login(self.organizer)
        self.choose(self.subject, self.desk)
        self.call("post", f"{RE}cases/{self.subject.pk}/coordination/", {"event": "family_arrived"})
        self.login(self.staff)
        self.call("post", f"{RE}cases/{self.subject.pk}/coordination/", {"event": "person_arrived"})
        self.assertEqual(self.stage(), "at_point")
        self.assertEqual(self.status(), Status.SUBMITTED)
        self.assertIsNone(LostFoundCase.objects.get(pk=self.subject.pk).reunited_at)

    def test_family_cant_record_the_person_arriving_or_write_updates(self):
        self.login(self.organizer)
        self.choose(self.subject, self.desk)
        self.call("post", f"{RE}cases/{self.subject.pk}/coordination/", {"event": "person_arrived"}, 403)
        self.call("post", f"{RE}cases/{self.subject.pk}/coordination/", {"update": "Done"}, 403)

    def test_arrival_needs_a_point(self):
        self.login(self.organizer)
        self.call("post", f"{RE}cases/{self.subject.pk}/coordination/", {"event": "family_arrived"}, 409)

    def test_staff_updates_reach_the_family_timeline(self):
        self.login(self.staff)
        self.call("post", f"{RE}cases/{self.subject.pk}/coordination/", {"update": "Waiting at the desk"})
        self.login(self.organizer)
        self.assertIn("Waiting at the desk", str(self.call("get", f"{RE}cases/{self.subject.pk}/")["case"]["timeline"]))

    def test_being_at_the_same_place_is_not_a_reunion(self):
        session = self.share(self.adult, [self.org_member.pk])
        self.login(self.organizer)
        self.choose(self.subject, self.desk)
        self.call("get", f"{LOC}circles/{self.fid}/feed/")
        self.assertTrue(session)
        self.assertEqual(self.status(), Status.SUBMITTED)

    def test_family_cant_reach_the_reunion_step(self):
        self.login(self.organizer)
        self.call("post", f"/api/lostfound/ops/cases/{self.subject.pk}/reunite/", {
            "method": "family_in_person", "remarks": "They hugged each other", "identity_checked": True,
        }, 403)

    def test_full_path_needs_a_human_check(self):
        self.login(self.organizer)
        self.choose(self.subject, self.desk)
        with self.assertRaises(Exception):
            record_reunion(
                self.subject, self.staff, method="other", remarks="Long enough remarks", identity_checked=True,
                person_recognised=False,
            )
        LostFoundCase.objects.filter(pk=self.subject.pk).update(status=Status.VERIFICATION_REQUIRED)
        self.subject.refresh_from_db()
        self.assertEqual(self.stage(), "verifying")
        with mock.patch(LF_PUSH, return_value=SENT):
            verify_case(self.subject, self.staff, method="id_document", remarks="Checked the Aadhaar in person")
            self.subject.refresh_from_db()
            with self.assertRaises(Exception):
                record_reunion(
                    self.subject, self.staff, method="other", remarks="Long enough remarks", identity_checked=False,
                    person_recognised=False,
                )
            record_reunion(
                self.subject, self.staff, method="family_in_person", remarks="Recognised each other, ID checked",
                identity_checked=True, person_recognised=False,
            )
        self.assertEqual(self.stage(), "reunited")

    def test_a_closed_case_cant_be_planned(self):
        LostFoundCase.objects.filter(pk=self.subject.pk).update(status=Status.CLOSED)
        self.login(self.organizer)
        self.choose(self.subject, self.desk, 409)


class FamilyActionTests(ReTestCase):
    def send(self, body, push=None):
        with mock.patch(RE_PUSH, return_value=SENT) as sender:
            response = self.client.post(f"{RE}circles/{self.fid}/notify/", body, format="json")
        return response, sender

    def test_tells_the_rest_of_the_family(self):
        self.login(self.adult)
        response, push = self.send({"kind": "meet_at_point"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(sorted(push.call_args.kwargs["users"]), sorted([self.organizer.pk, self.relative.pk]))
        self.assertTrue(FamilyAuditLog.objects.filter(action="reunion_meet_at_point").exists())

    def test_a_shared_point_travels_by_id_only(self):
        point = self.point()
        self.login(self.adult)
        _, push = self.send({"kind": "meet_at_point", "point_id": str(point.pk)})
        data = push.call_args.kwargs["data"]
        self.assertEqual(data["point_id"], str(point.pk))
        self.assertNotIn("19.99", str(data))

    def test_another_familys_private_point_cant_be_shared(self):
        self.login(self.outsider)
        other = self.call("post", f"{RE}circles/{self.other_family['id']}/points/", {"name": "Tree", **ORIGIN}, 201)
        self.login(self.adult)
        self.assertEqual(self.send({"kind": "meet_at_point", "point_id": other["id"]})[0].status_code, 400)

    def test_the_text_holds_nothing_private(self):
        self.login(self.adult)
        _, push = self.send({"kind": "meet_at_point"})
        for language in ("en", "hi", "mr"):
            self.assertNotIn("Asha", str(push.call_args.args[1](language)))

    def test_outsiders_get_404(self):
        self.login(self.outsider)
        self.assertEqual(self.send({"kind": "check_map"})[0].status_code, 404)

    def test_unknown_kinds_are_refused(self):
        self.login(self.adult)
        self.assertEqual(self.send({"kind": "anything"})[0].status_code, 400)

    def test_is_rate_limited(self):
        self.login(self.adult)
        with mock.patch("apps.reunification.views.NotifyThrottle.rate", "2/hour"):
            codes = [self.send({"kind": "check_map"})[0].status_code for _ in range(4)]
        self.assertIn(429, codes)

    def test_guardian_link_data_isnt_needed_for_organizers(self):
        GuardianLink.objects.create(dependent_id=self.child["id"], guardian=self.adult_member)
        self.assertTrue(policy.can_coordinate(self.adult, self.child_case()))

    @override_settings(SAFETY_REQUIRE_HTTPS=True)
    def test_plain_http_is_refused_when_required(self):
        self.login(self.adult)
        self.assertEqual(self.client.post(f"{RE}route/", {}, format="json").status_code, 400)
