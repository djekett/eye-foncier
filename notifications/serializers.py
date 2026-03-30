"""Serializers Notifications — EYE-FONCIER."""
from rest_framework import serializers
from .models import Notification, NotificationPreference


class NotificationSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(
        source="get_notification_type_display", read_only=True
    )
    channel_display = serializers.CharField(
        source="get_channel_display", read_only=True
    )
    priority_display = serializers.CharField(
        source="get_priority_display", read_only=True
    )

    class Meta:
        model = Notification
        fields = [
            "id",
            "notification_type",
            "type_display",
            "channel",
            "channel_display",
            "priority",
            "priority_display",
            "title",
            "message",
            "data",
            "is_read",
            "read_at",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "notification_type",
            "channel",
            "priority",
            "title",
            "message",
            "data",
            "created_at",
        ]


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = [
            "email_enabled",
            "sms_enabled",
            "whatsapp_enabled",
            "push_enabled",
            "inapp_enabled",
            "whatsapp_number",
            "whatsapp_consent",
            "whatsapp_verified",
            "quiet_hours_start",
            "quiet_hours_end",
            "disabled_types",
        ]
        read_only_fields = ["whatsapp_verified"]
