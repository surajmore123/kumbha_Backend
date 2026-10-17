import json
import os
import struct
import zlib
from datetime import timedelta
from unittest import mock

from django.test import TestCase

from apps.authentication.models import User

from . import conf, core
from .models import AdminAccount, MediaFile, PhoneLock, RefreshToken

USER, OTHER = "9811111111", "9822222222"
ADMIN_USER, ADMIN_PASSWORD = "root", "root-password-1"


class ApiTestCase(TestCase):
    def setUp(self):
        # Ignore any real KP_* settings (e.g. production .env inside the container).
        env = {k: v for k, v in os.environ.items() if not k.startswith("KP_")}
        env |= {"KP_ENV": "test", "KP_SMS_PROVIDER": "console"}
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        conf.get_settings.cache_clear()
        self.addCleanup(conf.get_settings.cache_clear)
        core._limiter = None  # fresh in-memory rate limits per test
        AdminAccount.objects.create(username=ADMIN_USER, name="Root Admin", password_hash=core.hash_password(ADMIN_PASSWORD))

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

    def admin_login(self, username=ADMIN_USER, password=ADMIN_PASSWORD):
        status, body = self.call("POST", "/admin/auth/login", {"username": username, "password": password})
        self.assertEqual(status, 200, body)
        return body["access_token"]


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

    def test_sign_in_never_makes_admins(self):
        self.assertEqual(self.login(OTHER)["user"]["role"], "user")

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
        other = self.login(OTHER)["access_token"]
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
        admin = self.admin_login()
        status, partner = self.call(
            "POST", "/partners", {"name": "Godavari Stay", "category": "hotels", "contact_phone": USER, "town": "Nashik"}, token=tok
        )
        self.assertEqual(status, 201)
        listing = {"name": "Riverside", "type": "Hotel", "town": "Nashik", "area": "Panchavati", "price_from": 2500, "unit": "per night"}
        self.assertEqual(self.call("POST", "/partners/me/listings", listing, token=tok)[0], 403)
        self.assertEqual(self.call("GET", "/admin/partners", token=tok)[0], 401)
        self.assertEqual(self.call("POST", f"/admin/partners/{partner['id']}/status", token=admin, status="verified")[0], 200)
        status, created = self.call("POST", "/partners/me/listings", listing, token=tok)
        self.assertEqual((status, created["status"]), (201, "pending"))
        self.assertEqual(self.call("GET", "/listings")[1]["total"], 0)
        self.call("POST", f"/admin/listings/{created['id']}/status", token=admin, status="published")
        status, page = self.call("GET", "/listings", q="river")
        self.assertEqual((status, page["total"]), (200, 1))

    def test_enquiry_and_admin_user_management(self):
        tok = self.login()["access_token"]
        admin = self.admin_login()
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


class AdminPanelTests(ApiTestCase):
    def test_wrong_password_and_lockout(self):
        bad = {"username": ADMIN_USER, "password": "nope-nope"}
        status, body = self.call("POST", "/admin/auth/login", bad)
        self.assertEqual((status, body["error"]["code"]), (401, "admin_login_failed"))
        # Unknown usernames get the same answer, so usernames can't be guessed.
        status2, body2 = self.call("POST", "/admin/auth/login", {"username": "ghost", "password": "x"})
        self.assertEqual((status2, body2["error"]["message"]), (401, body["error"]["message"]))
        for _ in range(4):
            self.call("POST", "/admin/auth/login", bad)
        status, body = self.call("POST", "/admin/auth/login", {"username": ADMIN_USER, "password": ADMIN_PASSWORD})
        self.assertEqual((status, body["error"]["code"]), (423, "admin_locked"))

    def test_admin_and_user_sessions_are_separate(self):
        admin = self.admin_login()
        self.assertEqual(self.call("GET", "/admin/auth/me", token=admin)[1]["username"], ADMIN_USER)
        self.assertEqual(self.call("GET", "/auth/me", token=admin)[0], 401)  # not a website session
        user = self.login()["access_token"]
        self.assertEqual(self.call("GET", "/admin/auth/me", token=user)[0], 401)
        # Even a user whose role was set to "admin" (old data) can't open the admin API.
        User.objects.update(role="admin")
        self.assertEqual(self.call("GET", "/admin/stats", token=user)[0], 401)

    def test_users_cannot_be_made_admins(self):
        admin = self.admin_login()
        uid = self.login()["user"]["id"]
        status, body = self.call("PATCH", f"/admin/users/{uid}", {"role": "admin"}, token=admin)
        self.assertEqual((status, body["error"]["code"]), (400, "admin_is_separate"))

    def test_admins_manage_each_other(self):
        root = self.admin_login()
        status, priya = self.call("POST", "/admin/accounts", {"username": "priya", "name": "Priya", "password": "priya-pass-1"}, token=root)
        self.assertEqual(status, 201, priya)
        self.assertEqual(self.call("POST", "/admin/accounts", {"username": "PRIYA", "name": "Again", "password": "whatever-1"}, token=root)[0], 409)
        self.assertEqual(self.call("POST", "/admin/accounts", {"username": "x1y", "name": "Short", "password": "short"}, token=root)[0], 422)

        p_tok = self.admin_login("priya", "priya-pass-1")
        self.assertEqual(len(self.call("GET", "/admin/accounts", token=p_tok)[1]), 2)
        # Disabling an admin ends their session immediately.
        self.assertEqual(self.call("PATCH", f"/admin/accounts/{priya['id']}", {"is_active": False}, token=root)[0], 200)
        self.assertEqual(self.call("GET", "/admin/stats", token=p_tok)[0], 401)
        me = self.call("GET", "/admin/auth/me", token=root)[1]["id"]
        self.assertEqual(self.call("PATCH", f"/admin/accounts/{me}", {"is_active": False}, token=root)[0], 400)

    def test_change_own_password(self):
        root = self.admin_login()
        wrong = self.call("POST", "/admin/auth/password", {"current_password": "bad", "new_password": "new-pass-123"}, token=root)
        self.assertEqual(wrong[0], 400)
        ok = self.call("POST", "/admin/auth/password", {"current_password": ADMIN_PASSWORD, "new_password": "new-pass-123"}, token=root)
        self.assertEqual(ok[0], 200)
        self.assertEqual(self.call("GET", "/admin/auth/me", token=root)[0], 401)  # old session ended
        self.admin_login(ADMIN_USER, "new-pass-123")


def tiny_png(w=3, h=2) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    raw = b"".join(b"\x00" + b"\xff\x99\x33" * w for _ in range(h))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


class CmsTests(ApiTestCase):
    def upload(self, data, token, content_type="image/png", name="ghat.png"):
        resp = self.client.post(f"/api/v1/admin/media?name={name}", data=data, content_type=content_type, HTTP_AUTHORIZATION=f"Bearer {token}")
        return resp.status_code, resp.json()

    def test_page_text_edit_and_reset(self):
        admin = self.admin_login()
        self.assertEqual(self.call("GET", "/content/home"), (200, {}))
        status, rows = self.call("PUT", "/admin/content/home", {"values": {"home.hero.title": "Jai Godavari", "home.hero.subtitle": "Hi"}}, token=admin)
        self.assertEqual(status, 200, rows)
        self.assertEqual({r["key"]: r["updated_by_name"] for r in rows}, {"home.hero.title": "Root Admin", "home.hero.subtitle": "Root Admin"})
        self.assertEqual(self.call("GET", "/content/home")[1], {"home.hero.title": "Jai Godavari", "home.hero.subtitle": "Hi"})
        # null resets a field to the built-in text
        self.call("PUT", "/admin/content/home", {"values": {"home.hero.subtitle": None}}, token=admin)
        self.assertEqual(self.call("GET", "/content/home")[1], {"home.hero.title": "Jai Godavari"})
        # keys must belong to the page being saved, and look like keys
        self.assertEqual(self.call("PUT", "/admin/content/home", {"values": {"about.hero.title": "x"}}, token=admin)[0], 422)
        self.assertEqual(self.call("PUT", "/admin/content/home", {"values": {"home.<script>": "x"}}, token=admin)[0], 422)

    def test_only_admins_edit_content(self):
        user = self.login()["access_token"]
        body = {"values": {"home.hero.title": "x"}}
        self.assertEqual(self.call("PUT", "/admin/content/home", body, token=user)[0], 401)
        self.assertEqual(self.call("PUT", "/admin/content/home", body)[0], 401)

    def test_image_upload_serve_and_delete(self):
        admin = self.admin_login()
        png = tiny_png()
        status, m = self.upload(png, admin)
        self.assertEqual(status, 201, m)
        self.assertEqual((m["width"], m["height"], m["content_type"], m["url"]), (3, 2, "image/png", f"/media/{m['id']}.png"))

        served = self.client.get(f"/api/v1{m['url']}")
        self.assertEqual((served.status_code, served.content, served["Content-Type"]), (200, png, "image/png"))
        self.assertIn("immutable", served["Cache-Control"])
        self.assertEqual(self.client.get(f"/api/v1/media/{m['id']}.jpg").status_code, 404)

        # Not an image (an SVG with a script, sent as PNG) is refused by its bytes.
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        self.assertEqual(self.upload(svg, admin)[0], 415)

        # In use on a page: can't be deleted until replaced there.
        self.call("PUT", "/admin/content/home", {"values": {"home.hero.image": m["url"]}}, token=admin)
        self.assertEqual(self.call("DELETE", f"/admin/media/{m['id']}", token=admin)[0], 409)
        self.call("PUT", "/admin/content/home", {"values": {"home.hero.image": None}}, token=admin)
        self.assertEqual(self.call("DELETE", f"/admin/media/{m['id']}", token=admin)[0], 200)
        self.assertEqual(self.call("GET", "/admin/media", token=admin)[1], [])
        self.assertFalse(MediaFile.objects.exists())

    def test_upload_size_limits(self):
        admin = self.admin_login()
        big = tiny_png() + b"\x00" * (5 * 1024 * 1024)
        self.assertEqual(self.upload(big, admin)[0], 413)
        # Other endpoints keep the small body limit.
        resp = self.client.put("/api/v1/admin/content/home", data=b"x" * 70_000, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {admin}")
        self.assertEqual(resp.status_code, 413)
