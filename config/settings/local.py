"""
Local settings for KUMBHA_BACKEND.
"""
from datetime import timedelta
from pathlib import Path
import os
from dotenv import load_dotenv

from utils.observability import logging_config

# Build paths inside the project like this: BASE_DIR / 'subdir'.
# local.py is at: config/settings/local.py
# So parent.parent.parent = KUMBHA_BACKEND
BASE_DIR = Path(__file__).resolve(strict=True).parent.parent.parent
APPS_DIR = BASE_DIR / "apps"
# Load envs/.env.local
ENV_FILE = BASE_DIR / "envs" / ".env.local"
load_dotenv(ENV_FILE)

# ==== CORE SETTINGS ===='
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
DEBUG = os.getenv("DEBUG", "True").lower() == "true"
# CELERY_BROKER_URL = "redis://127.0.0.1:6379/0"
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "192.168.1.2","10.184.4.30","192.168.1.6","192.168.1.42","192.168.1.5","0.0.0.0","kumbha-backend.onrender.com"]
# Extra hosts from the environment, comma separated (e.g. "api.kumbhapath.in")
ALLOWED_HOSTS += [h.strip() for h in os.getenv("EXTRA_ALLOWED_HOSTS", "").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS if "." in h and not h[0].isdigit()]
# Behind nginx, which terminates HTTPS
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.authentication",
    "apps.aiChat",
    "apps.temples",
    "apps.events",
    "django_celery_beat",
    "apps.crowd",
    "apps.journal",
    "apps.website",
    "apps.journeys",
    "apps.akhadas",
    "apps.news",
    "apps.learn",
    "apps.bookings",
    "apps.family",
    "apps.safety",
    "apps.lostfound",
    "apps.familylocation",
    "apps.reunification",
    "apps.notifications",
    "apps.emergency",
    "apps.operations",
 
]

MIDDLEWARE = [
    "utils.observability.RequestLogMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "corsheaders.middleware.CorsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_TIMEZONE = "Asia/Kolkata"
# ==== DATABASE: POSTGRES ====
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("RDS_DATABASE"),
        "USER": os.getenv("RDS_USERNAME"),
        "PASSWORD": os.getenv("RDS_PASSWORD"),
        "HOST": os.getenv("RDS_HOST", "localhost"),
        "PORT": os.getenv("RDS_PORT", "5432"),
    }
}

# ==== PASSWORD VALIDATION ====
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# ==== I18N / L10N ====
TIME_ZONE = "Asia/Kolkata"
USE_TZ = True

USE_I18N = True
USE_TZ = True



DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True


JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", SECRET_KEY)

# Derives Safety QR tokens. Set it in production and keep it: changing it stops
# every existing QR working until it's generated again.
SAFETY_QR_SECRET = os.getenv("SAFETY_QR_SECRET") or SECRET_KEY
SAFETY_REQUIRE_HTTPS = os.getenv("SAFETY_REQUIRE_HTTPS", str(not DEBUG)).lower() == "true"

# Walking routes for the reunification map. Without a key the app falls back
# to opening Google Maps. Needs the Routes API enabled on the key.
GOOGLE_ROUTES_API_KEY = os.getenv("GOOGLE_ROUTES_API_KEY", "")

# Numbers offered for a direct phone call on the SOS screen, as "label:number"
# separated by commas. These are calls from the phone, not app features.
EMERGENCY_NUMBERS = [
    {"label": item.split(":", 1)[0].strip(), "number": item.split(":", 1)[1].strip()}
    for item in os.getenv("EMERGENCY_NUMBERS", "emergency:112").split(",") if ":" in item
]
EMERGENCY_LOCATION_RETENTION_DAYS = int(os.getenv("EMERGENCY_LOCATION_RETENTION_DAYS", "30"))

# Volunteer accounts.
OPERATIONS_SETUP_CODE_HOURS = int(os.getenv("OPERATIONS_SETUP_CODE_HOURS", "48"))
OPERATIONS_DEFAULT_ZONE_RADIUS_M = int(os.getenv("OPERATIONS_DEFAULT_ZONE_RADIUS_M", "1500"))

# Family location sharing.
LOCATION_MAX_SHARE_HOURS = int(os.getenv("LOCATION_MAX_SHARE_HOURS", "12"))
LOCATION_UPDATE_SECONDS = int(os.getenv("LOCATION_UPDATE_SECONDS", "30"))
LOCATION_DISTANCE_METRES = int(os.getenv("LOCATION_DISTANCE_METRES", "25"))
LOCATION_POLL_SECONDS = int(os.getenv("LOCATION_POLL_SECONDS", "20"))
LOCATION_LIVE_SECONDS = int(os.getenv("LOCATION_LIVE_SECONDS", "120"))
LOCATION_RECENT_SECONDS = int(os.getenv("LOCATION_RECENT_SECONDS", "600"))
LOCATION_STALE_NOTICE_MINUTES = int(os.getenv("LOCATION_STALE_NOTICE_MINUTES", "30"))
LOCATION_SESSION_RETENTION_DAYS = int(os.getenv("LOCATION_SESSION_RETENTION_DAYS", "7"))

SIMPLE_JWT = {
    "SIGNING_KEY": JWT_SECRET_KEY,
    "ALGORITHM": "HS256",
    "ACCESS_TOKEN_LIFETIME": timedelta(days=7),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=14),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "user_id",
    "USER_ID_CLAIM": "user_id",
    "AUTH_TOKEN_CLASSES": ("apps.authentication.tokens.KumbhAccessToken",),
}



AUTH_USER_MODEL = "authentication.User"

# "fixed" is the development code. Production uses "sms".
MOBILE_OTP_MODE = os.getenv("MOBILE_OTP_MODE", "fixed")

LOGGING = logging_config(os.getenv("LOG_LEVEL", "INFO"))

STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
# STATICFILES_DIRS = [APPS_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"



# =====================================================================
# GURU AI (LangGraph + RAG chatbot)
# =====================================================================
AI = {
    "PROVIDER": os.getenv("AI_PROVIDER", "gemini"),
    "LOST_FOUND_ENABLED": os.getenv("AI_LOST_FOUND_ENABLED", "true").lower() == "true",
    "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY", ""),
    # Graph nodes ask for a *purpose*, never a model name.
    #   default: final answers to the user
    #   fast:    routing, language detection, query rewriting
    "MODELS": {
        "default": {
            "name": os.getenv("AI_CHAT_MODEL", "gemini-3.8-flash"),
            "thinking_level": os.getenv("AI_CHAT_THINKING", "low"),
        },
        "fast": {
            "name": os.getenv("AI_FAST_MODEL", "gemini-3.5-flash-lite"),
            "thinking_level": os.getenv("AI_FAST_THINKING", "minimal"),
        },
    },
    # gemini-embedding-2: 100+ languages, also supports images.
    # Changing model or dimension later = re-embedding the knowledge base.
    "EMBEDDING_MODEL": os.getenv("AI_EMBEDDING_MODEL", "gemini-embedding-2"),
    "EMBEDDING_DIM": int(os.getenv("AI_EMBEDDING_DIM", "768")),
    # Leave empty for Gemini 3+ models (Google recommends their default).
    "TEMPERATURE": float(os.getenv("AI_TEMPERATURE")) if os.getenv("AI_TEMPERATURE") else None,
    "TIMEOUT_SECONDS": int(os.getenv("AI_TIMEOUT_SECONDS", "30")),
    "MAX_RETRIES": int(os.getenv("AI_MAX_RETRIES", "2")),
    # Free tier ~10-15 requests/min. 0.15/sec = 9/min. Raise on a paid key.
    "REQUESTS_PER_SECOND": float(os.getenv("AI_REQUESTS_PER_SECOND", "0.15")),
}
