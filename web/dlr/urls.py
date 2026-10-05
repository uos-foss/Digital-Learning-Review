from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("", RedirectView.as_view(url="/modules/", permanent=False)),
    path("modules/", include("modules.urls")),
    path("admin/", admin.site.urls),
]
