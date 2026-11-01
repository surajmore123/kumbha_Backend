"""
Sign-in codes for the mobile app.

`MOBILE_OTP_MODE = "fixed"` is the development code, which proves nothing about
who is signing in and must never reach real users. `"sms"` sends a random code
through the website's existing SMS integration and stores only a keyed hash.
"""

from datetime import timedelta
import hmac
import logging

from django.conf import settings
from django.utils import timezone

from apps.authentication.models import Otp
from apps.website.core import generate_otp, hash_otp, verify_otp_hash
from apps.website.integrations import get_sms_sender

logger = logging.getLogger(__name__)

FIXED_CODE = "111111"
CODE_LENGTH = 6
LIFETIME = timedelta(minutes=5)
MAX_ATTEMPTS = 5


class OtpDeliveryFailed(Exception):
    """The code couldn't be sent, so nobody should wait for it."""


def uses_sms():
    return settings.MOBILE_OTP_MODE == "sms"


def _expiry():
    return timezone.now() + LIFETIME


def issue(user):
    if not uses_sms():
        return Otp.objects.create(user=user, otp_code=FIXED_CODE, expiry_time=_expiry())

    sender = get_sms_sender()
    # The console sender writes codes to the log, which is only for development.
    if sender.name == "console":
        logger.error("SMS sign-in is on but no SMS provider is configured.")
        raise OtpDeliveryFailed
    code = generate_otp(CODE_LENGTH)
    Otp.objects.filter(user=user, is_used=False).update(is_used=True)
    row = Otp.objects.create(
        user=user, otp_code="", code_hash=hash_otp(user.phone_number, code), expiry_time=_expiry(),
    )
    try:
        sender.send_otp(user.phone_number.removeprefix("+91"), code)
    except Exception as failure:
        logger.warning("OTP delivery failed (%s).", type(failure).__name__)
        row.is_used = True
        row.save(update_fields=["is_used"])
        raise OtpDeliveryFailed from failure
    return row


def matches(row, phone_number, code):
    """A wrong guess counts against the code, which stops working after a few."""
    if not uses_sms():
        return hmac.compare_digest(row.otp_code, code)
    # Anything issued before SMS was turned on has no hash and can't be used.
    if row.code_hash and verify_otp_hash(phone_number, code, row.code_hash):
        return True
    row.attempts += 1
    row.is_used = row.attempts >= MAX_ATTEMPTS or not row.code_hash
    row.save(update_fields=["attempts", "is_used"])
    return False
