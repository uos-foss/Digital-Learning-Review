from django.urls import path

from modules import views

app_name = "modules"

urlpatterns = [
    path("", views.module_index, name="index"),
    path("<str:code>/", views.module_report, name="report"),
]
