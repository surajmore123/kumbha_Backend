"""
Production settings. They start from `local.py`, tighten what must be tight, and
refuse to start rather than run with a missing or development secret.

Not active yet: `docker-compose.prod.yml` still names `config.settings.local`.
See docs/production_readiness.md in the app repository before switching it.
"""

import os

from django.core.exceptions import ImproperlyConfigured

from .local import *  # noqa: F403
from .local import SIMPLE_JWT

_DEVELOPMENT_VALUES = {"", "dev-secret-key", "change-me", "changeme", "secret"}
_MINIMUM_SECRET_LENGTH = 32


def _secret(name):
    value = os.getenv(name, "")
    if value.lower() in _DEVELOPMENT_VALUES or len(value) < _MINIMUM_SECRET_LENGTH:
        raise ImproperlyConfigured(f"{name} must be set to a strong value of at least 32 characters.")
    return value


def _hosts(name, default):
    return [host.strip() for host in os.getenv(name, default).split(",") if host.strip()]


DEBUG = False
SECRET_KEY = _secret("SECRET_KEY")
JWT_SECRET_KEY = _secret("JWT_SECRET_KEY")
SIMPLE_JWT = {**SIMPLE_JWT, "SIGNING_KEY": JWT_SECRET_KEY}
SAFETY_QR_SECRET = _secret("SAFETY_QR_SECRET")

ALLOWED_HOSTS = _hosts("ALLOWED_HOSTS", "kumbhapath.in,www.kumbhapath.in,api.kumbhapath.in")
CSRF_TRUSTED_ORIGINS = [f"https://{host}" for host in ALLOWED_HOSTS]

# The app isn't a browser, so CORS only concerns the website.
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = _hosts("CORS_ALLOWED_ORIGINS", "https://kumbhapath.in,https://www.kumbhapath.in")
CORS_ALLOW_CREDENTIALS = True

# TLS ends at Nginx, which must set X-Forwarded-Proto.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^api/health/"]
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "3600"))
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"

MOBILE_OTP_MODE = "sms"

# Shared, so sign-in locks and rate limits hold across every gunicorn worker.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.getenv("CACHE_URL", "redis://redis:6379/1"),
    },
}

# Wide enough for shared mobile networks, where many pilgrims share one address.
REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"anon": "600/minute", "user": "300/minute"},
    "NUM_PROXIES": int(os.getenv("NUM_PROXIES", "1")),
}
