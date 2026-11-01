"""Checks that cut across modules. Every person and value here is synthetic."""

import json
import logging
import os
import re
import subprocess
import sys
import uuid
from datetime import timedelta
from unittest import mock

from django.contrib.admin.sites import site
from django.core.cache import cache
from django.db import connection
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.test.client import Client
from django.urls import get_resolver
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.authentication import otp
from apps.authentication.models import Otp, User
from apps.authentication.tokens import KumbhAccessToken
from apps.crowd.models.Zone import Zone
from apps.emergency.models import EmergencySOS
from apps.family.models import FamilyCircle, FamilyMember
from apps.lostfound.models import LostFoundCase
from apps.operations import services
from apps.safety.models import SafetyHelper, SafetyQRIdentity
from utils.observability import JsonFormatter, RequestLogMiddleware, log_task_failure, redact

AUTH = "/api/auth/"
FAMILY = "/api/family/"
SAFETY = "/api/safety/"
EM = "/api/emergency/"
LF = "/api/lostfound/"
LOC = "/api/location/"
OPS = "/api/operations/"
PUSH_TARGETS = (
    "apps.emergency.services.send_localized",
    "apps.lostfound.notifications.send_localized",
    "apps.safety.notifications.send_localized",
    "apps.operations.services.send_localized",
)
SENT = {"status": "sent", "success": 1, "failure": 0, "deactivated": 0}

# Reading these needs no sign-in, on purpose. A new public route has to be added
# here, which makes that a decision rather than an accident.
PUBLIC = {
    "akhadas/", "akhadas/activities/", "akhadas/articles/", "akhadas/articles/<slug:slug>/", "akhadas/filters/",
    "akhadas/saints/", "akhadas/saints/<slug:slug>/", "akhadas/<slug:slug>/",
    "auth/send-mobile-otp/", "auth/verify-mobile-otp/",
    "bookings/stays/", "bookings/stays/filters/", "bookings/stays/<str:listing_id>/", "bookings/transport/",
    "bookings/transport/search/", "bookings/transport/<slug:slug>/",
    "health/", "health/ready/",
    "learn/articles/", "learn/articles/<slug:slug>/", "learn/glossary/", "learn/glossary/<slug:slug>/", "learn/home/",
    "news/", "news/home/", "news/<slug:slug>/",
    "operations/auth/login/", "operations/auth/setup/",
}
READ_ONLY_PUBLIC_ALLOWED_WRITES = {
    "auth/send-mobile-otp/", "auth/verify-mobile-otp/", "operations/auth/login/", "operations/auth/setup/",
}
CONVERTERS = {"uuid": str(uuid.uuid4()), "int": "1", "slug": "x", "str": "x", "path": "x"}


def walk(patterns, prefix=""):
    for item in patterns:
        if hasattr(item, "url_patterns"):
            yield from walk(item.url_patterns, prefix + str(item.pattern))
        else:
            yield prefix + str(item.pattern), item.callback


def api_routes():
    for path, callback in walk(get_resolver().url_patterns):
        view = getattr(callback, "cls", None)
        if path.startswith("api/") and not path.startswith(("api/admin", "api/v1")) and view is not None:
            yield path.removeprefix("api/"), view


def concrete(path):
    return "/api/" + re.sub(r"<(?:(\w+):)?\w+>", lambda m: CONVERTERS[m.group(1) or "str"], path)


class Actors(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.zone = Zone.objects.create(
            code="SYN1", name="Synthetic One", city="Test", latitude="19.99", longitude="73.79", radius_m=900,
        )
        self.far_zone = Zone.objects.create(
            code="SYN2", name="Synthetic Two", city="Test", latitude="20.60", longitude="74.60", radius_m=900,
        )
        self.parent = self.person("9220000001")
        self.stranger = self.person("9220000002")
        self.staff = self.helper("9220000003", "safety_staff", self.zone)
        self.far_staff = self.helper("9220000004", "safety_staff", self.far_zone)
        self.volunteer = self.helper("9220000005", "volunteer", self.zone)
        self.admin = User.objects.create_superuser("synthetic@test.in", "9220000006", "Synthetic-Pass-2027!")
        patches = [mock.patch(target, return_value=SENT) for target in PUSH_TARGETS]
        for patch in patches:
            try:
                patch.start()
                self.addCleanup(patch.stop)
            except AttributeError:
                pass

    def person(self, phone):
        return User.objects.create_user(phone_number=f"+91{phone}", full_Name="Synthetic Person")

    def helper(self, phone, role, zone):
        user = self.person(phone)
        SafetyHelper.objects.create(user=user, role=role).zones.add(zone)
        return user

    def as_user(self, user):
        self.client.force_authenticate(user)

    def bearer(self, token):
        self.client.force_authenticate(None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def call(self, method, url, body=None, code=200):
        with self.captureOnCommitCallbacks(execute=True):
            response = getattr(self.client, method)(url, body if body is not None else {}, format="json")
        self.assertEqual(response.status_code, code, f"{url}: {response.content[:300]}")
        return response.json().get("data") if response.content else None

    def make_case(self, zone=None, **extra):
        values = {
            "case_type": "lost", "reporter": self.parent, "event_at": timezone.now(), "location_text": "Synthetic ghat",
            "clothing_description": "Blue shirt", "zone": zone or self.zone, **extra,
        }
        return LostFoundCase.objects.create(**values)


class RouteSweepTests(TestCase):
    def test_every_private_route_refuses_anonymous_callers(self):
        checked = 0
        client = APIClient()
        for path, view in api_routes():
            if path in PUBLIC:
                continue
            for method in ("get", "post", "put", "patch", "delete"):
                if hasattr(view, method):
                    response = getattr(client, method)(concrete(path), {}, format="json")
                    self.assertIn(response.status_code, (401, 405), f"{method} {path}")
                    checked += 1
        self.assertGreater(checked, 150)

    def test_nothing_is_public_by_accident(self):
        public = {
            path for path, view in api_routes()
            if any(issubclass(p, AllowAny) for p in view.permission_classes) or not view.permission_classes
        }
        self.assertEqual(public - PUBLIC, set())

    def test_public_content_routes_cant_be_written(self):
        client = APIClient()
        for path, view in api_routes():
            if path in PUBLIC and path not in READ_ONLY_PUBLIC_ALLOWED_WRITES:
                for method in ("post", "put", "patch", "delete"):
                    self.assertEqual(getattr(client, method)(concrete(path), {}).status_code, 405, path)

    def test_sign_in_routes_are_rate_limited(self):
        for path, view in api_routes():
            if path in READ_ONLY_PUBLIC_ALLOWED_WRITES:
                self.assertTrue(view.throttle_classes, path)

    def test_sessions_are_not_accepted_on_token_routes(self):
        for path, view in api_routes():
            if path not in PUBLIC and path.startswith(("family/", "emergency/", "lostfound/", "operations/", "location/")):
                names = {auth.__name__ for auth in view.authentication_classes}
                self.assertNotIn("BasicAuthentication", names, path)


class TokenTests(Actors):
    URL = f"{OPS}me/"

    def code(self):
        return self.client.get(self.URL).status_code

    def forged(self, key, **claims):
        import jwt

        payload = {
            "token_type": "access", "user_id": str(self.staff.pk), "jti": uuid.uuid4().hex,
            "iat": int(timezone.now().timestamp()),
            "exp": int((timezone.now() + timedelta(hours=1)).timestamp()), **claims,
        }
        return jwt.encode(payload, key, algorithm="HS256")

    def test_a_real_token_works(self):
        self.bearer(RefreshToken.for_user(self.parent).access_token)
        self.assertEqual(self.code(), 200)

    def test_garbage_is_refused(self):
        self.bearer("not-a-token")
        self.assertEqual(self.code(), 401)

    def test_a_token_signed_with_the_wrong_key_is_refused(self):
        for key in ("wrong-key-of-a-reasonable-length-000", "dev-secret-key-but-wrong-000000000000"):
            self.bearer(self.forged(key))
            self.assertEqual(self.code(), 401)

    def test_unsigned_tokens_are_refused(self):
        def part(value):
            import base64

            return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()

        now = int(timezone.now().timestamp())
        claims = {"token_type": "access", "user_id": str(self.staff.pk), "exp": now + 3600, "jti": "x"}
        self.bearer(f"{part({'alg': 'none', 'typ': 'JWT'})}.{part(claims)}.")
        self.assertEqual(self.code(), 401)

    def test_an_expired_token_is_refused(self):
        token = RefreshToken.for_user(self.parent).access_token
        token.set_exp(lifetime=-timedelta(seconds=5))
        self.bearer(token)
        self.assertEqual(self.code(), 401)

    def test_a_refresh_token_cant_be_used_as_access(self):
        self.bearer(RefreshToken.for_user(self.parent))
        self.assertEqual(self.code(), 401)

    def test_a_token_for_a_removed_user_is_refused(self):
        user = self.person("9220000099")
        token = RefreshToken.for_user(user).access_token
        user.delete()
        self.bearer(token)
        self.assertEqual(self.code(), 401)

    def test_extra_claims_grant_nothing(self):
        token = RefreshToken.for_user(self.parent).access_token
        token["role"] = "ADMIN"
        token["is_staff"] = True
        token["is_superuser"] = True
        self.bearer(token)
        self.assertEqual(self.client.get(f"{OPS}overview/").status_code, 403)
        self.assertEqual(self.client.get(f"{LF}ops/cases/").status_code, 403)
        self.assertEqual(self.client.get(f"{EM}ops/sos/").status_code, 403)

    def test_signing_out_everywhere_ends_tokens(self):
        token = RefreshToken.for_user(self.volunteer).access_token
        User.objects.filter(pk=self.volunteer.pk).update(tokens_valid_after=timezone.now() + timedelta(seconds=5))
        self.bearer(token)
        self.assertIn(self.code(), (401, 403))

    def test_deactivating_stops_a_session_already_running(self):
        token = RefreshToken.for_user(self.volunteer).access_token
        self.bearer(token)
        self.assertEqual(self.client.get(f"{OPS}cases/").status_code, 200)
        helper = SafetyHelper.objects.get(user=self.volunteer)
        services.set_status(helper, "deactivated", self.admin)
        self.assertIn(self.client.get(f"{OPS}cases/").status_code, (401, 403))

    def test_the_token_class_is_the_checked_one(self):
        self.assertTrue(issubclass(KumbhAccessToken, AccessToken))


class RoleEscalationTests(Actors):
    def test_a_profile_update_cant_change_privilege(self):
        self.as_user(self.parent)
        self.client.patch(f"{AUTH}profile/", {
            "full_name": "Still Synthetic", "role": "ADMIN", "is_staff": True, "is_superuser": True,
            "is_active": False, "otp_verified": False, "tokens_valid_after": None, "phone_number": "+919220000111",
        }, format="json")
        self.parent.refresh_from_db()
        self.assertFalse(self.parent.is_staff)
        self.assertFalse(self.parent.is_superuser)
        self.assertTrue(self.parent.is_active)
        self.assertEqual(self.parent.phone_number, "+919220000001")

    def test_what_the_app_sends_about_a_role_is_ignored(self):
        self.as_user(self.volunteer)
        before = self.call("get", f"{OPS}me/")["role"]
        self.call("patch", f"{OPS}me/availability/", {"availability": "AVAILABLE", "role": "SAFETY_COORDINATOR"})
        self.assertEqual(self.call("get", f"{OPS}me/")["role"], before)
        self.assertEqual(SafetyHelper.objects.get(user=self.volunteer).role, "volunteer")

    def test_a_volunteer_cant_assign_or_see_the_team(self):
        case = self.make_case()
        self.as_user(self.volunteer)
        self.assertIn(
            self.client.post(f"{OPS}cases/{case.pk}/assign/", {"volunteer_id": str(self.volunteer.pk)}, format="json").status_code,
            (403, 404),
        )
        self.assertIn(self.client.get(f"{OPS}team/").status_code, (403, 404))

    def test_a_helper_cant_reach_django_admin(self):
        self.client.force_login(self.volunteer)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.volunteer.is_staff)

    def test_a_user_id_in_the_body_doesnt_change_the_owner(self):
        self.as_user(self.stranger)
        data = self.call("post", f"{LF}cases/", {
            "reporter": str(self.parent.pk), "reporter_id": str(self.parent.pk), "user_id": str(self.parent.pk),
            "relationship": "Parent", "location_text": "Synthetic ghat", "clothing_description": "Blue shirt",
            "event_at": timezone.now().isoformat(),
        }, 201)
        self.assertEqual(LostFoundCase.objects.get(pk=data["id"]).reporter, self.stranger)


class IsolationTests(Actors):
    def circle(self, owner):
        self.as_user(owner)
        return self.call("post", f"{FAMILY}circles/", {"name": "Synthetic Family"}, 201)["id"]

    def test_one_family_cant_reach_another(self):
        family = self.circle(self.parent)
        self.as_user(self.stranger)
        for url in (
            f"{FAMILY}circles/{family}/", f"{FAMILY}circles/{family}/members/", f"{FAMILY}circles/{family}/contacts/",
            f"{SAFETY}circles/{family}/alerts/", f"{LOC}circles/{family}/feed/", f"{LOC}circles/{family}/eligible/",
        ):
            self.assertEqual(self.client.get(url).status_code, 404, url)

    def test_a_case_in_another_zone_is_hidden(self):
        case = self.make_case(self.far_zone)
        self.as_user(self.staff)
        self.assertEqual(self.client.get(f"{LF}ops/cases/{case.pk}/").status_code, 404)
        self.assertEqual(
            self.client.post(f"{LF}ops/cases/{case.pk}/status/", {"status": "CLOSED", "reason": "x"}, format="json").status_code,
            404,
        )
        ids = [row["id"] for row in self.call("get", f"{LF}ops/cases/")["results"]]
        self.assertNotIn(str(case.pk), ids)

    def test_unauthorized_case_updates_are_refused(self):
        case = self.make_case()
        for user in (self.stranger, self.parent, self.volunteer):
            self.as_user(user)
            for action in ("verify", "reunite", "assign", "notes", "status", "contact"):
                response = self.client.post(f"{LF}ops/cases/{case.pk}/{action}/", {}, format="json")
                self.assertIn(response.status_code, (403, 404), action)
        case.refresh_from_db()
        self.assertEqual(case.status, "SUBMITTED")

    def sos(self, user):
        self.as_user(user)
        return self.call("post", f"{EM}sos/", {"client_id": str(uuid.uuid4()), "category": "medical"}, 201)

    def test_nobody_outside_operations_can_resolve_an_sos(self):
        sos = self.sos(self.parent)
        for user in (self.parent, self.stranger, self.volunteer):
            self.as_user(user)
            for action in ("acknowledge", "resolve", "close", "escalate"):
                response = self.client.post(f"{EM}ops/sos/{sos['id']}/{action}/", {"body": "x"}, format="json")
                self.assertIn(response.status_code, (403, 404), action)
        self.assertEqual(EmergencySOS.objects.get(pk=sos["id"]).resolved_at, None)

    def test_an_sos_is_never_visible_to_a_stranger(self):
        sos = self.sos(self.parent)
        self.as_user(self.stranger)
        self.assertEqual(self.client.get(f"{EM}sos/{sos['id']}/").status_code, 404)

    def test_a_repeated_sos_is_one_sos(self):
        first = self.sos(self.parent)
        again = self.client.post(f"{EM}sos/", {"client_id": str(uuid.uuid4()), "category": "lost"}, format="json")
        self.assertEqual(again.status_code, 409)
        self.assertEqual(self.client.get(f"{EM}sos/{first['id']}/").status_code, 200)
        self.assertEqual(EmergencySOS.objects.count(), 1)


class QrPrivacyTests(Actors):
    def setUp(self):
        super().setUp()
        self.as_user(self.parent)
        self.family = self.call("post", f"{FAMILY}circles/", {"name": "Synthetic Family"}, 201)["id"]
        self.child = self.call("post", f"{FAMILY}circles/{self.family}/members/", {
            "full_name": "Synthetic Child", "kind": "dependent_child", "relationship": "son", "age_group": "6_12",
        }, 201)
        self.url = f"{SAFETY}circles/{self.family}/members/{self.child['id']}/qr/"
        self.identity = self.call("post", self.url, {}, 201)
        self.token = self.identity["payload"].partition("#t=")[2]

    def test_an_invalid_token_says_nothing(self):
        self.as_user(self.volunteer)
        response = self.client.post(f"{SAFETY}scan/resolve/", {"token": "x" * 40}, format="json")
        self.assertIn(response.status_code, (400, 404, 410))
        self.assertNotIn("Synthetic", response.content.decode())

    def test_a_pilgrim_cant_scan(self):
        self.as_user(self.stranger)
        response = self.client.post(f"{SAFETY}scan/resolve/", {"token": self.token}, format="json")
        self.assertIn(response.status_code, (403, 404))
        self.assertNotIn("Synthetic", response.content.decode())

    def test_a_scan_shows_little_and_opens_no_case(self):
        self.as_user(self.volunteer)
        data = self.call("post", f"{SAFETY}scan/resolve/", {"token": self.token})
        body = json.dumps(data)
        self.assertNotIn("+91", body)
        self.assertNotIn("phone", body)
        self.assertFalse(LostFoundCase.objects.exists())

    def test_the_token_itself_is_not_stored(self):
        for identity in SafetyQRIdentity.objects.all():
            self.assertNotIn(self.token, json.dumps(
                {field.name: str(getattr(identity, field.attname)) for field in identity._meta.fields},
            ))

    def test_tokens_are_unique(self):
        payloads = {self.identity["payload"]}
        for _ in range(3):
            payloads.add(self.call("post", f"{self.url}regenerate/", {}, 201)["payload"])
        self.assertEqual(len(payloads), 4)


@override_settings(MOBILE_OTP_MODE="sms")
class SmsOtpTests(Actors):
    PHONE = "+919220000050"

    def sender(self, name="msg91"):
        sender = mock.Mock()
        sender.name = name
        patch = mock.patch("apps.authentication.otp.get_sms_sender", return_value=sender)
        patch.start()
        self.addCleanup(patch.stop)
        return sender

    def request_code(self):
        return self.client.post(f"{AUTH}send-mobile-otp/", {"phone_number": self.PHONE}, format="json")

    def verify(self, code):
        return self.client.post(f"{AUTH}verify-mobile-otp/", {"phone_number": self.PHONE, "otp_code": code}, format="json")

    def sent_code(self, sender):
        return sender.send_otp.call_args.args[1]

    def test_a_random_code_is_sent_and_only_its_hash_is_stored(self):
        sender = self.sender()
        self.assertEqual(self.request_code().status_code, 201)
        code = self.sent_code(sender)
        row = Otp.objects.get()
        self.assertRegex(code, r"^\d{6}$")
        self.assertEqual(sender.send_otp.call_args.args[0], "9220000050")
        self.assertEqual(row.otp_code, "")
        self.assertNotIn(code, row.code_hash)
        self.assertNotIn(code, self.request_code().content.decode())

    def test_the_right_code_signs_in_once(self):
        sender = self.sender()
        self.request_code()
        code = self.sent_code(sender)
        response = self.verify(code)
        self.assertEqual(response.status_code, 200)
        self.assertIn("access_token", response.json()["data"])
        self.assertEqual(self.verify(code).status_code, 400)

    def test_the_old_fixed_code_never_works(self):
        sender = self.sender()
        self.request_code()
        self.assertEqual(self.verify(otp.FIXED_CODE).status_code, 400)
        sender.send_otp.assert_called_once()

    def test_a_code_from_before_sms_was_turned_on_is_refused(self):
        self.sender()
        user = self.person("9220000050")
        Otp.objects.create(user=user, otp_code=otp.FIXED_CODE, expiry_time=timezone.now() + timedelta(minutes=5))
        self.assertEqual(self.verify(otp.FIXED_CODE).status_code, 400)

    def test_too_many_wrong_guesses_burn_the_code(self):
        sender = self.sender()
        self.request_code()
        code = self.sent_code(sender)
        wrong = "000000" if code != "000000" else "000001"
        for _ in range(otp.MAX_ATTEMPTS):
            self.assertEqual(self.verify(wrong).status_code, 400)
        self.assertEqual(self.verify(code).status_code, 400)

    def test_a_new_code_replaces_the_last(self):
        sender = self.sender()
        self.request_code()
        first = self.sent_code(sender)
        self.request_code()
        if first != self.sent_code(sender):
            self.assertEqual(self.verify(first).status_code, 400)

    def test_an_expired_code_is_refused_and_not_counted(self):
        sender = self.sender()
        self.request_code()
        Otp.objects.update(expiry_time=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.verify(self.sent_code(sender)).status_code, 400)
        self.assertEqual(Otp.objects.get().attempts, 0)

    def test_a_failed_send_is_reported_and_the_code_is_dead(self):
        sender = self.sender()
        sender.send_otp.side_effect = RuntimeError("provider said no")
        response = self.request_code()
        self.assertEqual(response.status_code, 503)
        self.assertTrue(Otp.objects.get().is_used)

    def test_console_delivery_is_refused_so_codes_never_reach_logs(self):
        sender = self.sender("console")
        self.assertEqual(self.request_code().status_code, 503)
        sender.send_otp.assert_not_called()
        self.assertFalse(Otp.objects.exists())

    def test_staff_still_cant_use_otp(self):
        sender = self.sender()
        self.client.post(f"{AUTH}send-mobile-otp/", {"phone_number": self.staff.phone_number}, format="json")
        response = self.client.post(f"{AUTH}verify-mobile-otp/", {
            "phone_number": self.staff.phone_number, "otp_code": self.sent_code(sender),
        }, format="json")
        self.assertEqual(response.status_code, 400)


class OtpTests(Actors):
    def test_a_number_starting_91_can_sign_in(self):
        phone = "9123456780"
        self.client.post(f"{AUTH}send-mobile-otp/", {"phone_number": phone}, format="json")
        response = self.client.post(f"{AUTH}verify-mobile-otp/", {"phone_number": phone, "otp_code": "111111"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)

    @mock.patch("apps.authentication.views.SendOtpPhoneThrottle.rate", "3/hour")
    def test_sending_is_limited_per_number(self):
        cache.clear()
        codes = [
            self.client.post(f"{AUTH}send-mobile-otp/", {"phone_number": "9220000060"}, format="json").status_code
            for _ in range(4)
        ]
        self.assertEqual(codes, [201, 201, 201, 429])
        other = self.client.post(f"{AUTH}send-mobile-otp/", {"phone_number": "9220000061"}, format="json")
        self.assertEqual(other.status_code, 201)

    @mock.patch("apps.authentication.views.VerifyOtpPhoneThrottle.rate", "2/hour")
    def test_guessing_is_limited_however_the_number_is_written(self):
        cache.clear()
        spellings = ("9220000062", "+919220000062", "919220000062")
        codes = [
            self.client.post(f"{AUTH}verify-mobile-otp/", {"phone_number": phone, "otp_code": "000000"}, format="json").status_code
            for phone in spellings
        ]
        self.assertEqual(codes[-1], 429)

    def test_admin_shows_no_codes(self):
        admin = site._registry[Otp]
        self.assertNotIn("otp_code", admin.list_display)
        self.assertNotIn("otp_code", admin.search_fields)


class InputSafetyTests(Actors):
    def test_sql_in_filters_is_only_text(self):
        self.make_case()
        self.as_user(self.staff)
        for value in ("' OR 1=1 --", "1; DROP TABLE lostfound_lostfoundcase", "%' UNION SELECT 1 --"):
            self.assertEqual(self.call("get", f"{LF}ops/cases/?q={value}")["count"], 0)
            self.client.get(f"{LF}ops/cases/", {"status": value, "type": value})
        self.assertEqual(LostFoundCase.objects.count(), 1)

    def test_scripts_come_back_as_data_not_html(self):
        self.as_user(self.parent)
        script = "<script>alert(1)</script>"
        data = self.call("post", f"{LF}cases/", {
            "relationship": "Parent", "location_text": script, "clothing_description": script,
            "event_at": timezone.now().isoformat(),
        }, 201)
        response = self.client.get(f"{LF}cases/{data['id']}/")
        self.assertEqual(response["Content-Type"], "application/json")

    def test_oversized_text_is_refused(self):
        self.as_user(self.parent)
        response = self.client.post(f"{LF}cases/", {
            "relationship": "Parent", "location_text": "x" * 5000, "clothing_description": "Blue",
            "event_at": timezone.now().isoformat(),
        }, format="json")
        self.assertEqual(response.status_code, 400)

    def test_a_non_image_attachment_is_refused(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        case = self.make_case()
        self.as_user(self.parent)
        upload = SimpleUploadedFile("photo.jpg", b"<?php evil(); ?>", content_type="image/jpeg")
        response = self.client.post(f"{LF}cases/{case.pk}/attachments/", {"file": upload}, format="multipart")
        self.assertEqual(response.status_code, 400)

    def test_errors_show_no_internals(self):
        client = Client(raise_request_exception=False)
        with override_settings(DEBUG=False), mock.patch(
            "apps.operations.health.LiveAPI.get", side_effect=RuntimeError("password=hunter2 at /srv/app"),
        ):
            response = client.get("/api/health/")
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("hunter2", response.content.decode())
        self.assertNotIn("Traceback", response.content.decode())
        self.assertIn("X-Request-ID", response)


class RedactionTests(SimpleTestCase):
    def test_sensitive_values_are_removed(self):
        for secret, text in (
            ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl", "token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl"),
            ("abc.def", "Authorization: Bearer abc.def"),
            ("9876543210", "phone 9876543210"),
            ("98765 43210", "phone +91 98765 43210"),
            ("person@example.test", "mail person@example.test"),
            ("19.997512", "at 19.997512, 73.789812"),
            ("73.789812", "at 19.997512, 73.789812"),
            ("482913", 'otp="482913"'),
            ("hunter2", "password=hunter2"),
            ("hunter2", "{'password': 'hunter2'}"),
        ):
            self.assertNotIn(secret, redact(text), text)

    def test_ordinary_values_survive(self):
        text = "Zone SYN1 changed at 2026-11-01T10:00:00 with 12 people, took 145 ms, status 200"
        self.assertEqual(redact(text), text)

    def format(self, message, *args, **extra):
        record = logging.LogRecord("x", logging.INFO, "f", 1, message, args, None)
        record.__dict__.update(extra)
        return json.loads(JsonFormatter().format(record))

    def test_logs_are_structured_and_redacted(self):
        entry = self.format("Sent to %s", "+919876543210", route="api/x/", status=200)
        self.assertEqual(entry["level"], "INFO")
        self.assertEqual(entry["route"], "api/x/")
        self.assertNotIn("9876543210", entry["message"])

    def test_exception_messages_are_left_out(self):
        try:
            raise ValueError("phone 9876543210 and private text")
        except ValueError:
            record = logging.LogRecord("x", logging.ERROR, "f", 1, "Failed", (), sys.exc_info())
        line = JsonFormatter().format(record)
        self.assertIn("ValueError", line)
        self.assertNotIn("private text", line)

    def test_requests_log_the_route_not_the_path(self):
        request = RequestFactory().get("/api/family/circles/private-value/?token=secret-value")
        request.resolver_match = mock.Mock(route="api/family/circles/<uuid:family_id>/")
        response = mock.MagicMock(status_code=200)
        middleware = RequestLogMiddleware(lambda _: response)
        with self.assertLogs("kumbha.request", "INFO") as logs:
            middleware(request)
        self.assertNotIn("private-value", str(logs.records[0].__dict__))
        self.assertNotIn("secret-value", str(logs.records[0].__dict__))

    def test_task_failures_are_tracked_without_their_message(self):
        with self.assertLogs("kumbha.tasks", "ERROR") as logs:
            log_task_failure(sender=mock.Mock(), exception=ValueError("private text"))
        self.assertEqual(logs.records[0].event, "task_failure")
        self.assertNotIn("private text", str(logs.records[0].__dict__))


class HealthTests(Actors):
    def test_liveness_is_public_and_says_nothing(self):
        self.assertEqual(self.client.get("/api/health/").json()["data"], {"alive": True})

    @mock.patch("apps.operations.health._broker", return_value=True)
    def test_ready_when_the_database_and_broker_work(self, _):
        data = self.client.get("/api/health/ready/").json()["data"]
        self.assertTrue(data["ready"])
        self.assertEqual(set(data), {"ready", "database", "broker", "background_tasks"})

    @mock.patch("apps.operations.health._broker", side_effect=OSError("redis://secret-host"))
    def test_a_failure_is_503_without_details(self, _):
        with self.assertLogs("kumbha.health", "ERROR"):
            response = self.client.get("/api/health/ready/")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("secret-host", response.content.decode())

    @mock.patch("apps.operations.health._broker", return_value=True)
    def test_stopped_background_work_shows(self, _):
        from django_celery_beat.models import IntervalSchedule, PeriodicTask

        from apps.operations.health import SWEEPS

        schedule = IntervalSchedule.objects.create(every=1, period="minutes")
        for name in SWEEPS:
            PeriodicTask.objects.create(name=name, task="x", interval=schedule, last_run_at=timezone.now())
        self.assertTrue(self.client.get("/api/health/ready/").json()["data"]["background_tasks"])
        PeriodicTask.objects.update(last_run_at=timezone.now() - timedelta(hours=1))
        data = self.client.get("/api/health/ready/").json()["data"]
        self.assertFalse(data["background_tasks"])
        self.assertTrue(data["ready"])

    @mock.patch("apps.operations.health._broker", return_value=True)
    def test_counts_are_for_administrators(self, _):
        self.assertEqual(self.client.get("/api/health/operations/").status_code, 401)
        self.as_user(self.staff)
        self.assertEqual(self.client.get("/api/health/operations/").status_code, 403)
        self.as_user(self.admin)
        self.assertIn("notifications_last_hour", self.call("get", "/api/health/operations/"))


class ProductionSettingsTests(SimpleTestCase):
    SECRETS = {
        "SECRET_KEY": "s" * 48, "JWT_SECRET_KEY": "j" * 48, "SAFETY_QR_SECRET": "q" * 48,
    }

    def run_check(self, env, *args):
        full = {
            key: value for key, value in os.environ.items()
            if key not in {"SECRET_KEY", "JWT_SECRET_KEY", "SAFETY_QR_SECRET"}
        }
        full.update({"DJANGO_SETTINGS_MODULE": "config.settings.production", **env})
        return subprocess.run(
            [sys.executable, "manage.py", "check", "--settings=config.settings.production", *args],
            env=full, capture_output=True, text=True, timeout=120,
        )

    def test_refuses_to_start_without_secrets(self):
        with mock.patch("dotenv.load_dotenv"):
            for name in self.SECRETS:
                env = {**self.SECRETS, name: "dev-secret-key"}
                result = self.run_check(env)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(name, result.stderr)

    def test_a_short_secret_is_refused(self):
        self.assertNotEqual(self.run_check({**self.SECRETS, "SECRET_KEY": "short"}).returncode, 0)

    def test_starts_with_strong_secrets(self):
        result = self.run_check(self.SECRETS)
        self.assertEqual(result.returncode, 0, result.stderr[-400:])

    def test_the_deployment_check_finds_nothing_serious(self):
        result = self.run_check(self.SECRETS, "--deploy", "--fail-level", "ERROR")
        self.assertEqual(result.returncode, 0, result.stderr[-400:])


class QueryBudgetTests(Actors):
    """Lists must not grow a query per row."""

    def count(self, url):
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(self.client.get(url).status_code, 200)
        return len(queries)

    def budget(self, url, grow):
        grow(2)
        small = self.count(url)
        grow(15)
        self.assertLessEqual(self.count(url), small + 2, url)

    def test_staff_case_list(self):
        self.as_user(self.staff)
        self.budget(f"{LF}ops/cases/", lambda n: [self.make_case() for _ in range(n)])

    def test_volunteer_case_list(self):
        def grow(n):
            for _ in range(n):
                services.assign(self.make_case(), self.volunteer, self.staff)

        self.as_user(self.volunteer)
        self.budget(f"{OPS}cases/", grow)

    def test_match_list(self):
        from apps.lostfound.models import CaseMatch

        def grow(n):
            for _ in range(n):
                lost = self.make_case()
                found = self.make_case(case_type="found")
                CaseMatch.objects.create(lost_case=lost, found_case=found, score=50)

        self.as_user(self.staff)
        self.budget(f"{LF}ops/matches/", grow)

    def test_sos_list(self):
        def grow(n):
            for _ in range(n):
                user = User.objects.create_user(phone_number=f"+9192{uuid.uuid4().int % 10**8:08d}", full_Name="Synthetic")
                self.as_user(user)
                self.call("post", f"{EM}sos/", {"client_id": str(uuid.uuid4()), "category": "medical"}, 201)
            self.as_user(self.staff)

        self.as_user(self.staff)
        self.budget(f"{EM}ops/sos/", grow)
