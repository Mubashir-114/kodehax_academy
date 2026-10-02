from .settings import *  # noqa: F403,F401


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "test_db.sqlite3",  # noqa: F405
    }
}

ROOT_URLCONF = "kodehax_academy.test_urls"
SILENCED_SYSTEM_CHECKS = ["fields.E210"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
