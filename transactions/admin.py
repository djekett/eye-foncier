"""Administration transactions — EYE-FONCIER.
Audit complet : format_html sécurisé, aucun formatage numérique dans format_html.
"""
from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Transaction, BonDeVisite, FinancialScore, SimulationResult,
    TransactionEvent, TransactionApproval,
)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = [
        "reference", "parcelle", "buyer", "seller", "amount_formatted",
        "status_color_badge", "escrow_info", "progress_bar", "created_at",
    ]
    list_filter = ["status", "payment_method", "escrow_funded", "compromis_generated"]
    search_fields = [
        "reference", "parcelle__lot_number",
        "buyer__email", "seller__email",
    ]
    readonly_fields = [
        "id", "reference", "created_at", "updated_at",
        "reserved_at", "completed_at", "cancelled_at",
        "escrow_funded_at", "escrow_released_at",
        "buyer_docs_confirmed_at", "compromis_generated_at",
    ]
    date_hierarchy = "created_at"
    list_per_page = 25
    actions = ["release_escrow", "cancel_transactions"]

    fieldsets = (
        ("Transaction", {"fields": (
            "reference", "parcelle", "buyer", "seller",
            "amount", "status", "payment_method", "notes",
        )}),
        ("Séquestre", {"fields": (
            "escrow_funded", "escrow_amount", "escrow_funded_at",
            "buyer_docs_confirmed", "buyer_docs_confirmed_at",
            "escrow_released", "escrow_released_at",
        )}),
        ("Compromis", {"fields": (
            "compromis_generated", "compromis_generated_at",
            "compromis_signed_buyer", "compromis_signed_seller",
        )}),
        ("Dates", {"fields": ("reserved_at", "completed_at", "cancelled_at")}),
    )

    @admin.display(description="Montant")
    def amount_formatted(self, obj):
        if obj.amount:
            # IMPORTANT: formater le nombre AVANT de le passer à format_html
            amount_str = "{:,.0f}".format(float(obj.amount))
            return format_html("<strong>{} FCFA</strong>", amount_str)
        return "—"

    @admin.display(description="Statut")
    def status_color_badge(self, obj):
        colors = {
            "pending": "#6b7280", "reserved": "#3b82f6",
            "escrow_funded": "#8b5cf6", "docs_validated": "#f59e0b",
            "paid": "#22c55e", "completed": "#16a34a",
            "cancelled": "#ef4444", "disputed": "#dc2626",
        }
        color = colors.get(obj.status, "#6b7280")
        label = obj.get_status_display()
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;'
            'border-radius:12px;font-size:11px;font-weight:600;">{}</span>',
            color, label,
        )

    @admin.display(description="Séquestre")
    def escrow_info(self, obj):
        if obj.escrow_released:
            return format_html('<span style="color:#16a34a;">Libéré</span>')
        if obj.escrow_funded:
            return format_html('<span style="color:#f59e0b;">Alimenté</span>')
        return "—"

    @admin.display(description="Progression")
    def progress_bar(self, obj):
        try:
            pct = obj.progress_percent
        except Exception:
            pct = 0
        if pct >= 80:
            color = "#22c55e"
        elif pct >= 40:
            color = "#f59e0b"
        else:
            color = "#6b7280"
        pct_str = str(pct)
        return format_html(
            '<div style="width:80px;background:#e5e7eb;border-radius:4px;overflow:hidden;">'
            '<div style="width:{pct}%;height:8px;background:{color};"></div></div>'
            '<small style="color:#6b7280;">{pct}%</small>',
            pct=pct_str, color=color,
        )

    @admin.action(description="Libérer le séquestre")
    def release_escrow(self, request, queryset):
        from django.utils import timezone
        from parcelles.models import Parcelle
        count = 0
        for tx in queryset.filter(escrow_funded=True, escrow_released=False):
            tx.escrow_released = True
            tx.escrow_released_at = timezone.now()
            tx.status = Transaction.Status.COMPLETED
            tx.completed_at = timezone.now()
            tx.parcelle.status = Parcelle.Status.VENDU
            tx.parcelle.save()
            tx.save()
            count += 1
        self.message_user(request, "{} séquestre(s) libéré(s).".format(count))

    @admin.action(description="Annuler les transactions")
    def cancel_transactions(self, request, queryset):
        from django.utils import timezone
        from parcelles.models import Parcelle
        count = 0
        for tx in queryset.exclude(status="completed"):
            tx.status = Transaction.Status.CANCELLED
            tx.cancelled_at = timezone.now()
            tx.parcelle.status = Parcelle.Status.DISPONIBLE
            tx.parcelle.save()
            tx.save()
            count += 1
        self.message_user(request, "{} transaction(s) annulée(s).".format(count))


@admin.register(BonDeVisite)
class BonDeVisiteAdmin(admin.ModelAdmin):
    list_display = [
        "reference", "parcelle", "visitor", "status_color_badge",
        "visit_date", "feedback_rating", "created_at",
    ]
    list_filter = ["status"]
    search_fields = ["reference", "parcelle__lot_number", "visitor__email"]
    date_hierarchy = "created_at"
    list_per_page = 25
    actions = ["approve_visits"]

    @admin.display(description="Statut")
    def status_color_badge(self, obj):
        colors = {
            "pending": "#f59e0b", "approved": "#22c55e",
            "used": "#3b82f6", "expired": "#6b7280", "cancelled": "#ef4444",
        }
        color = colors.get(obj.status, "#6b7280")
        label = obj.get_status_display()
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;'
            'border-radius:12px;font-size:11px;font-weight:600;">{}</span>',
            color, label,
        )

    @admin.action(description="Approuver les visites")
    def approve_visits(self, request, queryset):
        updated = queryset.filter(status="pending").update(status="approved")
        self.message_user(request, "{} visite(s) approuvée(s).".format(updated))


@admin.register(FinancialScore)
class FinancialScoreAdmin(admin.ModelAdmin):
    list_display = [
        "user", "overall_score_display", "grade_badge",
        "revenue_declared_fmt", "employment_type", "computed_at",
    ]
    list_filter = ["grade", "employment_type"]
    search_fields = ["user__email", "user__first_name", "employer_name"]
    readonly_fields = [
        "overall_score", "score_kyc", "score_revenue", "score_history",
        "score_mobile_money", "grade", "max_purchase_capacity",
        "monthly_capacity", "breakdown", "computed_at",
    ]

    @admin.display(description="Score")
    def overall_score_display(self, obj):
        score = obj.overall_score or 0
        score_str = "{:.0f}".format(score)
        color = "#22c55e" if score >= 60 else "#f59e0b" if score >= 40 else "#ef4444"
        return format_html(
            '<span style="font-weight:700;color:{}">{}/100</span>',
            color, score_str,
        )

    @admin.display(description="Grade")
    def grade_badge(self, obj):
        colors = {"A": "#22c55e", "B": "#3b82f6", "C": "#f59e0b", "D": "#ea580c", "E": "#ef4444"}
        color = colors.get(obj.grade, "#6b7280")
        return format_html(
            '<span style="background:{};color:white;padding:2px 10px;border-radius:12px;font-weight:700">{}</span>',
            color, obj.grade or "?",
        )

    @admin.display(description="Revenus")
    def revenue_declared_fmt(self, obj):
        if obj.revenue_declared:
            return "{:,.0f} FCFA".format(obj.revenue_declared)
        return "—"


@admin.register(SimulationResult)
class SimulationResultAdmin(admin.ModelAdmin):
    list_display = ["user", "price_fmt", "monthly_fmt", "duration_months", "is_feasible", "created_at"]
    list_filter = ["is_feasible", "duration_months"]
    search_fields = ["user__email"]

    @admin.display(description="Prix")
    def price_fmt(self, obj):
        return "{:,.0f} FCFA".format(obj.property_price)

    @admin.display(description="Mensualité")
    def monthly_fmt(self, obj):
        return "{:,.0f} FCFA".format(obj.monthly_payment)


@admin.register(TransactionEvent)
class TransactionEventAdmin(admin.ModelAdmin):
    list_display = ["transaction", "event_type", "old_status", "new_status", "actor", "created_at"]
    list_filter = ["event_type", "created_at"]
    search_fields = ["transaction__reference", "description"]
    readonly_fields = [
        "id", "transaction", "event_type", "old_status", "new_status",
        "actor", "description", "metadata", "created_at",
    ]

    def has_add_permission(self, request):
        return False


@admin.register(TransactionApproval)
class TransactionApprovalAdmin(admin.ModelAdmin):
    list_display = [
        "transaction", "operation_type", "status_badge",
        "requested_by", "reviewed_by", "created_at", "reviewed_at",
    ]
    list_filter = ["status", "operation_type"]
    search_fields = ["transaction__reference", "requested_by__email", "reviewed_by__email"]
    readonly_fields = [
        "id", "transaction", "operation_type", "status",
        "requested_by", "reviewed_by", "reason",
        "metadata", "created_at", "reviewed_at",
    ]

    @admin.display(description="Statut")
    def status_badge(self, obj):
        colors = {"pending": "#f59e0b", "approved": "#22c55e", "rejected": "#ef4444"}
        color = colors.get(obj.status, "#6b7280")
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;'
            'border-radius:12px;font-size:11px;font-weight:600;">{}</span>',
            color, obj.get_status_display(),
        )

    def has_add_permission(self, request):
        return False

# ── Import des admins Cotation / Boutique / Vérification ──
from .cotation_admin import *  # noqa: F401, F403

# ── Import des admins Litiges ──
from .dispute_admin import *  # noqa: F401, F403
