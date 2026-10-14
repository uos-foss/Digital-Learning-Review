from django.contrib import admin
from django.urls import include, path

from modules.views import home

urlpatterns = [
    path("", home, name="home"),
    path("modules/", include("modules.urls")),
    path("schools/", include("modules.school_urls")),
    # Sign-in, sign-out and the Google callback. allauth owns these URLs; the
    # Google project's authorised redirect URI is
    # <host>/accounts/google/login/callback/.
    path("accounts/", include("allauth.urls")),
    path("admin/", admin.site.urls),
]
