from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("", RedirectView.as_view(url="/modules/", permanent=False)),
    path("modules/", include("modules.urls")),
    # Sign-in, sign-out and the Google callback. allauth owns these URLs; the
    # Google project's authorised redirect URI is
    # <host>/accounts/google/login/callback/.
    path("accounts/", include("allauth.urls")),
    path("admin/", admin.site.urls),
]
