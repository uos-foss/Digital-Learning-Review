"""
Checks the production URL setup, starting Django the way gunicorn does.

    cd web
    ../.venv-django/Scripts/python check_prefix.py

smoke.py cannot catch this class of fault: it runs in debug with no path
prefix, and Django is set up differently there. Under gunicorn,
get_wsgi_application() starts Django WITHOUT setting the script prefix, so a
relative STATIC_URL is read, joined to "/" and cached before the first request
knows it is served under /module-reports. Pages then ask Caddy for
/static/..., which it does not route, and the admin renders with no CSS. That
happened on first deployment (12-10-2026); this keeps it from coming back.

Exits non-zero on any failure. Needs no database and reads nothing real.
"""

import os
import sys

PREFIX = "/module-reports"

os.environ.update(
    DJANGO_SETTINGS_MODULE="dlr.settings", DJANGO_DEBUG="0",
    DJANGO_SECRET_KEY="k" * 50, DJANGO_ALLOWED_HOSTS="example.test",
    DJANGO_SCRIPT_NAME=PREFIX)


def main():
    from django.core.wsgi import get_wsgi_application

    app = get_wsgi_application()          # gunicorn's entry point, deliberately

    from django.conf import settings
    from django.templatetags.static import static
    from django.test.client import RequestFactory

    failures = []

    def check(label, ok, detail=""):
        print(f"{'PASS' if ok else 'FAIL'}  {label}{(' - ' + detail) if detail else ''}")
        if not ok:
            failures.append(label)

    def call(path):
        environ = RequestFactory().get(
            path, HTTP_HOST="example.test", HTTP_X_FORWARDED_PROTO="https").environ
        status = []
        body = b"".join(app(environ, lambda s, h, e=None: status.append(s)))
        return status[0], body

    call("/accounts/login/")              # a first request, as in production

    check("static URLs carry the prefix", static("admin/css/base.css")
          == f"{PREFIX}/static/admin/css/base.css", static("admin/css/base.css"))
    # Caddy's handle_path strips the prefix, so this is what reaches Django.
    status, _ = call("/static/admin/css/base.css")
    check("the stripped path still serves the file (needs collectstatic)",
          status.startswith("200"), status)
    check("cookies are scoped to the prefix and Secure",
          settings.SESSION_COOKIE_PATH == PREFIX + "/" and settings.SESSION_COOKIE_SECURE)
    status, _ = call("/modules/ALA102/")
    check("sign-in redirect keeps the prefix", status.startswith("302"), status)

    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
