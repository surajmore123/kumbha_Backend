"""Settings for the website API, read from KP_* environment variables (same names the old FastAPI
backend used, so its production values can be copied over unchanged)."""

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache

DEV_SECRET = "dev-only-insecure-secret-change-me-0000000000"


def _list(name: str) -> list[str]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return []
    if raw.startswith("["):
        return [str(v) for v in json.loads(raw)]
    return [v.strip() for v in raw.split(",") if v.strip()]


@dataclass(frozen=True)
class WebsiteSettings:
    env: str = "dev"
    secret_key: str = DEV_SECRET
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    redis_url: str | None = None
    max_body_bytes: int = 64_000
    rate_limit_per_minute: int = 120
    admin_phones: list[str] = field(default_factory=list)
    admin_emails: list[str] = field(default_factory=list)
    google_client_id: str | None = None

    otp_length: int = 6
    otp_ttl_seconds: int = 300
    otp_max_attempts: int = 3
    otp_lock_minutes: int = 15
    otp_resend_seconds: int = 45
    otp_daily_limit: int = 10

    sms_provider: str = "console"
    msg91_auth_key: str | None = None
    msg91_template_id: str | None = None
    whatsapp_token: str | None = None
    whatsapp_phone_number_id: str | None = None
    whatsapp_api_version: str = "v21.0"
    enquiry_notify_to: str | None = None
    partner_feed_url: str | None = None
    partner_feed_key: str | None = None
    provider_timeout_seconds: float = 4.0

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"


@lru_cache
def get_settings() -> WebsiteSettings:
    env = lambda name, default=None: os.getenv(name) or default  # noqa: E731
    s = WebsiteSettings(
        env=env("KP_ENV", "dev"),
        secret_key=env("KP_SECRET_KEY", DEV_SECRET),
        redis_url=env("KP_REDIS_URL"),
        admin_phones=_list("KP_ADMIN_PHONES"),
        admin_emails=[e.lower() for e in _list("KP_ADMIN_EMAILS")],
        google_client_id=env("KP_GOOGLE_CLIENT_ID"),
        sms_provider=env("KP_SMS_PROVIDER", "console"),
        msg91_auth_key=env("KP_MSG91_AUTH_KEY"),
        msg91_template_id=env("KP_MSG91_TEMPLATE_ID"),
        whatsapp_token=env("KP_WHATSAPP_TOKEN"),
        whatsapp_phone_number_id=env("KP_WHATSAPP_PHONE_NUMBER_ID"),
        enquiry_notify_to=env("KP_ENQUIRY_NOTIFY_TO"),
        partner_feed_url=env("KP_PARTNER_FEED_URL"),
        partner_feed_key=env("KP_PARTNER_FEED_KEY"),
    )
    if s.is_prod and (s.secret_key == DEV_SECRET or len(s.secret_key) < 32):
        raise RuntimeError("KP_SECRET_KEY must be set to a random value of at least 32 characters in prod")
    return s
