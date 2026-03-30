"""
Administration parcelles — EYE-FONCIER.
Corrigé : GIS widget + Jazzmin compat, readonly auto-fields, réactions, promotions.
"""
from django.contrib.gis import admin as gis_admin
from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Zone, Ilot, Parcelle, ParcelleMedia,
    ParcelleReaction, PromotionCampaign,
)


@admin.register(Zone)
class ZoneAdmin(gis_admin.GISModelAdmin):
    list_display = ["name", "code", "parcelle_count", "population", "created_at"]
    search_fields = ["name", "code"]
    list_per_page = 25

    @admin.display(description="Parcelles")
    def parcelle_count(self, obj):
        return obj.parcelles.count()


@admin.register(Ilot)
class IlotAdmin(gis_admin.GISModelAdmin):
    list_display = ["code", "name", "zone", "parcelle_count", "created_at"]
    list_filter = ["zone"]
    search_fields = ["code", "name"]
    list_per_page = 25

    @admin.display(description="Parcelles")
    def parcelle_count(self, obj):
        return obj.parcelles.count()


class ParcelleMediaInline(admin.TabularInline):
    model = ParcelleMedia
    extra = 0
    fields = ["media_type", "title", "file", "order"]


class ParcelleReactionInline(admin.TabularInline):
    model = ParcelleReaction
    extra = 0
    readonly_fields = ["user", "reaction_type", "created_at"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Parcelle)
class ParcelleAdmin(gis_admin.GISModelAdmin):
    """Admin Parcelle — compatible Jazzmin.

    IMPORTANT : changeform_format = 'collapsible' pour éviter
    le conflit widget GIS (OpenLayers) × onglets horizontaux Jazzmin.
    Le widget OpenLayers doit être visible au chargement pour s'initialiser.
    """
    inlines = [ParcelleMediaInline, ParcelleReactionInline]

    list_display = [
        "lot_number", "title", "owner", "status", "status_color_badge",
        "price_formatted", "surface_m2", "land_type",
        "is_validated", "trust_badge", "reactions_count",
        "views_count", "created_at",
    ]
    list_filter = ["status", "land_type", "is_validated", "trust_badge", "zone"]
    search_fields = ["lot_number", "title", "address", "owner__email"]
    date_hierarchy = "created_at"
    list_per_page = 25
    list_editable = ["status", "is_validated"]
    actions = ["validate_parcelles", "mark_disponible"]

    # ── Auto-fields doivent être readonly pour apparaître ──
    readonly_fields = [
        "centroid", "price_per_m2", "views_count", "trust_badge",
        "created_at", "updated_at",
    ]

    # ── Fieldsets : structure claire pour Jazzmin collapsible ──
    fieldsets = (
        ("Identification", {
            "fields": ("lot_number", "title", "description", "owner"),
        }),
        ("Localisation", {
            "description": "Géométrie de la parcelle — le widget carte apparaît ci-dessous.",
            "fields": ("zone", "ilot", "address", "geometry", "centroid"),
        }),
        ("Caractéristiques", {
            "fields": ("land_type", "surface_m2", "price", "price_per_m2"),
        }),
        ("Statut & Validation", {
            "fields": ("status", "is_validated", "validated_by", "validated_at"),
        }),
        ("Confiance", {
            "fields": ("title_holder_name", "trust_badge"),
        }),
        ("Statistiques", {
            "classes": ("collapse",),
            "fields": ("views_count", "created_at", "updated_at"),
        }),
    )

    @admin.display(description="Statut")
    def status_color_badge(self, obj):
        colors = {"disponible": "#22c55e", "reserve": "#f59e0b", "vendu": "#ef4444"}
        color = colors.get(obj.status, "#6b7280")
        label = obj.get_status_display()
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;'
            'border-radius:12px;font-size:11px;font-weight:600;">{}</span>',
            color, label,
        )

    @admin.display(description="Prix (FCFA)")
    def price_formatted(self, obj):
        if obj.price:
            price_str = "{:,.0f}".format(float(obj.price))
            return format_html("<strong>{}</strong>", price_str)
        return "—"

    @admin.display(description="Réactions")
    def reactions_count(self, obj):
        count = obj.reactions.count()
        if count == 0:
            return "—"
        return format_html(
            '<span class="badge bg-info">{}</span>', count,
        )

    @admin.action(description="Valider les parcelles sélectionnées")
    def validate_parcelles(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(
            is_validated=True, validated_by=request.user, validated_at=timezone.now(),
        )
        self.message_user(request, "{} parcelle(s) validée(s).".format(updated))

    @admin.action(description="Remettre en disponible")
    def mark_disponible(self, request, queryset):
        updated = queryset.update(status="disponible")
        self.message_user(request, "{} parcelle(s) remise(s) en disponible.".format(updated))


@admin.register(ParcelleMedia)
class ParcelleMediaAdmin(admin.ModelAdmin):
    list_display = ["parcelle", "media_type", "title", "order", "created_at"]
    list_filter = ["media_type"]
    list_per_page = 25


# ═══════════════════════════════════════════════════════════
# RÉACTIONS
# ═══════════════════════════════════════════════════════════

@admin.register(ParcelleReaction)
class ParcelleReactionAdmin(admin.ModelAdmin):
    list_display = ["user", "parcelle", "reaction_badge", "created_at"]
    list_filter = ["reaction_type"]
    search_fields = ["user__email", "parcelle__lot_number"]
    readonly_fields = ["user", "parcelle", "reaction_type", "created_at"]
    list_per_page = 50

    @admin.display(description="Réaction")
    def reaction_badge(self, obj):
        icons = {
            "like": (
                '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="#ef4444" stroke="#ef4444" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-3px"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/></svg>',
                "#ef4444",
            ),
            "favorite": (
                '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="#f59e0b" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-3px"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>',
                "#f59e0b",
            ),
            "interested": (
                '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-3px"><path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/></svg>',
                "#3b82f6",
            ),
            "dislike": (
                '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#6b7280" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-3px"><path d="M17 14V2"/><path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88Z"/></svg>',
                "#6b7280",
            ),
        }
        svg_icon, color = icons.get(obj.reaction_type, (
            '<span style="font-weight:700">?</span>', "#6b7280"
        ))
        return format_html(
            '<span style="color:{}">{} {}</span>',
            color, svg_icon, obj.get_reaction_type_display(),
        )

    def has_add_permission(self, request):
        return False


# ═══════════════════════════════════════════════════════════
# PROMOTIONS
# ═══════════════════════════════════════════════════════════

@admin.register(PromotionCampaign)
class PromotionCampaignAdmin(admin.ModelAdmin):
    list_display = [
        "parcelle", "seller", "campaign_type", "status_badge",
        "duration_weeks", "amount_display", "impressions",
        "clicks", "ctr_display", "start_date", "end_date",
    ]
    list_filter = ["campaign_type", "status"]
    search_fields = ["parcelle__lot_number", "seller__email"]
    filter_horizontal = ["target_zones"]
    readonly_fields = ["impressions", "clicks", "created_at", "updated_at"]
    list_per_page = 25
    actions = ["activate_campaigns", "pause_campaigns"]

    fieldsets = (
        ("Campagne", {"fields": (
            "parcelle", "seller", "campaign_type", "status",
            "highlight_text",
        )}),
        ("Durée", {"fields": ("start_date", "end_date", "duration_weeks")}),
        ("Paiement", {"fields": (
            "amount_paid", "payment_reference", "payment_method",
        )}),
        ("Ciblage Smart Matching", {
            "classes": ("collapse",),
            "fields": (
                "target_zones", "target_land_types",
                "target_budget_min", "target_budget_max",
            ),
        }),
        ("Statistiques", {
            "classes": ("collapse",),
            "fields": ("impressions", "clicks", "created_at", "updated_at"),
        }),
    )

    @admin.display(description="Statut")
    def status_badge(self, obj):
        colors = {
            "draft": "#6b7280", "pending_payment": "#f59e0b",
            "active": "#22c55e", "paused": "#3b82f6",
            "completed": "#8b5cf6", "cancelled": "#ef4444",
        }
        color = colors.get(obj.status, "#6b7280")
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;'
            'border-radius:12px;font-size:11px;">{}</span>',
            color, obj.get_status_display(),
        )

    @admin.display(description="Montant")
    def amount_display(self, obj):
        if obj.amount_paid:
            return "{:,.0f} FCFA".format(float(obj.amount_paid))
        return "{:,.0f} FCFA".format(obj.total_price)

    @admin.display(description="CTR")
    def ctr_display(self, obj):
        return "{}%".format(obj.ctr)

    @admin.action(description="Activer les campagnes sélectionnées")
    def activate_campaigns(self, request, queryset):
        from django.utils import timezone
        updated = queryset.filter(status__in=["draft", "pending_payment", "paused"]).update(
            status="active", start_date=timezone.now(),
        )
        self.message_user(request, "{} campagne(s) activée(s).".format(updated))

    @admin.action(description="Mettre en pause les campagnes")
    def pause_campaigns(self, request, queryset):
        updated = queryset.filter(status="active").update(status="paused")
        self.message_user(request, "{} campagne(s) en pause.".format(updated))
