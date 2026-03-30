"""API URL patterns Notifications — EYE-FONCIER."""
from django.urls import path
from . import api_views

app_name = "notifications_api"

urlpatterns = [
    path("", api_views.NotificationListAPIView.as_view(), name="list"),
    path("count/", api_views.UnreadCountAPIView.as_view(), name="count"),
    path("<uuid:pk>/read/", api_views.NotificationMarkReadAPIView.as_view(), name="mark_read"),
    path("all-read/", api_views.MarkAllReadAPIView.as_view(), name="mark_all_read"),
    path("preferences/", api_views.NotificationPreferenceAPIView.as_view(), name="preferences"),
    path("fcm-token/", api_views.RegisterFCMTokenAPIView.as_view(), name="register_fcm_token"),
    path("whatsapp/register/", api_views.RegisterWhatsAppAPIView.as_view(), name="register_whatsapp"),
    path("whatsapp/verify/", api_views.VerifyWhatsAppAPIView.as_view(), name="verify_whatsapp"),
]
