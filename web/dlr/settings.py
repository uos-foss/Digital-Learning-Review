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

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent      # <repo>/web
REPO_ROOT = BASE_DIR.parent                            # <repo>

# Reach processing.py / database.py at the repo root (choice 1 above).
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# The same .env the Streamlit app reads, so one VM has one place where
# credentials live. Without this, settings fall back to defaults and the
# Google client id reads as empty while sitting in the file two directories
# up, which is a confusing way to be unconfigured.
load_dotenv(REPO_ROOT / ".env")

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
    "django.contrib.sites",          # allauth needs it
    "django_htmx",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "accounts",
    "auditdata",
    "modules",
]

SITE_ID = 1

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    # allauth needs this, and it must sit after AuthenticationMiddleware.
    "allauth.account.middleware.AccountMiddleware",
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
                "accounts.context.signin_state",
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

# ---------------------------------------------------------------------------
# Sign-in
#
# Google, through allauth, with Django's own signed HttpOnly session cookie.
# That alone removes the forgeable-cookie problem the Streamlit app had: the
# CookieManager component writes from JavaScript and cannot set HttpOnly, so
# its cookie was readable and settable in devtools. See CLAUDE.md, "Auth".
#
# Institutional SSO (Entra ID, over OIDC) is the eventual target and an
# enquiry is outstanding with IT. Nothing below has to change for it except
# adding a provider and mapping its claims onto accounts.Profile: allauth
# takes providers side by side.
# ---------------------------------------------------------------------------

AUTHENTICATION_BACKENDS = [
    # Local accounts an admin created, including the break-glass superuser.
    "django.contrib.auth.backends.ModelBackend",
    # Google.
    "allauth.account.auth_backends.AuthenticationBackend",
]

ACCOUNT_ADAPTER = "accounts.adapters.AccountAdapter"
SOCIALACCOUNT_ADAPTER = "accounts.adapters.SocialAccountAdapter"

# Only university addresses may sign in, checked server side in the adapter
# against the email Google reports as verified.
ALLOWED_EMAIL_DOMAIN = os.getenv("ALLOWED_EMAIL_DOMAIN", "sheffield.ac.uk")

ACCOUNT_EMAIL_VERIFICATION = "none"      # Google has already verified it
ACCOUNT_LOGIN_METHODS = {"username", "email"}
ACCOUNT_SIGNUP_FIELDS = ["email*"]
SOCIALACCOUNT_LOGIN_ON_GET = True        # no extra "continue" click
SOCIALACCOUNT_AUTO_SIGNUP = True         # the adapter has already vetted them
SOCIALACCOUNT_STORE_TOKENS = False       # nothing here calls Google's APIs

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APP": {
            # Same Google project as the Streamlit app, which reads the same
            # two variables. The Django callback URL has to be added to that
            # project's authorised redirect URIs.
            "client_id": (os.getenv("GOOGLE_OAUTH_CLIENT_ID")
                          or os.getenv("GOOGLE_CLIENT_ID", "")),
            "secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
            "key": "",
        },
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {
            # A hint to the account chooser, not a control: see
            # accounts/adapters.py for why the real check is server side.
            "hd": os.getenv("ALLOWED_EMAIL_DOMAIN", "sheffield.ac.uk"),
        },
    },
}

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/modules/"
ACCOUNT_LOGOUT_REDIRECT_URL = "/accounts/login/"
ACCOUNT_LOGOUT_ON_GET = False            # logging out is a POST, so a link cannot do it
