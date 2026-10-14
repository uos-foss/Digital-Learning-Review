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


def site_name(request):
    """The site's name for every template (settings.SITE_NAME)."""
    return {"site_name": settings.SITE_NAME}


def nav_state(request):
    """What the header needs: the schools the signed-in account can see, and the
    one of them when there is exactly one (the link then reads "My school" and
    goes straight there)."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    from accounts.models import schools_of
    schools = schools_of(user)
    return {"nav_one_school": schools[0] if len(schools) == 1 else ""}
