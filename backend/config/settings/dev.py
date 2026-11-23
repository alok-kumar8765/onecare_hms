from .base import *  # noqa: F401,F403

DEBUG = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Explicit safeguard: 'development' licensing provider is isolated to non-production settings.
assert LICENSE_PROVIDER == "development", "Dev settings must use 'development' license provider."  # noqa: F405