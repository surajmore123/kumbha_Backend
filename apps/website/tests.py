import json
import os
from datetime import timedelta
from unittest import mock

from django.test import TestCase

from apps.authentication.models import User

from . import conf, core
from .models import PhoneLock, RefreshToken

USER, ADMIN = "9811111111", "9822222222"


class ApiTestCase(TestCase):
    def setUp(self):
        # Ignore any real KP_* settings (e.g. production .env inside the container).
        env = {k: v for k, v in os.environ.items() if not k.startswith("KP_")}
        env |= {"KP_ENV": "test", "KP_ADMIN_PHONES": f'["{ADMIN}"]', "KP_SMS_PROVIDER": "console"}
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        conf.get_settings.cache_clear()
        self.addCleanup(conf.get_settings.cache_clear)
        core._limiter = None  # fresh in-memory rate limits per test

    def call(self, method, path, body=None, token=None, **params):
        kwargs = {"content_type": "application/json"}
        if body is not None:
            kwargs["data"] = json.dumps(body)
        if token:
            kwargs["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        url = f"/api/v1{path}"
        if params:
            url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
        resp = getattr(self.client, method.lower())(url, **kwargs)
        return resp.status_code, (resp.json() if resp.content else None)

    def login(self, phone=USER):
        status, body = self.call("POST", "/auth/otp/request", {"phone": phone})
        self.assertEqual(status, 200, body)
        status, body = self.call("POST", "/auth/otp/verify", {"phone": phone, "code": body["debug_code"]})
        self.assertEqual(status, 200, body)
        return body


class AuthTests(ApiTestCase):
    def test_otp_sign_in_creates_app_style_user(self):
        tp = self.login()
        self.assertEqual(tp["user"]["phone"], USER)
        self.assertEqual(tp["user"]["role"], "user")
        user = User.objects.get()
        self.assertEqual(user.phone_number, f"+91{USER}")  # same format the mobile app uses
        self.assertEqual(tp["user"]["id"], user.user_id.hex)

    def test_app_user_gets_same_account_on_website(self):
        app_user = User.objects.create(phone_number=f"+91{USER}", full_Name="Ravi")
        tp = self.login()
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(tp["user"]["id"], app_user.user_id.hex)
        self.assertEqual(tp["user"]["name"], "Ravi")

    def test_admin_phone_becomes_admin(self):
        self.assertEqual(self.login(ADMIN)["user"]["role"], "admin")

    def test_wrong_codes_lock_the_number(self):
        status, body = self.call("POST", "/auth/otp/request", {"phone": USER})
        wrong = "000000" if body["debug_code"] != "000000" else "111111"
        status, body = self.call("POST", "/auth/otp/verify", {"phone": USER, "code": wrong})
        self.assertEqual((status, body["error"]["code"], body["error"]["attempts_left"]), (400, "otp_invalid", 2))
        self.call("POST", "/auth/otp/verify", {"phone": USER, "code": wrong})
        status, body = self.call("POST", "/auth/otp/verify", {"phone": USER, "code": wrong})
        self.assertEqual((status, body["error"]["code"]), (423, "otp_locked"))
        self.assertTrue(PhoneLock.objects.filter(phone=USER).exists())

    def test_resend_gap(self):
        self.call("POST", "/auth/otp/request", {"phone": USER})
        status, body = self.call("POST", "/auth/otp/request", {"phone": USER})
        self.assertEqual((status, body["error"]["code"]), (429, "rate_limited"))

    def test_refresh_rotation_and_reuse_detection(self):
        tp = self.login()
        status, tp2 = self.call("POST", "/auth/refresh", {"refresh_token": tp["refresh_token"]})
        self.assertEqual(status, 200)
        status, body = self.call("POST", "/auth/refresh", {"refresh_token": tp["refresh_token"]})
        self.assertEqual((status, body["error"]["code"]), (401, "token_reused"))
        status, body = self.call("POST", "/auth/refresh", {"refresh_token": tp2["refresh_token"]})
        self.assertEqual(status, 401)  # every session ended

    def test_expired_access_token(self):
        user = User.objects.create(phone_number=f"+91{USER}")
        with mock.patch.object(core, "utcnow", return_value=core.utcnow() - timedelta(hours=1)):
            token, _ = core.create_access_token(user.user_id.hex, "user")
        status, body = self.call("GET", "/auth/me", token=token)
        self.assertEqual((status, body["error"]["code"]), (401, "invalid_token"))

    def test_profile_update_and_validation(self):
        tok = self.login()["access_token"]
        status, body = self.call("PATCH", "/auth/me", {"name": " Ravi ", "preferred_language": "mr"}, token=tok)
        self.assertEqual((status, body["name"], body["preferred_language"]), (200, "Ravi", "mr"))
        status, body = self.call("PATCH", "/auth/me", {"role": "admin"}, token=tok)
        self.assertEqual((status, body["error"]["code"]), (422, "validation_error"))

    def test_google_disabled_without_client_id(self):
        status, body = self.call("POST", "/auth/google", {"credential": "x" * 120})
        self.assertEqual((status, body["error"]["code"]), (503, "google_disabled"))

    def test_google_sign_in_matches_existing_email(self):
        existing = User.objects.create(phone_number=f"+91{USER}", email="ravi@example.com")
        claims = {"sub": "1", "email": "ravi@example.com", "name": "Ravi"}
        with mock.patch("apps.website.views.auth.verify_google_credential", return_value=claims):
            status, body = self.call("POST", "/auth/google", {"credential": "x" * 120})
        self.assertEqual(status, 200, body)
        self.assertEqual(body["user"]["id"], existing.user_id.hex)
        self.assertEqual(body["user"]["phone"], USER)


class DataTests(ApiTestCase):
    def test_items_and_safety_cards_are_private(self):
        tok = self.login()["access_token"]
        other = self.login(ADMIN)["access_token"]
        status, _ = self.call("PUT", "/me/items/plan/trip-1", {"data": {"days": 3}}, token=tok)
        self.assertEqual(status, 200)
        self.assertEqual(len(self.call("GET", "/me/items", token=tok)[1]), 1)
        self.assertEqual(self.call("GET", "/me/items", token=other)[1], [])
        status, body = self.call("PUT", "/me/items/boat/x", {"data": {}}, token=tok)
        self.assertEqual((status, body["error"]["fields"][0]["field"]), (422, "kind"))

        status, card = self.call("POST", "/me/safety-cards", {"name": "Sita", "phones": ["+91 98111 11111"], "meet": "Gate 4"}, token=tok)
        self.assertEqual((status, card["phones"]), (201, [USER]))
        status, _ = self.call("DELETE", f"/me/safety-cards/{card['id']}", token=other)
        self.assertEqual(status, 404)
        status, _ = self.call("DELETE", f"/me/safety-cards/{card['id']}", token=tok)
        self.assertEqual(status, 204)

    def test_partner_listing_review_flow(self):
        tok = self.login()["access_token"]
        admin = self.login(ADMIN)["access_token"]
        status, partner = self.call(
            "POST", "/partners", {"name": "Godavari Stay", "category": "hotels", "contact_phone": USER, "town": "Nashik"}, token=tok
        )
        self.assertEqual(status, 201)
        listing = {"name": "Riverside", "type": "Hotel", "town": "Nashik", "area": "Panchavati", "price_from": 2500, "unit": "per night"}
        self.assertEqual(self.call("POST", "/partners/me/listings", listing, token=tok)[0], 403)
        self.assertEqual(self.call("GET", "/admin/partners", token=tok)[0], 403)
        self.assertEqual(self.call("POST", f"/admin/partners/{partner['id']}/status", token=admin, status="verified")[0], 200)
        status, created = self.call("POST", "/partners/me/listings", listing, token=tok)
        self.assertEqual((status, created["status"]), (201, "pending"))
        self.assertEqual(self.call("GET", "/listings")[1]["total"], 0)
        self.call("POST", f"/admin/listings/{created['id']}/status", token=admin, status="published")
        status, page = self.call("GET", "/listings", q="river")
        self.assertEqual((status, page["total"]), (200, 1))

    def test_enquiry_and_admin_user_management(self):
        tok = self.login()["access_token"]
        admin = self.login(ADMIN)["access_token"]
        status, e = self.call("POST", "/enquiries", {"subject": "Room", "name": "Ravi", "phone": USER, "people": 2})
        self.assertEqual(status, 201)
        self.assertEqual(len(self.call("GET", "/enquiries/me", token=tok)[1]), 1)  # matched by verified mobile
        status, page = self.call("GET", "/admin/users", token=admin)
        uid = next(u["id"] for u in page["items"] if u["phone"] == USER)
        status, detail = self.call("PATCH", f"/admin/users/{uid}", {"is_active": False}, token=admin)
        self.assertEqual((status, detail["activity"]["enquiries"]), (200, 1))
        self.assertFalse(RefreshToken.objects.filter(user__user_id=uid).exists())
        self.assertEqual(self.call("GET", "/auth/me", token=tok)[0], 401)

    def test_errors_use_the_json_error_format(self):
        status, body = self.call("GET", "/does-not-exist")
        self.assertEqual((status, body["error"]["code"]), (404, "http_error"))
        status, body = self.call("DELETE", "/listings")
        self.assertEqual((status, body["error"]["code"]), (405, "http_error"))
        status, body = self.call("POST", "/waitlist", {"name": "A", "contact": "nope"})
        self.assertEqual((status, body["error"]["code"]), (422, "validation_error"))
