"""
Admin — Module Analyse SIG, Matching & Rapport
Audit complet : format_html sécurisé, aucun formatage numérique dans format_html.
"""
from django.contrib import admin
from django.contrib.gis import admin as gis_admin
from django.utils.html import format_html

from .models import (
    TerrainAnalysis, SpatialConstraint, ProximityAnalysis,
    RiskAssessment, BuyerProfile, MatchScore, MatchNotification,
    AnalysisReport, GISReferenceLayer,
)


@admin.register(TerrainAnalysis)
class TerrainAnalysisAdmin(admin.ModelAdmin):
    list_display = [
        "parcelle", "slope_category_badge", "technical_score_bar",
        "elevation_mean", "drainage_quality", "analyzed_at",
    ]
    list_filter = ["slope_category", "drainage_quality", "slope_is_constructible"]
    search_fields = ["parcelle__lot_number", "parcelle__title"]
    readonly_fields = [
        "elevation_min", "elevation_max", "elevation_mean", "elevation_range",
        "slope_mean", "slope_max", "slope_category", "slope_is_constructible",
        "aspect_dominant", "solar_potential", "water_accumulation_risk",
        "drainage_quality", "technical_score", "dem_source", "raw_data", "analyzed_at",
    ]
    fieldsets = (
        ("Parcelle", {"fields": ("parcelle",)}),
        ("Élévation", {"fields": ("elevation_min", "elevation_max", "elevation_mean", "elevation_range")}),
        ("Pente", {"fields": ("slope_mean", "slope_max", "slope_category", "slope_is_constructible")}),
        ("Exposition & Hydrologie", {"fields": ("aspect_dominant", "solar_potential", "water_accumulation_risk", "drainage_quality")}),
        ("Score", {"fields": ("technical_score", "dem_source", "raw_data")}),
    )

    def slope_category_badge(self, obj):
        colors = {"flat": "#22c55e", "gentle": "#86efac", "moderate": "#f59e0b", "steep": "#ef4444", "very_steep": "#dc2626"}
        color = colors.get(obj.slope_category, "#6b7280")
        label = obj.get_slope_category_display() if obj.slope_category else "—"
        return format_html('<span style="background:{};color:white;padding:3px 8px;border-radius:12px;font-size:11px;">{}</span>', color, label)
    slope_category_badge.short_description = "Pente"

    def technical_score_bar(self, obj):
        score = obj.technical_score or 0
        color = "#22c55e" if score >= 70 else "#f59e0b" if score >= 45 else "#ef4444"
        s = "{:.0f}".format(score)
        return format_html(
            '<div style="width:100px;background:#e2e8f0;border-radius:8px;">'
            '<div style="width:{}%;background:{};height:18px;border-radius:8px;text-align:center;color:white;font-size:11px;line-height:18px;">{}</div></div>',
            s, color, s)
    technical_score_bar.short_description = "Score technique"


@admin.register(SpatialConstraint)
class SpatialConstraintAdmin(gis_admin.GISModelAdmin):
    list_display = ["parcelle", "constraint_type", "severity_badge", "affected_area_pct", "source_layer", "detected_at"]
    list_filter = ["constraint_type", "severity"]
    search_fields = ["parcelle__lot_number", "source_layer"]
    readonly_fields = ["intersection_geometry", "detected_at"]

    def severity_badge(self, obj):
        colors = {"info": "#3b82f6", "warning": "#f59e0b", "critical": "#ef4444"}
        color = colors.get(obj.severity, "#6b7280")
        return format_html('<span style="background:{};color:white;padding:3px 8px;border-radius:12px;font-size:11px;">{}</span>', color, obj.get_severity_display())
    severity_badge.short_description = "Gravité"


@admin.register(ProximityAnalysis)
class ProximityAnalysisAdmin(admin.ModelAdmin):
    list_display = ["parcelle", "poi_type", "distance_display", "score_bar", "poi_name"]
    list_filter = ["poi_type"]
    search_fields = ["parcelle__lot_number", "poi_name"]

    def distance_display(self, obj):
        if obj.distance_m is not None:
            return format_html("{} m", "{:,.0f}".format(obj.distance_m))
        return "—"
    distance_display.short_description = "Distance"

    def score_bar(self, obj):
        score = obj.score or 0
        color = "#22c55e" if score >= 70 else "#f59e0b" if score >= 40 else "#ef4444"
        s = "{:.0f}".format(score)
        return format_html(
            '<div style="width:80px;background:#e2e8f0;border-radius:8px;">'
            '<div style="width:{}%;background:{};height:16px;border-radius:8px;text-align:center;color:white;font-size:10px;line-height:16px;">{}</div></div>',
            s, color, s)
    score_bar.short_description = "Score"


@admin.register(RiskAssessment)
class RiskAssessmentAdmin(admin.ModelAdmin):
    list_display = ["parcelle", "overall_score_display", "overall_risk_badge", "recommendation_badge", "assessed_at"]
    list_filter = ["overall_risk", "recommendation"]
    search_fields = ["parcelle__lot_number"]
    readonly_fields = [
        "flood_risk", "erosion_risk", "slope_risk", "legal_risk",
        "score_accessibility", "score_topography", "score_legal",
        "score_environment", "score_price", "overall_score",
        "overall_risk", "ai_conclusion", "recommendation", "assessed_at",
    ]

    def overall_score_display(self, obj):
        score = obj.overall_score or 0
        color = "#22c55e" if score >= 70 else "#f59e0b" if score >= 45 else "#ef4444"
        s = "{:.0f}".format(score)
        return format_html('<span style="background:{};color:white;padding:4px 10px;border-radius:12px;font-weight:bold;">{}/100</span>', color, s)
    overall_score_display.short_description = "Score"

    def overall_risk_badge(self, obj):
        colors = {"low": "#22c55e", "medium": "#f59e0b", "high": "#ef4444", "critical": "#dc2626"}
        color = colors.get(obj.overall_risk, "#6b7280")
        return format_html('<span style="background:{};color:white;padding:3px 8px;border-radius:12px;font-size:11px;">{}</span>', color, obj.get_overall_risk_display())
    overall_risk_badge.short_description = "Risque"

    def recommendation_badge(self, obj):
        colors = {"ideal": "#16a34a", "good": "#22c55e", "caution": "#f59e0b", "risky": "#ef4444", "no_go": "#dc2626"}
        color = colors.get(obj.recommendation, "#6b7280")
        label = obj.get_recommendation_display() if obj.recommendation else "—"
        return format_html('<span style="color:{};font-weight:bold;">{}</span>', color, label)
    recommendation_badge.short_description = "Recommandation"


@admin.register(BuyerProfile)
class BuyerProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "budget_display", "surface_range", "project_type", "lifestyle", "risk_tolerance", "is_active"]
    list_filter = ["project_type", "lifestyle", "risk_tolerance", "is_active"]
    search_fields = ["user__email", "user__first_name", "user__last_name"]
    filter_horizontal = ["preferred_zones"]

    def budget_display(self, obj):
        parts = []
        if obj.budget_min:
            parts.append("{:,.0f}".format(float(obj.budget_min)))
        if obj.budget_max:
            parts.append("{:,.0f}".format(float(obj.budget_max)))
        return " — ".join(parts) + " FCFA" if parts else "—"
    budget_display.short_description = "Budget"

    def surface_range(self, obj):
        parts = []
        if obj.surface_min:
            parts.append("{:,.0f}".format(float(obj.surface_min)))
        if obj.surface_max:
            parts.append("{:,.0f}".format(float(obj.surface_max)))
        return " — ".join(parts) + " m²" if parts else "—"
    surface_range.short_description = "Surface"


@admin.register(MatchScore)
class MatchScoreAdmin(admin.ModelAdmin):
    list_display = ["parcelle", "buyer_display", "final_score_bar", "score_price", "score_location", "score_technical", "score_seller", "is_notified", "computed_at"]
    list_filter = ["is_notified"]
    search_fields = ["buyer_profile__user__email", "parcelle__lot_number"]
    readonly_fields = ["score_price", "score_location", "score_technical", "score_seller", "final_score", "breakdown", "computed_at"]
    ordering = ["-final_score"]

    def buyer_display(self, obj):
        return obj.buyer_profile.user.get_full_name()
    buyer_display.short_description = "Acheteur"

    def final_score_bar(self, obj):
        score = obj.final_score or 0
        color = "#16a34a" if score >= 85 else "#22c55e" if score >= 60 else "#f59e0b" if score >= 40 else "#ef4444"
        s = "{:.0f}".format(min(score, 100))
        label = "{:.0f}%".format(score)
        return format_html(
            '<div style="width:120px;background:#e2e8f0;border-radius:8px;">'
            '<div style="width:{}%;background:{};height:20px;border-radius:8px;text-align:center;color:white;font-size:11px;line-height:20px;font-weight:bold;">{}</div></div>',
            s, color, label)
    final_score_bar.short_description = "Compatibilité"


@admin.register(MatchNotification)
class MatchNotificationAdmin(admin.ModelAdmin):
    list_display = ["title", "channel", "is_read", "sent_at"]
    list_filter = ["channel", "is_read"]
    readonly_fields = ["match_score", "sent_at"]


@admin.register(AnalysisReport)
class AnalysisReportAdmin(admin.ModelAdmin):
    list_display = ["parcelle", "status_badge", "requested_by", "qr_verification_code", "generated_at"]
    list_filter = ["status"]
    search_fields = ["parcelle__lot_number", "qr_verification_code"]
    readonly_fields = ["pdf_file", "qr_verification_code", "snapshot_data", "generated_at"]

    def status_badge(self, obj):
        colors = {"pending": "#f59e0b", "ready": "#22c55e", "error": "#ef4444"}
        color = colors.get(obj.status, "#6b7280")
        return format_html('<span style="background:{};color:white;padding:3px 8px;border-radius:12px;font-size:11px;">{}</span>', color, obj.get_status_display())
    status_badge.short_description = "Statut"


@admin.register(GISReferenceLayer)
class GISReferenceLayerAdmin(gis_admin.GISModelAdmin):
    list_display = ["name", "layer_type", "is_active", "buffer_distance_m", "uploaded_at"]
    list_filter = ["layer_type", "is_active"]
    search_fields = ["name", "description"]
