"""Admin Notifications — EYE-FONCIER."""
from django.contrib import admin
from django.utils.html import format_html
from .models import Notification, NotificationLog, NotificationPreference


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = [
        "title_short",
        "recipient",
        "type_badge",
        "channel_badge",
        "priority_badge",
        "is_read",
        "is_sent",
        "retry_count",
        "created_at",
    ]
    list_filter = [
        "notification_type",
        "channel",
        "priority",
        "is_read",
        "is_sent",
        "created_at",
    ]
    search_fields = ["title", "recipient__email", "recipient__first_name"]
    readonly_fields = [
        "id",
        "recipient",
        "notification_type",
        "channel",
        "priority",
        "title",
        "message",
        "data",
        "is_read",
        "read_at",
        "is_sent",
        "sent_at",
        "error_message",
        "retry_count",
        "created_at",
    ]
    list_per_page = 50

    def title_short(self, obj):
        return obj.title[:60] + ("..." if len(obj.title) > 60 else "")

    title_short.short_description = "Titre"

    def type_badge(self, obj):
        colors = {
            "transaction_status": "#2563eb",
            "payment_confirmed": "#16a34a",
            "payment_reminder": "#f59e0b",
            "match_found": "#8b5cf6",
            "visit_request": "#0891b2",
            "visit_confirmed": "#0891b2",
            "kyc_update": "#64748b",
            "escrow_update": "#ea580c",
            "parcelle_published": "#059669",
            "parcelle_validated": "#16a34a",
            "parcelle_rejected": "#dc2626",
            "parcelle_interest": "#7c3aed",
            "new_message": "#2563eb",
            "new_review": "#d97706",
            "client_request": "#0284c7",
            "account_update": "#475569",
            "welcome": "#10b981",
            "system": "#374151",
        }
        display = str(obj.get_notification_type_display())
        color = colors.get(obj.notification_type, "#6b7280")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px">{}</span>',
            color,
            display,
        )

    type_badge.short_description = "Type"

    def channel_badge(self, obj):
        icons = {
            "inapp": "bell",
            "email": "envelope",
            "sms": "phone",
            "whatsapp": "comment-dots",
            "push": "broadcast",
        }
        colors = {
            "inapp": "#6b7280",
            "email": "#2563eb",
            "sms": "#059669",
            "whatsapp": "#25D366",
            "push": "#f59e0b",
        }
        icon = icons.get(obj.channel, "circle")
        color = colors.get(obj.channel, "#6b7280")
        return format_html(
            '<i class="fas fa-{}" style="color:{}" title="{}"></i>',
            icon,
            color,
            str(obj.get_channel_display()),
        )

    channel_badge.short_description = "Canal"

    def priority_badge(self, obj):
        colors = {
            "low": "#9ca3af",
            "normal": "#3b82f6",
            "high": "#f59e0b",
            "urgent": "#ef4444",
        }
        color = colors.get(obj.priority, "#6b7280")
        return format_html(
            '<span style="color:{};font-weight:600;font-size:11px">{}</span>',
            color,
            str(obj.get_priority_display()),
        )

    priority_badge.short_description = "Priorité"

    def has_add_permission(self, request):
        return False


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "email_enabled",
        "sms_enabled",
        "whatsapp_enabled",
        "whatsapp_verified",
        "push_enabled",
        "inapp_enabled",
        "quiet_hours_start",
        "quiet_hours_end",
    ]
    list_filter = [
        "email_enabled",
        "sms_enabled",
        "whatsapp_enabled",
        "whatsapp_verified",
        "push_enabled",
    ]
    search_fields = ["user__email", "user__first_name"]
    readonly_fields = ["whatsapp_verified"]


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = [
        "notification_short",
        "status_badge",
        "channel_badge",
        "provider",
        "provider_message_id_short",
        "created_at",
    ]
    list_filter = ["status", "channel", "provider", "created_at"]
    search_fields = [
        "notification__title",
        "notification__recipient__email",
        "provider_message_id",
    ]
    readonly_fields = [
        "id",
        "notification",
        "status",
        "channel",
        "provider",
        "provider_message_id",
        "error_detail",
        "response_data",
        "created_at",
    ]
    list_per_page = 50

    def notification_short(self, obj):
        title = obj.notification.title
        return title[:50] + ("..." if len(title) > 50 else "")

    notification_short.short_description = "Notification"

    def status_badge(self, obj):
        colors = {
            "queued": "#6b7280",
            "sending": "#3b82f6",
            "sent": "#16a34a",
            "delivered": "#059669",
            "failed": "#ef4444",
            "retrying": "#f59e0b",
        }
        color = colors.get(obj.status, "#6b7280")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px">{}</span>',
            color,
            str(obj.get_status_display()),
        )

    status_badge.short_description = "Statut"

    def channel_badge(self, obj):
        return format_html(
            '<span style="font-size:11px">{}</span>',
            str(obj.get_channel_display()),
        )

    channel_badge.short_description = "Canal"

    def provider_message_id_short(self, obj):
        mid = obj.provider_message_id
        if len(mid) > 20:
            return mid[:20] + "..."
        return mid

    provider_message_id_short.short_description = "ID Message"

    def has_add_permission(self, request):
        return False
