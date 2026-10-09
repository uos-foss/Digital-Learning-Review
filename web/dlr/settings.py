"""
Settings for the Django platform spike.

Two deliberate choices worth keeping if this goes further:

1. The repo root is on sys.path, so `import processing` / `import database`
   reach the same modules the Streamlit app uses. No copy, no package, no
   drift while both front ends exist. See CLAUDE.md on why one copy matters.

2. Two databases. 'default' is Django's own small SQLite file (sessions,
   migrations, users). 'audit' is the shared audit database that the Streamlit
   app and the AI-Audit app also read, and Django never migrates it. Keeping
   Django's plumbing tables out of the shared file matters: other apps read it
   and it is the thing that gets backed up.
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent      # <repo>/web
REPO_ROOT = BASE_DIR.parent                            # <repo>

# Reach processing.py / database.py at the repo root (choice 1 above).
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Spike only. A real deployment reads this from the environment and refuses to
# start without it.
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "spike-only-not-for-deployment")
DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_htmx",
    "auditdata",
    "modules",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "dlr.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
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

WSGI_APPLICATION = "dlr.wsgi.application"


def _shared_audit_db_path():
    """
    The shared audit database, found the same way the Streamlit app finds it,
    so both front ends always read the same file in every environment.
    """
    from database import get_database_path

    return get_database_path()


DATABASES = {
    # Django's own tables. Small, and ours alone.
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "dlr_platform.sqlite3",
    },
    # The shared audit database. Every model reading it is managed = False.
    "audit": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": _shared_audit_db_path(),
        "OPTIONS": {
            # The Streamlit app sets WAL and a busy timeout on its own
            # connections (database.py). Match the timeout here so a
            # concurrent write from either app waits rather than erroring.
            "timeout": 5,
        },
    },
}

DATABASE_ROUTERS = ["dlr.routers.AuditRouter"]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

# The existing scrypt hashes verify through the first hasher; new or changed
# passwords are written in Django's own default format. See
# dlr/hashers.py for why this is a read-only bridge, not a migration.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "dlr.hashers.LegacyScryptHasher",
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Europe/London"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/admin/login/"
LOGIN_REDIRECT_URL = "/modules/"
