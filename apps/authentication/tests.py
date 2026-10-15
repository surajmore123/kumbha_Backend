import os
from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from apps.website import conf, core

from .models import Otp, User

PHONE = "9811111111"


class FakeSms:
    name = "fake"

    def __init__(self):
        self.sent = []

    def send_otp(self, phone, code):
        self.sent.append((phone, code))


class MobileOtpTests(TestCase):
    def setUp(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("KP_", "APP_OTP_"))}
        env["KP_ENV"] = "test"
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        conf.get_settings.cache_clear()
        self.addCleanup(conf.get_settings.cache_clear)
        core._limiter = None  # fresh in-memory rate limits
        self.sms = FakeSms()
        sms_patch = mock.patch("apps.authentication.otp.get_sms_sender", return_value=self.sms)
        sms_patch.start()
        self.addCleanup(sms_patch.stop)

    def send(self, phone=PHONE):
        return self.client.post("/api/auth/send-mobile-otp/", {"phone_number": phone}, content_type="application/json")

    def verify(self, code, phone=PHONE):
        return self.client.post("/api/auth/verify-mobile-otp/", {"phone_number": phone, "otp_code": code}, content_type="application/json")

    def test_random_code_is_texted_and_only_its_hash_stored(self):
        resp = self.send("+91 98111 11111")
        self.assertEqual(resp.status_code, 201, resp.json())
        self.assertEqual(set(resp.json()["data"]), {"user_id", "phone_number", "otp_id", "otp_verified"})
        self.assertEqual(len(self.sms.sent), 1)
        phone, code = self.sms.sent[0]
        self.assertEqual((phone, len(code)), (PHONE, 6))
        stored = Otp.objects.get().otp_code
        self.assertNotEqual(stored, code)
        self.assertEqual(len(stored), 64)

        resp = self.verify(code)
        self.assertEqual(resp.status_code, 200, resp.json())
        data = resp.json()["data"]
        self.assertEqual(data["phone_number"], f"+91{PHONE}")
        self.assertTrue(data["access_token"])
        self.assertEqual(self.verify(code).status_code, 400)  # single use

    def test_fixed_111111_no_longer_works(self):
        self.send()
        if self.sms.sent[0][1] == "111111":  # 1 in a million: pick a different wrong code
            self.skipTest("random code happened to be 111111")
        resp = self.verify("111111")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["errors"]["non_field_errors"], ["Invalid OTP code."])

    def test_three_wrong_codes_end_the_otp(self):
        self.send()
        code = self.sms.sent[0][1]
        wrong = "000000" if code != "000000" else "999999"
        self.assertEqual(self.verify(wrong).json()["errors"]["non_field_errors"], ["Invalid OTP code."])
        self.verify(wrong)
        resp = self.verify(wrong)
        self.assertEqual(resp.json()["errors"]["non_field_errors"], ["Too many wrong codes. Please request a new OTP."])
        self.assertEqual(self.verify(code).status_code, 400)  # even the right code is now refused

    def test_expired_code(self):
        self.send()
        Otp.objects.update(expiry_time=timezone.now() - timedelta(seconds=1))
        resp = self.verify(self.sms.sent[0][1])
        self.assertEqual(resp.json()["errors"]["non_field_errors"], ["OTP has expired. Please request a new one."])

    def test_resend_gap_and_newest_code_only(self):
        self.send()
        resp = self.send()
        self.assertEqual(resp.status_code, 429)
        self.assertIn("phone_number", resp.json()["errors"])
        core._limiter = None  # pretend the gap has passed
        self.send()
        first, second = self.sms.sent[0][1], self.sms.sent[1][1]
        if first != second:
            self.assertEqual(self.verify(first).status_code, 400)
        self.assertEqual(self.verify(second).status_code, 200)

    def test_sms_failure_is_reported(self):
        self.sms.send_otp = mock.Mock(side_effect=RuntimeError("no template"))
        resp = self.send()
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()["status"], "error")
        self.assertFalse(Otp.objects.exists())

    def test_test_numbers_get_the_fixed_code_without_sms(self):
        with mock.patch.dict(os.environ, {"APP_OTP_TEST_NUMBERS": "9000000001", "APP_OTP_TEST_CODE": "246810"}):
            self.assertEqual(self.send("9000000001").status_code, 201)
            self.assertEqual(self.sms.sent, [])
            self.assertEqual(self.verify("246810", "9000000001").status_code, 200)
            self.send()  # other numbers still get a random texted code
            self.assertEqual(len(self.sms.sent), 1)

    def test_same_account_as_existing_number_without_prefix(self):
        existing = User.objects.create(phone_number=PHONE)
        self.send()
        self.assertEqual(User.objects.count(), 1)
        resp = self.verify(self.sms.sent[0][1])
        self.assertEqual(resp.json()["data"]["user_id"], str(existing.user_id))

    def test_invalid_input(self):
        self.assertEqual(self.send("12345").status_code, 400)
        self.assertEqual(self.verify("12ab56").status_code, 400)
