import logging
from datetime import timedelta
from unittest import mock

from django.contrib.admin.sites import site
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.authentication.models import FCMDevice, User
from apps.family.models import EmergencyContact, FamilyAuditLog, FamilyMember, GuardianLink
from apps.safety import models, policy
from apps.safety.models import SafetyAlert, SafetyHelper, SafetyQRIdentity, SafetyScanLog, hash_token

FAMILY = "/api/family/"
SAFETY = "/api/safety/"
PUSH = "apps.safety.notifications.send_localized"
SENT = {"status": "sent", "success": 1, "failure": 0, "deactivated": 0}


@override_settings(SAFETY_REQUIRE_HTTPS=False, SAFETY_QR_SECRET="test-key")
class SafetyTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.father = User.objects.create_user(phone_number="+919100000041", full_Name="Suresh More")
        self.mother = User.objects.create_user(phone_number="+919100000042", full_Name="Asha More")
        self.uncle = User.objects.create_user(phone_number="+919100000043", full_Name="Ravi More")
        self.outsider = User.objects.create_user(phone_number="+919100000044", full_Name="Stranger")
        self.volunteer = User.objects.create_user(phone_number="+919100000045", full_Name="Volunteer One")
        self.helper = SafetyHelper.objects.create(user=self.volunteer, role="volunteer")
        self.client = APIClient()
        self.login(self.father)
        self.family = self.post(f"{FAMILY}circles/", {"name": "More Family"}, 201)
        self.fam = f"{SAFETY}circles/{self.family['id']}/"
        self.child = self.post(f"{FAMILY}circles/{self.family['id']}/members/", {
            "full_name": "Aarav Kumar More", "kind": "dependent_child", "relationship": "son",
            "age_group": "6_12", "mobile": "9812345678", "date_of_birth": "2018-02-03",
        }, 201)
        self.organizer = FamilyMember.objects.get(user=self.father)
        self.mother_member = self.join(self.mother)
        self.uncle_member = self.join(self.uncle)

    def join(self, user):
        self.login(self.father)
        code = self.post(f"{FAMILY}circles/{self.family['id']}/invitations/", {"relationship": "spouse"}, 201)["code"]
        self.login(user)
        joined = self.post(f"{FAMILY}invitations/accept/", {"code": code})
        self.login(self.father)
        return FamilyMember.objects.get(pk=joined["member_id"])

    def login(self, user):
        self.client.force_authenticate(user)

    def post(self, url, body=None, code=200):
        response = self.client.post(url, body or {}, format="json")
        self.assertEqual(response.status_code, code, response.content)
        return response.json().get("data") if response.content else None

    def qr_url(self, member_id):
        return f"{self.fam}members/{member_id}/qr/"

    def child_qr(self):
        self.login(self.father)
        response = self.client.post(self.qr_url(self.child["id"]), {}, format="json")
        self.assertIn(response.status_code, (200, 201), response.content)
        return response.json()["data"]

    def token_of(self, identity):
        return identity["payload"].partition("#t=")[2]

    def resolve(self, identity=None, code=200):
        identity = identity or self.child_qr()
        self.login(self.volunteer)
        return self.post(f"{SAFETY}scan/resolve/", {"token": self.token_of(identity)}, code)

    def confirm(self, scan, situation="separated", code=201, **extra):
        body = {"situation": situation, "confirmed": True, **extra}
        return self.post(f"{SAFETY}scan/{scan['scan_id']}/confirm/", body, code)

    def alert(self, **extra):
        with mock.patch(PUSH, return_value=SENT):
            return self.confirm(self.resolve(), **extra)


class GenerationTests(SafetyTestCase):
    def test_each_member_gets_their_own(self):
        one = self.child_qr()
        self.login(self.mother)
        two = self.post(self.qr_url(self.mother_member.pk), code=201)
        self.assertNotEqual(one["payload"], two["payload"])

    def test_payload_holds_nothing_personal(self):
        identity = self.child_qr()
        payload = identity["payload"]
        self.assertTrue(payload.startswith("https://kumbhapath.in/safety/qr#t="))
        for private in ("Aarav", "More", "9812345678", self.family["id"], self.child["id"], identity["id"]):
            self.assertNotIn(private, payload)
        self.assertGreaterEqual(len(self.token_of(identity)), 43)

    def test_the_token_is_never_stored(self):
        identity = self.child_qr()
        token = self.token_of(identity)
        stored = SafetyQRIdentity.objects.get()
        self.assertEqual(stored.token_hash, hash_token(token))
        self.assertNotIn(token, str(stored.__dict__))

    def test_a_copy_of_the_database_alone_gives_no_token(self):
        identity = self.child_qr()
        stored = SafetyQRIdentity.objects.get()
        with override_settings(SAFETY_QR_SECRET="another-key"):
            self.assertNotEqual(models.derive_token(stored.salt), self.token_of(identity))

    def test_asking_again_returns_the_same_qr(self):
        first = self.child_qr()
        second = self.post(self.qr_url(self.child["id"]), code=200)
        self.assertEqual(first["payload"], second["payload"])
        self.assertEqual(SafetyQRIdentity.objects.count(), 1)

    def test_the_database_allows_one_active_qr(self):
        self.child_qr()
        with self.assertRaises(IntegrityError), transaction.atomic():
            SafetyQRIdentity.objects.create(member_id=self.child["id"])

    def test_a_lost_race_returns_the_winners_qr(self):
        self.child_qr()
        winner = SafetyQRIdentity.objects.get()
        view = __import__("apps.safety.views", fromlist=["x"]).MemberQrAPI()
        identity, created = view.create(FamilyMember.objects.get(pk=self.child["id"]), self.father)
        self.assertFalse(created)
        self.assertEqual(identity.pk, winner.pk)

    def test_viewing_before_generating_returns_nothing(self):
        self.assertIsNone(self.client.get(self.qr_url(self.child["id"])).json()["data"])

    def test_responses_arent_cached(self):
        self.child_qr()
        self.assertIn("no-store", self.client.get(self.qr_url(self.child["id"]))["Cache-Control"])

    def test_a_changed_server_key_is_reported_not_hidden(self):
        self.child_qr()
        with override_settings(SAFETY_QR_SECRET="another-key"):
            self.assertEqual(self.client.get(self.qr_url(self.child["id"])).status_code, 409)

    def test_generation_is_audited_without_the_token(self):
        token = self.token_of(self.child_qr())
        log = FamilyAuditLog.objects.get(action="safety_qr_created")
        self.assertNotIn(token, str(log.details))


class RevokeTests(SafetyTestCase):
    def test_revoking_kills_the_old_code(self):
        identity = self.child_qr()
        self.post(self.qr_url(self.child["id"]) + "revoke/")
        self.resolve(identity, code=410)
        self.assertEqual(self.client.get(f"{SAFETY}helper/me/").status_code, 200)

    def test_regenerating_replaces_it(self):
        old = self.child_qr()
        new = self.post(self.qr_url(self.child["id"]) + "regenerate/", code=201)
        self.assertNotEqual(old["payload"], new["payload"])
        self.assertEqual(SafetyQRIdentity.objects.filter(status="active").count(), 1)
        self.resolve(old, code=410)
        self.resolve(new)

    def test_regenerating_with_none_active_works(self):
        self.post(self.qr_url(self.child["id"]) + "regenerate/", code=201)
        self.assertEqual(SafetyQRIdentity.objects.count(), 1)

    def test_revoking_nothing_is_a_conflict(self):
        self.post(self.qr_url(self.child["id"]) + "revoke/", code=409)

    def test_expired_is_treated_as_revoked(self):
        identity = self.child_qr()
        SafetyQRIdentity.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        self.resolve(identity, code=410)


class AccessTests(SafetyTestCase):
    def test_needs_login(self):
        self.client.force_authenticate(None)
        for url in (self.qr_url(self.child["id"]), f"{self.fam}alerts/", f"{SAFETY}helper/me/"):
            self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(self.client.post(f"{SAFETY}scan/resolve/", {"token": "x"}, format="json").status_code, 401)

    def test_guardian_can_reach_a_dependent(self):
        GuardianLink.objects.create(dependent_id=self.child["id"], guardian=self.mother_member)
        self.child_qr()
        self.login(self.mother)
        self.assertEqual(self.client.get(self.qr_url(self.child["id"])).status_code, 200)
        self.post(self.qr_url(self.child["id"]) + "regenerate/", code=201)

    def test_another_family_member_cant_reach_a_dependent(self):
        self.child_qr()
        self.login(self.uncle)
        url = self.qr_url(self.child["id"])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.post(url, code=403)
        self.post(url + "revoke/", code=403)
        self.post(url + "regenerate/", code=403)

    def test_organizer_cant_reach_an_adults_qr(self):
        self.login(self.mother)
        self.post(self.qr_url(self.mother_member.pk), code=201)
        self.login(self.father)
        url = self.qr_url(self.mother_member.pk)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.post(url, code=403)
        self.post(url + "revoke/", code=403)
        self.post(url + "regenerate/", code=403)

    def test_an_adult_controls_their_own(self):
        self.login(self.mother)
        url = self.qr_url(self.mother_member.pk)
        self.post(url, code=201)
        self.post(url + "regenerate/", code=201)
        self.post(url + "revoke/")

    def test_outsiders_get_404(self):
        self.child_qr()
        self.login(self.outsider)
        self.assertEqual(self.client.get(self.qr_url(self.child["id"])).status_code, 404)
        self.post(self.qr_url(self.child["id"]), code=404)
        self.assertEqual(self.client.get(f"{self.fam}alerts/").status_code, 404)

    def test_ids_from_another_family_are_refused(self):
        self.login(self.outsider)
        other = self.post(f"{FAMILY}circles/", {"name": "Other"}, 201)
        url = f"{SAFETY}circles/{other['id']}/members/{self.child['id']}/qr/"
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_the_app_is_told_who_may_view(self):
        self.login(self.father)
        members = self.client.get(f"{FAMILY}circles/{self.family['id']}/members/").json()["data"]
        by_id = {m["id"]: m["permissions"]["view_qr"] for m in members}
        self.assertTrue(by_id[self.child["id"]])
        self.assertFalse(by_id[str(self.mother_member.pk)])
        self.assertTrue(by_id[str(self.organizer.pk)])


class ScanTests(SafetyTestCase):
    def test_an_ordinary_user_learns_nothing(self):
        token = self.token_of(self.child_qr())
        self.login(self.outsider)
        real = self.client.post(f"{SAFETY}scan/resolve/", {"token": token}, format="json")
        fake = self.client.post(f"{SAFETY}scan/resolve/", {"token": "x" * 43}, format="json")
        self.assertEqual((real.status_code, fake.status_code), (403, 403))
        self.assertEqual(real.content, fake.content)
        self.assertNotIn(b"Aarav", real.content)

    def test_family_members_cant_scan_either(self):
        token = self.token_of(self.child_qr())
        self.post(f"{SAFETY}scan/resolve/", {"token": token}, 403)

    def test_a_disabled_or_lapsed_helper_cant_scan(self):
        token = self.token_of(self.child_qr())
        self.login(self.volunteer)
        SafetyHelper.objects.update(is_active=False)
        self.post(f"{SAFETY}scan/resolve/", {"token": token}, 403)
        SafetyHelper.objects.update(is_active=True, expires_at=timezone.now() - timedelta(days=1))
        self.post(f"{SAFETY}scan/resolve/", {"token": token}, 403)

    def test_a_helper_gets_only_the_minimum(self):
        scan = self.resolve()
        self.assertEqual(scan["first_name"], "Aarav")
        self.assertEqual(scan["category"], "child")
        self.assertEqual(set(scan), {
            "scan_id", "first_name", "category", "language", "open_alerts", "valid_seconds",
        })
        text = str(scan)
        for private in ("More", "Kumar", "9812345678", "2018", self.family["id"], self.child["id"]):
            self.assertNotIn(private, text)

    def test_no_phone_number_anywhere_in_the_flow(self):
        EmergencyContact.objects.create(
            family_id=self.family["id"], name="Uncle", mobile="+919876543210", priority=1,
        )
        identity = self.child_qr()
        self.login(self.volunteer)
        first = self.client.post(f"{SAFETY}scan/resolve/", {"token": self.token_of(identity)}, format="json")
        scan = first.json()["data"]["scan_id"]
        with mock.patch(PUSH, return_value=SENT):
            second = self.client.post(
                f"{SAFETY}scan/{scan}/confirm/", {"situation": "separated", "confirmed": True}, format="json",
            )
        for response in (first, second):
            self.assertNotIn(b"9876543210", response.content)
            self.assertNotIn(b"9812345678", response.content)
            self.assertNotIn(b"+91", response.content)

    def test_an_adult_is_categorized_as_adult(self):
        self.login(self.mother)
        identity = self.post(self.qr_url(self.mother_member.pk), code=201)
        self.assertEqual(self.resolve(identity)["category"], "adult")

    def test_unknown_tokens_get_404(self):
        self.login(self.volunteer)
        for bad in ("x" * 43, "", 5, ["a"], {"a": 1}):
            self.post(f"{SAFETY}scan/resolve/", {"token": bad}, 404)

    def test_every_scan_is_logged_without_the_token(self):
        identity = self.child_qr()
        token = self.token_of(identity)
        self.login(self.outsider)
        self.post(f"{SAFETY}scan/resolve/", {"token": token}, 403)
        self.login(self.volunteer)
        self.post(f"{SAFETY}scan/resolve/", {"token": "bad"}, 404)
        self.post(f"{SAFETY}scan/resolve/", {"token": token})
        self.assertEqual(
            sorted(SafetyScanLog.objects.values_list("outcome", flat=True)), ["denied", "resolved", "unknown"],
        )
        for log in SafetyScanLog.objects.all():
            self.assertNotIn(token, str(log.__dict__))
        self.assertIsNotNone(SafetyQRIdentity.objects.get().last_scanned_at)

    def test_scanning_is_rate_limited(self):
        self.login(self.outsider)
        with mock.patch("apps.safety.views.ScanThrottle.rate", "5/hour"), mock.patch(
            "apps.safety.views.ScanThrottle.get_rate", return_value="5/hour",
        ):
            codes = [
                self.client.post(f"{SAFETY}scan/resolve/", {"token": f"g{i}"}, format="json").status_code
                for i in range(8)
            ]
        self.assertIn(429, codes)

    def test_a_scan_alone_creates_no_alert(self):
        self.resolve()
        self.assertFalse(SafetyAlert.objects.exists())

    @override_settings(SAFETY_REQUIRE_HTTPS=True)
    def test_plain_http_is_refused_when_required(self):
        self.login(self.volunteer)
        self.post(f"{SAFETY}scan/resolve/", {"token": "x"}, 400)
        self.assertFalse(SafetyScanLog.objects.exists())
        secure = self.client.post(f"{SAFETY}scan/resolve/", {"token": "x"}, format="json", secure=True)
        self.assertEqual(secure.status_code, 404)


class ConfirmTests(SafetyTestCase):
    def test_confirming_creates_one_alert_and_tells_the_family(self):
        with mock.patch(PUSH, return_value=SENT) as push:
            body = self.confirm(self.resolve())
        self.assertRegex(body["reference"], r"^KP-[A-Z2-9]{8}$")
        self.assertEqual((body["status"], body["delivery"], body["duplicate"]), ("open", "sent", False))
        alert = SafetyAlert.objects.get()
        self.assertEqual(str(alert.member_id), self.child["id"])
        self.assertEqual(alert.helper, self.volunteer)
        self.assertEqual(alert.helper_role, "volunteer")
        self.assertEqual(push.call_args.kwargs["users"], [self.father.pk])
        self.assertEqual(push.call_args.kwargs["data"]["route"], "/safetyAlerts")

    def test_the_helper_must_confirm(self):
        scan = self.resolve()
        self.post(f"{SAFETY}scan/{scan['scan_id']}/confirm/", {"situation": "separated", "confirmed": False}, 400)
        self.post(f"{SAFETY}scan/{scan['scan_id']}/confirm/", {"situation": "separated"}, 400)
        self.assertFalse(SafetyAlert.objects.exists())

    def test_bad_input_is_refused(self):
        scan = self.resolve()
        for body in (
            {"situation": "missing", "confirmed": True},
            {"situation": "separated", "confirmed": True, "latitude": 19.9},
            {"situation": "separated", "confirmed": True, "latitude": 200, "longitude": 73},
            {"situation": "separated", "confirmed": True, "note": "x" * 201},
        ):
            self.post(f"{SAFETY}scan/{scan['scan_id']}/confirm/", body, 400)

    def test_repeated_scans_make_no_duplicate(self):
        first = self.alert()
        with mock.patch(PUSH, return_value=SENT) as push:
            second = self.confirm(self.resolve(), code=200)
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["reference"], second["reference"])
        self.assertEqual(SafetyAlert.objects.count(), 1)
        push.assert_not_called()

    def test_pressing_confirm_twice_makes_no_duplicate(self):
        scan = self.resolve()
        with mock.patch(PUSH, return_value=SENT) as push:
            first = self.confirm(scan)
            second = self.confirm(scan, code=200)
        self.assertEqual(first["reference"], second["reference"])
        self.assertEqual(push.call_count, 1)

    def test_a_race_ends_in_one_alert(self):
        self.alert()
        alert = SafetyAlert.objects.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            SafetyAlert.objects.create(
                family=alert.family, member=alert.member, kind=alert.kind, helper_role="volunteer",
            )

    def test_a_different_situation_is_a_separate_alert(self):
        self.alert()
        with mock.patch(PUSH, return_value=SENT):
            self.confirm(self.resolve(), situation="medical")
        self.assertEqual(SafetyAlert.objects.count(), 2)

    def test_a_resolved_alert_doesnt_block_a_new_one(self):
        self.alert()
        SafetyAlert.objects.update(status="resolved")
        with mock.patch(PUSH, return_value=SENT):
            self.confirm(self.resolve())
        self.assertEqual(SafetyAlert.objects.count(), 2)

    def test_a_suspicious_scan_doesnt_alarm_the_family(self):
        with mock.patch(PUSH) as push:
            body = self.confirm(self.resolve(), situation="suspicious", code=200)
        self.assertTrue(body["recorded"])
        self.assertFalse(SafetyAlert.objects.exists())
        push.assert_not_called()
        self.assertEqual(SafetyScanLog.objects.get(outcome="resolved").situation, "suspicious")
        self.assertTrue(FamilyAuditLog.objects.filter(action="safety_scan_flagged").exists())

    def test_only_the_scanning_helper_can_confirm(self):
        scan = self.resolve()
        other = User.objects.create_user(phone_number="+919100000046")
        SafetyHelper.objects.create(user=other, role="help_desk")
        self.login(other)
        self.confirm(scan, code=404)
        self.login(self.outsider)
        self.confirm(scan, code=403)

    def test_a_stale_scan_cant_be_confirmed(self):
        scan = self.resolve()
        SafetyScanLog.objects.update(created_at=timezone.now() - timedelta(minutes=16))
        self.confirm(scan, code=410)

    def test_a_scan_of_a_revoked_qr_cant_be_confirmed(self):
        scan = self.resolve()
        SafetyQRIdentity.objects.update(status="revoked")
        self.confirm(scan, code=410)

    def test_location_is_kept_only_if_sent(self):
        self.alert()
        alert = SafetyAlert.objects.get()
        self.assertIsNone(alert.latitude)
        SafetyAlert.objects.all().delete()
        self.alert(latitude=19.9975, longitude=73.7898)
        self.assertEqual(float(SafetyAlert.objects.get().latitude), 19.9975)

    def test_a_push_failure_keeps_the_alert_and_says_so(self):
        with mock.patch(PUSH, side_effect=RuntimeError("firebase down")):
            body = self.confirm(self.resolve())
        self.assertEqual(body["delivery"], "unavailable")
        self.assertTrue(SafetyAlert.objects.exists())

    def test_disabled_firebase_is_reported(self):
        result = {"status": "disabled", "success": 0, "failure": 0, "deactivated": 0}
        with mock.patch(PUSH, return_value=result):
            body = self.confirm(self.resolve())
        self.assertEqual(body["delivery"], "unavailable")

    def test_no_registered_devices_is_reported(self):
        body = self.confirm(self.resolve())
        self.assertEqual(body["delivery"], "no_devices")

    def test_a_real_send_reaches_only_the_right_devices(self):
        GuardianLink.objects.create(dependent_id=self.child["id"], guardian=self.mother_member)
        for user, token in ((self.father, "t-father"), (self.mother, "t-mother"), (self.uncle, "t-uncle")):
            FCMDevice.objects.create(user=user, token=token, device_type="ANDROID")
        response = mock.Mock(success_count=2, failure_count=0, responses=[])
        with mock.patch("utils.push_notifications.messaging.send_each_for_multicast", return_value=response) as send:
            body = self.confirm(self.resolve())
        self.assertEqual(body["delivery"], "sent")
        message = send.call_args.args[0]
        self.assertEqual(sorted(message.tokens), ["t-father", "t-mother"])
        self.assertNotIn("Aarav", message.notification.title)
        self.assertNotIn("Aarav", message.notification.body)
        self.assertNotIn("Kumar", message.notification.body)

    def test_a_helper_follows_only_their_own_report(self):
        body = self.alert()
        url = f"{SAFETY}helper/alerts/{body['id']}/"
        seen = self.client.get(url).json()["data"]
        self.assertFalse(seen["family_acknowledged"])
        self.assertNotIn("member_name", seen)
        other = User.objects.create_user(phone_number="+919100000047")
        SafetyHelper.objects.create(user=other, role="help_desk")
        self.login(other)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_logs_hold_no_token_or_detail(self):
        identity = self.child_qr()
        token = self.token_of(identity)
        with self.assertLogs("apps.safety", level=logging.DEBUG) as logs, mock.patch(
            PUSH, side_effect=RuntimeError("firebase down"),
        ):
            self.confirm(self.resolve(identity))
        text = "\n".join(logs.output)
        for private in (token, "Aarav", "9812345678"):
            self.assertNotIn(private, text)


class FamilyAlertTests(SafetyTestCase):
    def alerts(self):
        return self.client.get(f"{self.fam}alerts/").json()["data"]

    def test_guardians_and_organizer_review_a_dependent(self):
        GuardianLink.objects.create(dependent_id=self.child["id"], guardian=self.mother_member)
        self.alert()
        for user in (self.father, self.mother):
            self.login(user)
            self.assertEqual(len(self.alerts()), 1)

    def test_other_members_dont_see_a_dependents_alert(self):
        body = self.alert()
        self.login(self.uncle)
        self.assertEqual(self.alerts(), [])
        self.post(f"{self.fam}alerts/{body['id']}/acknowledge/", code=404)
        self.post(f"{self.fam}alerts/{body['id']}/resolve/", code=404)

    def test_outsiders_cant_reach_it(self):
        body = self.alert()
        self.login(self.outsider)
        self.post(f"{self.fam}alerts/{body['id']}/acknowledge/", code=404)

    def test_the_family_never_sees_who_the_helper_is(self):
        self.alert()
        self.login(self.father)
        alert = self.alerts()[0]
        self.assertEqual(alert["helper_role"], "volunteer")
        self.assertNotIn("Volunteer One", str(alert))
        self.assertNotIn("helper", [k for k in alert if k != "helper_role"])

    def test_acknowledging_reaches_the_helper(self):
        body = self.alert()
        self.login(self.father)
        acknowledged = self.post(f"{self.fam}alerts/{body['id']}/acknowledge/")
        self.assertEqual(acknowledged["status"], "acknowledged")
        self.login(self.volunteer)
        seen = self.client.get(f"{SAFETY}helper/alerts/{body['id']}/").json()["data"]
        self.assertTrue(seen["family_acknowledged"])

    def test_resolving_is_audited_and_repeatable(self):
        body = self.alert()
        self.login(self.father)
        self.post(f"{self.fam}alerts/{body['id']}/resolve/")
        self.post(f"{self.fam}alerts/{body['id']}/resolve/")
        self.post(f"{self.fam}alerts/{body['id']}/acknowledge/")
        self.assertEqual(SafetyAlert.objects.get().status, "resolved")
        self.assertEqual(FamilyAuditLog.objects.filter(action="safety_alert_resolved").count(), 1)

    def test_a_dependents_location_goes_to_guardians(self):
        self.alert(latitude=19.9975, longitude=73.7898)
        self.login(self.father)
        self.assertEqual(self.alerts()[0]["location"]["latitude"], 19.9975)

    def adult_alert(self):
        self.login(self.mother)
        identity = self.post(self.qr_url(self.mother_member.pk), code=201)
        with mock.patch(PUSH, return_value=SENT) as push:
            self.confirm(self.resolve(identity), latitude=19.9975, longitude=73.7898)
        return push

    def test_an_adults_location_is_withheld_without_consent(self):
        self.adult_alert()
        self.login(self.father)
        alert = self.alerts()[0]
        self.assertIsNone(alert["location"])
        self.assertTrue(alert["location_withheld"])
        self.login(self.mother)
        self.assertIsNotNone(self.alerts()[0]["location"])

    def test_an_adults_consent_shares_their_location(self):
        FamilyMember.objects.filter(pk=self.mother_member.pk).update(location_sharing_consent=True)
        self.adult_alert()
        self.login(self.father)
        self.assertIsNotNone(self.alerts()[0]["location"])

    def test_an_adults_alert_reaches_their_family_not_themselves(self):
        push = self.adult_alert()
        self.assertCountEqual(push.call_args.kwargs["users"], [self.father.pk, self.uncle.pk])


class PolicyTests(SafetyTestCase):
    def test_recipients_of_a_child_are_guardians_and_the_organizer(self):
        GuardianLink.objects.filter(dependent_id=self.child["id"]).delete()
        GuardianLink.objects.create(dependent_id=self.child["id"], guardian=self.mother_member)
        member = FamilyMember.objects.get(pk=self.child["id"])
        self.assertCountEqual(policy.recipients_for(member), [self.father.pk, self.mother.pk])


class AdminTests(SafetyTestCase):
    def test_nothing_private_is_shown(self):
        self.alert(note="Near the gate", latitude=19.9975, longitude=73.7898)
        identity = SafetyQRIdentity.objects.get()
        staff = User.objects.create_superuser("admin-safety@example.org", "+919100000048", "pw-for-tests")
        client = self.client_class()
        client.force_login(staff)
        for url in (
            "/admin/safety/safetyqridentity/", f"/admin/safety/safetyqridentity/{identity.pk}/change/",
            "/admin/safety/safetyalert/", f"/admin/safety/safetyalert/{SafetyAlert.objects.get().pk}/change/",
            "/admin/safety/safetyscanlog/", "/admin/safety/safetyhelper/", "/admin/safety/safetyhelper/add/",
        ):
            response = client.get(url)
            self.assertEqual(response.status_code, 200, url)
            for private in (identity.token_hash, identity.salt, "Near the gate", "19.99"):
                self.assertNotContains(response, private)

    def test_only_helpers_are_editable(self):
        for model in (SafetyQRIdentity, SafetyAlert, SafetyScanLog):
            admin = site._registry[model]
            request = type("R", (), {"user": None})()
            self.assertFalse(admin.has_change_permission(request))
            self.assertFalse(admin.has_add_permission(request))
