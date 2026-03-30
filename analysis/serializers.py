"""Serializers Analysis — EYE-FONCIER (Smart Matching API)."""
from rest_framework import serializers
from .models import BuyerProfile, MatchScore, MatchNotification


class MatchScoreSerializer(serializers.ModelSerializer):
    """Score de compatibilité avec détails parcelle."""

    parcelle_lot = serializers.CharField(source="parcelle.lot_number", read_only=True)
    parcelle_title = serializers.CharField(source="parcelle.title", read_only=True)
    parcelle_price = serializers.DecimalField(
        source="parcelle.price", max_digits=15, decimal_places=0, read_only=True
    )
    parcelle_surface = serializers.DecimalField(
        source="parcelle.surface_m2", max_digits=12, decimal_places=2, read_only=True
    )
    parcelle_zone = serializers.CharField(
        source="parcelle.zone.name", read_only=True, default=""
    )
    parcelle_status = serializers.CharField(
        source="parcelle.get_status_display", read_only=True
    )
    parcelle_id = serializers.UUIDField(source="parcelle.pk", read_only=True)

    class Meta:
        model = MatchScore
        fields = [
            "id", "parcelle_id", "parcelle_lot", "parcelle_title",
            "parcelle_price", "parcelle_surface", "parcelle_zone", "parcelle_status",
            "score_price", "score_location", "score_technical", "score_seller",
            "final_score", "is_golden_opportunity", "breakdown", "computed_at",
        ]
        read_only_fields = fields


class BuyerProfileSerializer(serializers.ModelSerializer):
    """Profil acheteur pour le matching."""

    preferred_zones_names = serializers.SerializerMethodField()

    class Meta:
        model = BuyerProfile
        fields = [
            "budget_min", "budget_max", "surface_min", "surface_max",
            "preferred_land_types", "preferred_zones", "preferred_zones_names",
            "lifestyle", "risk_tolerance", "project_type",
            "max_travel_minutes",
            "weight_price", "weight_location", "weight_technical", "weight_seller",
            "notify_on_match", "match_threshold", "is_active",
            "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_preferred_zones_names(self, obj):
        return list(obj.preferred_zones.values_list("name", flat=True))


class MatchNotificationSerializer(serializers.ModelSerializer):
    parcelle_lot = serializers.CharField(
        source="match_score.parcelle.lot_number", read_only=True
    )
    final_score = serializers.FloatField(
        source="match_score.final_score", read_only=True
    )

    class Meta:
        model = MatchNotification
        fields = [
            "id", "title", "message", "parcelle_lot",
            "final_score", "is_read", "sent_at",
        ]
