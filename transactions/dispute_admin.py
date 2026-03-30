"""
Administration des litiges — EYE-FONCIER
Panel d'administration complet pour la gestion des litiges.
"""
from django.contrib import admin
from django.utils.html import format_html

from .dispute_models import Dispute, DisputeEvidence, DisputeMessage


class DisputeEvidenceInline(admin.TabularInline):
    model = DisputeEvidence
    extra = 0
    readonly_fields = ["id", "uploaded_by", "evidence_type", "title", "file", "file_size", "verified", "created_at"]
    fields = ["evidence_type", "title", "file", "file_size", "uploaded_by", "verified", "verified_by", "created_at"]


class DisputeMessageInline(admin.StackedInline):
    model = DisputeMessage
    extra = 0
    readonly_fields = ["id", "sender", "sender_role", "content", "is_internal", "created_at"]
    fields = ["sender", "sender_role", "content", "attachment", "is_internal", "created_at"]
    ordering = ["-created_at"]


@admin.register(Dispute)
class DisputeAdmin(admin.ModelAdmin):
    list_display = [
        "reference", "transaction_ref", "category_badge", "priority_badge",
        "status_badge", "opened_by", "assigned_to", "deadline_display",
        "days_open", "created_at",
    ]
    list_filter = ["status", "category", "priority", "created_at"]
    search_fields = [
        "reference", "subject", "transaction__reference",
        "opened_by__email", "assigned_to__email",
    ]
    readonly_fields = [
        "id", "reference", "created_at", "updated_at",
        "escalated_at", "resolved_at", "closed_at",
        "refund_processed_at", "days_open",
    ]
    date_hierarchy = "created_at"
    list_per_page = 25
    inlines = [DisputeEvidenceInline, DisputeMessageInline]

    fieldsets = (
        ("Litige", {
            "fields": (
                "reference", "transaction", "opened_by", "assigned_to",
                "category", "priority", "status",
            ),
        }),
        ("Description", {
            "fields": ("subject", "description"),
        }),
        ("Resolution", {
            "fields": (
                "resolution_type", "resolution_notes",
                "refund_amount", "refund_processed", "refund_processed_at",
            ),
            "classes": ("collapse",),
        }),
        ("Delais", {
            "fields": ("deadline", "escalated_at", "resolved_at", "closed_at"),
        }),
        ("Metadata", {
            "fields": ("metadata",),
            "classes": ("collapse",),
        }),
    )

    actions = [
        "assign_to_me", "mark_under_review", "start_mediation",
        "escalate", "close_disputes",
    ]

    @admin.display(description="Transaction")
    def transaction_ref(self, obj):
        return obj.transaction.reference

    @admin.display(description="Categorie")
    def category_badge(self, obj):
        colors = {
            "fraud": "#dc2626", "non_conformity": "#ea580c",
            "payment": "#f59e0b", "docs_missing": "#6366f1",
            "boundary": "#8b5cf6", "title_issue": "#ef4444",
            "seller_no_response": "#64748b", "buyer_withdrawal": "#0ea5e9",
            "other": "#6b7280",
        }
        color = colors.get(obj.category, "#6b7280")
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;'
            'border-radius:12px;font-size:11px;font-weight:600;">{}</span>',
            color, obj.get_category_display(),
        )

    @admin.display(description="Priorite")
    def priority_badge(self, obj):
        colors = {
            "low": "#6b7280", "normal": "#3b82f6",
            "high": "#f59e0b", "urgent": "#dc2626",
        }
        icons = {"low": "↓", "normal": "→", "high": "↑", "urgent": "⚡"}
        color = colors.get(obj.priority, "#6b7280")
        icon = icons.get(obj.priority, "")
        return format_html(
            '<span style="color:{};font-weight:700;">{} {}</span>',
            color, icon, obj.get_priority_display(),
        )

    @admin.display(description="Statut")
    def status_badge(self, obj):
        colors = {
            "opened": "#ef4444", "under_review": "#f59e0b",
            "mediation": "#8b5cf6", "escalated": "#dc2626",
            "resolved": "#22c55e", "closed": "#6b7280",
        }
        color = colors.get(obj.status, "#6b7280")
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;'
            'border-radius:12px;font-size:11px;font-weight:600;">{}</span>',
            color, obj.get_status_display(),
        )

    @admin.display(description="Deadline")
    def deadline_display(self, obj):
        if not obj.deadline:
            return "—"
        if obj.is_overdue:
            return format_html(
                '<span style="color:#dc2626;font-weight:700;">{} (DEPASSE)</span>',
                obj.deadline.strftime("%d/%m/%Y"),
            )
        return obj.deadline.strftime("%d/%m/%Y")

    @admin.display(description="Jours")
    def days_open(self, obj):
        days = obj.days_since_opened
        if days > 14:
            color = "#dc2626"
        elif days > 7:
            color = "#f59e0b"
        else:
            color = "#22c55e"
        return format_html(
            '<span style="color:{};font-weight:600;">{}j</span>',
            color, days,
        )

    @admin.action(description="M'assigner ces litiges")
    def assign_to_me(self, request, queryset):
        count = 0
        for dispute in queryset.filter(assigned_to__isnull=True):
            dispute.assigned_to = request.user
            if dispute.status == "opened":
                dispute.status = "under_review"
            dispute.save()
            count += 1
        self.message_user(request, "{} litige(s) assigne(s).".format(count))

    @admin.action(description="Passer en examen")
    def mark_under_review(self, request, queryset):
        count = queryset.filter(status="opened").update(status="under_review")
        self.message_user(request, "{} litige(s) en examen.".format(count))

    @admin.action(description="Demarrer la mediation")
    def start_mediation(self, request, queryset):
        count = queryset.filter(
            status__in=["opened", "under_review"]
        ).update(status="mediation")
        self.message_user(request, "{} litige(s) en mediation.".format(count))

    @admin.action(description="Escalader (juridique)")
    def escalate(self, request, queryset):
        from django.utils import timezone
        count = 0
        for d in queryset.exclude(status__in=["resolved", "closed"]):
            d.status = "escalated"
            d.escalated_at = timezone.now()
            d.save()
            count += 1
        self.message_user(request, "{} litige(s) escalade(s).".format(count))

    @admin.action(description="Clore les litiges")
    def close_disputes(self, request, queryset):
        from django.utils import timezone
        count = 0
        for d in queryset.filter(status="resolved"):
            d.status = "closed"
            d.closed_at = timezone.now()
            d.save()
            count += 1
        self.message_user(request, "{} litige(s) clos.".format(count))


@admin.register(DisputeEvidence)
class DisputeEvidenceAdmin(admin.ModelAdmin):
    list_display = ["dispute", "evidence_type", "title", "uploaded_by", "verified", "created_at"]
    list_filter = ["evidence_type", "verified"]
    search_fields = ["title", "dispute__reference"]
    readonly_fields = ["id", "file_size", "created_at"]

    actions = ["verify_evidences"]

    @admin.action(description="Marquer comme verifie")
    def verify_evidences(self, request, queryset):
        from django.utils import timezone
        count = queryset.filter(verified=False).update(
            verified=True,
            verified_by=request.user,
            verified_at=timezone.now(),
        )
        self.message_user(request, "{} piece(s) verifiee(s).".format(count))


@admin.register(DisputeMessage)
class DisputeMessageAdmin(admin.ModelAdmin):
    list_display = ["dispute", "sender", "sender_role", "content_preview", "is_internal", "created_at"]
    list_filter = ["sender_role", "is_internal"]
    search_fields = ["content", "dispute__reference"]
    readonly_fields = ["id", "created_at"]

    @admin.display(description="Message")
    def content_preview(self, obj):
        return obj.content[:80] + ("..." if len(obj.content) > 80 else "")
