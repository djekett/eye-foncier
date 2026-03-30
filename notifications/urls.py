"""URL patterns Notifications — EYE-FONCIER."""
from django.urls import path
from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.notification_list_view, name="list"),
    path("preferences/", views.preferences_view, name="preferences"),
    path("whatsapp/verifier/", views.verify_whatsapp_view, name="verify_whatsapp"),
    path("<uuid:pk>/lu/", views.mark_read_view, name="mark_read"),
    path("tout-lu/", views.mark_all_read_view, name="mark_all_read"),
]
