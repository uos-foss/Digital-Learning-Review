"""
What the sign-in page needs to know about its own configuration.

allauth's `{% get_providers %}` lists Google whether or not a client id is
set, so a server with no credentials would show a button that fails on click.
This says plainly whether the button can work, so the page can explain itself
instead.
"""

from django.conf import settings


def signin_state(request):
    google = (settings.SOCIALACCOUNT_PROVIDERS or {}).get("google", {})
    app = google.get("APP") or {}
    return {
        "google_configured": bool((app.get("client_id") or "").strip()
                                  and (app.get("secret") or "").strip()),
        "allowed_email_domain": getattr(settings, "ALLOWED_EMAIL_DOMAIN", ""),
    }
