"""
Local settings for KUMBHA_BACKEND.
"""
from datetime import timedelta
from pathlib import Path
import os
from dotenv import load_dotenv

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
CELERY_BROKER_URL = "redis://redis:6379/0"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "192.168.1.12","10.184.4.30","192.168.1.5","192.168.1.42","192.168.1.6","192.168.1.7","kumbha-backend.onrender.com"]

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
 
]

MIDDLEWARE = [
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
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
}



AUTH_USER_MODEL = "authentication.User"

STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
# STATICFILES_DIRS = [APPS_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
