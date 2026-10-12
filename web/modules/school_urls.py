from django.urls import path

from modules import views

app_name = "schools"

urlpatterns = [
    path("", views.school_index, name="index"),
    path("<str:school>/", views.school_dashboard, name="dashboard"),
]
