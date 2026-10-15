"""Mobile-app OTP codes: random, sent by SMS, stored only as a keyed hash, with expiry, a wrong-code
limit and resend limits. SMS goes through the same sender as the website (apps.website.integrations:
MSG91 in production, printed to the log with KP_SMS_PROVIDER=console).

Test numbers for the app team / store review (off unless both are set):
    APP_OTP_TEST_NUMBERS=9000000001,9000000002   APP_OTP_TEST_CODE=246810
Those numbers get the fixed code and no SMS; every other number gets a random code.
"""

import hmac
import logging
import os
import re
import secrets
from datetime import timedelta

from django.utils import timezone

from apps.website.core import enforce, hash_otp, AppError
from apps.website.integrations import get_sms_sender

from .models import Otp

log = logging.getLogger("apps.authentication.otp")

OTP_LENGTH = 6
OTP_TTL = timedelta(minutes=5)
MAX_ATTEMPTS = 3  # wrong codes before this OTP stops working
RESEND_SECONDS = 45
DAILY_LIMIT = 10


class OtpError(Exception):
    """Shown to the app as {"status": "error", "errors": {field: [message]}} with this HTTP status."""

    def __init__(self, status: int, message: str, field: str = "non_field_errors"):
        self.status, self.message, self.field = status, message, field


def normalize_phone(value: str) -> str | None:
    """'+91 98xxx', '9198…', '98…' -> 10 digits, or None if it isn't an Indian mobile number."""
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits if re.fullmatch(r"[6-9]\d{9}", digits) else None


def _test_code(phone10: str) -> str | None:
    numbers = {n.strip() for n in os.getenv("APP_OTP_TEST_NUMBERS", "").split(",") if n.strip()}
    code = os.getenv("APP_OTP_TEST_CODE", "").strip()
    return code if phone10 in numbers and re.fullmatch(r"\d{6}", code) else None


def send_otp(user, phone10: str) -> Otp:
    """Create a new OTP for this user and text it. Older unused codes stop working."""
    try:
        enforce(f"app-otp-resend:{phone10}", 1, RESEND_SECONDS)
        enforce(f"app-otp-daily:{phone10}", DAILY_LIMIT, 86_400)
    except AppError as exc:
        wait = exc.extra.get("retry_after", RESEND_SECONDS)
        raise OtpError(429, f"Please wait {wait} seconds before requesting another OTP.", "phone_number") from None

    test_code = _test_code(phone10)
    code = test_code or "".join(str(secrets.randbelow(10)) for _ in range(OTP_LENGTH))
    if not test_code:
        try:
            get_sms_sender().send_otp(phone10, code)
        except Exception:  # noqa: BLE001 - provider misconfigured or down
            log.exception("OTP SMS not sent")
            raise OtpError(503, "Could not send the OTP right now. Please try again in a few minutes.") from None

    Otp.objects.filter(user=user, is_used=False, is_del=0).update(is_del=1)
    return Otp.objects.create(user=user, otp_code=hash_otp(phone10, code), expiry_time=timezone.now() + OTP_TTL)


def check_otp(user, phone10: str, code: str) -> Otp:
    """Return the matching active OTP, or raise OtpError. Wrong codes count towards MAX_ATTEMPTS."""
    otp = Otp.objects.filter(user=user, is_used=False, is_del=0).order_by("-created_at").first()
    if otp is None:
        raise OtpError(400, "No active OTP found. Please request a new one.")
    if otp.is_expired():
        raise OtpError(400, "OTP has expired. Please request a new one.")
    if not hmac.compare_digest(otp.otp_code, hash_otp(phone10, code)):
        otp.attempts += 1
        if otp.attempts >= MAX_ATTEMPTS:
            otp.is_del = 1
            otp.save(update_fields=["attempts", "is_del", "updated_at"])
            raise OtpError(400, "Too many wrong codes. Please request a new OTP.")
        otp.save(update_fields=["attempts", "updated_at"])
        raise OtpError(400, "Invalid OTP code.")
    otp.is_used = True
    otp.save(update_fields=["is_used", "updated_at"])
    return otp
