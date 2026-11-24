import os
from django.core.exceptions import ImproperlyConfigured
from .base import *  # noqa: F401, F403

DJANGO_ENV = "production"
DEBUG = False

if LICENSE_PROVIDER == "development":  # noqa: F405
    raise ImproperlyConfigured("LICENSE_PROVIDER='development' is forbidden in production.")

SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY or SECRET_KEY.startswith("django-insecure") or SECRET_KEY.startswith("dev-only-"):
    raise ImproperlyConfigured("A strong production SECRET_KEY must be configured.")

LICENSE_PUBLIC_KEY = os.environ.get("LICENSE_PUBLIC_KEY", "")
if not LICENSE_PUBLIC_KEY:
    raise ImproperlyConfigured("LICENSE_PUBLIC_KEY environment variable is required in production.")

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("ALLOWED_HOSTS", "").split(",")
    if host.strip()
]
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS must not be empty in production.")

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

# Default SQLite fallback until pushing to live server.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
       # "ATOMIC_REQUESTS": False,
    }
}

# --- PostgreSQL (Uncomment when deploying to live server) ---
# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.postgresql",
#         "NAME": os.environ.get("DB_NAME", "onecare_hms"),
#         "USER": os.environ.get("DB_USER", "onecare_user"),
#         "PASSWORD": os.environ.get("DB_PASSWORD", ""),
#         "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
#         "PORT": os.environ.get("DB_PORT", "5432"),
#         "CONN_MAX_AGE": 60,
#         "OPTIONS": {"sslmode": os.environ.get("DB_SSLMODE", "prefer")},
#         "ATOMIC_REQUESTS": False,
#     }
# }

# --- MySQL / MariaDB (Uncomment when deploying to live server) ---
# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.mysql",
#         "NAME": os.environ.get("DB_NAME", "onecare_hms"),
#         "USER": os.environ.get("DB_USER", "onecare_user"),
#         "PASSWORD": os.environ.get("DB_PASSWORD", ""),
#         "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
#         "PORT": os.environ.get("DB_PORT", "3306"),
#         "CONN_MAX_AGE": 60,
#         "OPTIONS": {"charset": "utf8mb4"},
#         "ATOMIC_REQUESTS": False,
#     }
# }

# Security & HTTPS Hardening
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "True").lower() == "true"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True