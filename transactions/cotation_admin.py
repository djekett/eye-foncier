"""
Admin — Cotation, Boutique, Vérification — EYE-FONCIER
"""
from django.contrib import admin
from django.utils.html import format_html

from .cotation_models import Cotation, Boutique, VerificationRequest, Review


@admin.register(Cotation)
class CotationAdmin(admin.ModelAdmin):
    list_display = [
        "reference", "payer_name", "cotation_type",
        "amount_display", "status_badge", "parcelle_lot",
        "paid_at", "expires_at",
    ]
    list_filter = ["status", "cotation_type", "payment_method"]
    search_fields = [
        "reference", "payer__email", "payer__first_name",
        "payer__last_name", "parcelle__lot_number",
    ]
    readonly_fields = [
        "reference", "created_at", "updated_at",
        "paid_at", "validated_at",
    ]
    raw_id_fields = ["payer", "parcelle", "transaction", "validated_by"]
    list_per_page = 25

    fieldsets = (
        ("Cotation", {
            "fields": (
                "reference", "cotation_type", "payer", "parcelle",
                "amount", "property_price", "status",
            ),
        }),
        ("Paiement", {
            "fields": (
                "payment_reference", "payment_method",
                "paid_at", "validated_at", "expires_at",
            ),
        }),
        ("Liaison", {
            "fields": ("transaction", "validated_by", "notes"),
        }),
        ("Métadonnées", {
            "classes": ("collapse",),
            "fields": ("created_at", "updated_at"),
        }),
    )

    def payer_name(self, obj):
        return obj.payer.get_full_name() or obj.payer.email
    payer_name.short_description = "Payeur"

    def parcelle_lot(self, obj):
        return obj.parcelle.lot_number if obj.parcelle else "—"
    parcelle_lot.short_description = "Parcelle"

    def amount_display(self, obj):
        return f"{obj.amount:,.0f} FCFA"
    amount_display.short_description = "Montant"

    def status_badge(self, obj):
        colors = {
            "pending": "#f59e0b",
            "paid": "#3b82f6",
            "validated": "#22c55e",
            "expired": "#6b7280",
            "refunded": "#ef4444",
            "cancelled": "#ef4444",
        }
        color = colors.get(obj.status, "#6b7280")
        return format_html(
            '<span style="color:{}; font-weight:600;">●</span> {}',
            color, obj.get_status_display(),
        )
    status_badge.short_description = "Statut"


@admin.register(Boutique)
class BoutiqueAdmin(admin.ModelAdmin):
    list_display = [
        "name", "owner_name", "status_badge",
        "total_parcelles", "total_ventes", "rating",
        "created_at",
    ]
    list_filter = ["status"]
    search_fields = ["name", "owner__email", "owner__first_name"]
    readonly_fields = ["created_at", "updated_at"]
    raw_id_fields = ["owner", "cotation"]

    def owner_name(self, obj):
        return obj.owner.get_full_name() or obj.owner.email
    owner_name.short_description = "Propriétaire"

    def status_badge(self, obj):
        colors = {
            "pending": "#f59e0b",
            "active": "#22c55e",
            "suspended": "#ef4444",
            "closed": "#6b7280",
        }
        color = colors.get(obj.status, "#6b7280")
        return format_html(
            '<span style="color:{}; font-weight:600;">●</span> {}',
            color, obj.get_status_display(),
        )
    status_badge.short_description = "Statut"


@admin.register(VerificationRequest)
class VerificationRequestAdmin(admin.ModelAdmin):
    list_display = [
        "reference", "parcelle_lot", "buyer_name", "seller_name",
        "verifier_name", "status_badge", "progress_bar",
        "created_at",
    ]
    list_filter = ["status"]
    search_fields = [
        "reference", "buyer__email", "seller__email",
        "parcelle__lot_number",
    ]
    readonly_fields = [
        "reference", "created_at", "updated_at",
        "seller_contacted_at", "docs_received_at",
        "docs_verified_at", "client_contacted_at",
        "completed_at",
    ]
    raw_id_fields = ["cotation", "buyer", "seller", "verifier", "parcelle"]

    fieldsets = (
        ("Demande", {
            "fields": (
                "reference", "cotation", "parcelle",
                "buyer", "seller", "verifier", "status",
            ),
        }),
        ("Workflow", {
            "fields": (
                "seller_contacted_at", "seller_contact_notes",
                "docs_received_at", "docs_verified_at",
                "docs_are_authentic", "analysis_report",
                "client_contacted_at", "client_contact_notes",
                "rdv_date", "completed_at",
            ),
        }),
        ("Notes", {
            "fields": ("verification_notes",),
        }),
    )

    def parcelle_lot(self, obj):
        return obj.parcelle.lot_number
    parcelle_lot.short_description = "Parcelle"

    def buyer_name(self, obj):
        return obj.buyer.get_full_name() or obj.buyer.email
    buyer_name.short_description = "Acheteur"

    def seller_name(self, obj):
        return obj.seller.get_full_name() or obj.seller.email
    seller_name.short_description = "Vendeur"

    def verifier_name(self, obj):
        if obj.verifier:
            return obj.verifier.get_full_name() or obj.verifier.email
        return "— non assigné —"
    verifier_name.short_description = "Vérificateur"

    def status_badge(self, obj):
        colors = {
            "created": "#f59e0b",
            "assigned": "#3b82f6",
            "seller_contacted": "#8b5cf6",
            "docs_received": "#06b6d4",
            "docs_verified": "#10b981",
            "docs_watermarked": "#22c55e",
            "client_contacted": "#14b8a6",
            "rdv_scheduled": "#0ea5e9",
            "completed": "#22c55e",
            "cancelled": "#ef4444",
        }
        color = colors.get(obj.status, "#6b7280")
        return format_html(
            '<span style="color:{}; font-weight:600;">●</span> {}',
            color, obj.get_status_display(),
        )
    status_badge.short_description = "Statut"

    def progress_bar(self, obj):
        pct = obj.progress_percent
        color = "#22c55e" if pct >= 80 else "#f59e0b" if pct >= 40 else "#ef4444"
        return format_html(
            '<div style="width:80px;background:#e5e7eb;border-radius:4px;overflow:hidden;">'
            '<div style="width:{}%;height:8px;background:{};border-radius:4px;"></div>'
            '</div> <small>{}%</small>',
            pct, color, pct,
        )
    progress_bar.short_description = "Progression"


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = [
        "author_name", "target_type", "target_display",
        "score_stars", "is_verified", "is_visible", "created_at",
    ]
    list_filter = ["target_type", "is_verified", "is_visible", "score"]
    search_fields = [
        "author__email", "author__first_name",
        "boutique__name", "comment",
    ]
    readonly_fields = ["id", "created_at", "updated_at"]
    raw_id_fields = ["author", "boutique", "target_user", "transaction"]
    list_per_page = 30
    actions = ["mark_visible", "mark_hidden"]

    def author_name(self, obj):
        return obj.author.get_full_name() or obj.author.email
    author_name.short_description = "Auteur"

    def target_display(self, obj):
        if obj.target_type == "boutique" and obj.boutique:
            return obj.boutique.name
        if obj.target_type == "vendeur" and obj.target_user:
            return obj.target_user.get_full_name() or obj.target_user.email
        if obj.target_type == "prestation" and obj.transaction:
            return obj.transaction.reference
        return "—"
    target_display.short_description = "Cible"

    def score_stars(self, obj):
        filled = "★" * obj.score
        empty = "☆" * (5 - obj.score)
        return format_html(
            '<span style="color:#f59e0b;font-size:14px;">{}</span>'
            '<span style="color:#d1d5db;font-size:14px;">{}</span>',
            filled, empty,
        )
    score_stars.short_description = "Note"

    @admin.action(description="Rendre visible")
    def mark_visible(self, request, queryset):
        updated = queryset.update(is_visible=True)
        self.message_user(request, "{} avis rendu(s) visible(s).".format(updated))

    @admin.action(description="Masquer")
    def mark_hidden(self, request, queryset):
        updated = queryset.update(is_visible=False)
        self.message_user(request, "{} avis masqué(s).".format(updated))
