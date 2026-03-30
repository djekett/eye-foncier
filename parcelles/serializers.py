"""
Sérialiseurs GIS — EYE-FONCIER
RBAC : Les données retournées dépendent du statut d'authentification.
"""
from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from .models import Parcelle, ParcelleMedia, Zone, Ilot
from accounts.serializers import UserPublicSerializer


class ZoneSerializer(GeoFeatureModelSerializer):
    class Meta:
        model = Zone
        geo_field = "geometry"
        fields = ["id", "name", "code", "description"]


class IlotSerializer(GeoFeatureModelSerializer):
    class Meta:
        model = Ilot
        geo_field = "geometry"
        fields = ["id", "name", "code", "zone"]


class ParcelleMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParcelleMedia
        fields = ["id", "media_type", "title", "file", "thumbnail", "order"]


class ParcelleListSerializer(GeoFeatureModelSerializer):
    """
    Sérialiseur carte — GeoJSON FeatureCollection.

    RBAC :
      • Public      → titre, lot, surface, type, zone, statut, géométrie
      • Connecté    → + prix, propriétaire, téléphone, description, documents
    Tous les champs dérivés sont des SerializerMethodField (jamais de crash
    si une @property retourne None).
    """
    owner_name      = serializers.SerializerMethodField()
    owner_phone     = serializers.SerializerMethodField()
    status_display  = serializers.SerializerMethodField()
    land_type_display = serializers.SerializerMethodField()
    status_color    = serializers.SerializerMethodField()
    main_image      = serializers.SerializerMethodField()
    zone_name       = serializers.SerializerMethodField()
    # RBAC — ces champs retournent None pour les visiteurs
    price_display   = serializers.SerializerMethodField()
    description_display = serializers.SerializerMethodField()
    created_at_display  = serializers.SerializerMethodField()

    class Meta:
        model = Parcelle
        geo_field = "geometry"
        fields = [
            "id", "lot_number", "title", "status", "status_display",
            "price", "surface_m2", "price_per_m2", "land_type", "land_type_display",
            "owner_name", "owner_phone", "is_validated", "trust_badge",
            "status_color", "main_image", "address", "views_count",
            "zone_name", "description", "description_display",
            "price_display", "created_at_display",
        ]

    def _is_authenticated(self):
        request = self.context.get("request")
        return request and hasattr(request, "user") and request.user.is_authenticated

    # ──── Champs toujours visibles ────────────────
    def get_status_display(self, obj):
        try: return obj.get_status_display()
        except Exception: return obj.status or ""

    def get_land_type_display(self, obj):
        try: return obj.get_land_type_display()
        except Exception: return obj.land_type or ""

    def get_status_color(self, obj):
        try: return obj.status_color
        except Exception: return "#6b7280"

    def get_main_image(self, obj):
        try:
            img = obj.main_image
            return img if img else ""
        except Exception: return ""

    def get_zone_name(self, obj):
        try: return obj.zone.name if obj.zone else ""
        except Exception: return ""

    # ──── Champs conditionnels (RBAC) ─────────────
    def get_owner_name(self, obj):
        if not self._is_authenticated():
            return None
        try:
            full = obj.owner.get_full_name()
            return full if full else obj.owner.username
        except Exception: return ""

    def get_owner_phone(self, obj):
        if not self._is_authenticated():
            return None
        try: return obj.owner.phone or ""
        except Exception: return ""

    def get_price_display(self, obj):
        """Prix formaté — visible par tous, mais les détails (prix/m²) réservés aux connectés."""
        try: return str(obj.price) if obj.price else "0"
        except Exception: return "0"

    def get_description_display(self, obj):
        if not self._is_authenticated():
            return None
        try: return obj.description or ""
        except Exception: return ""

    def get_created_at_display(self, obj):
        if not self._is_authenticated():
            return None
        try: return obj.created_at.isoformat() if obj.created_at else ""
        except Exception: return ""


class ParcelleDetailSerializer(GeoFeatureModelSerializer):
    """Sérialiseur complet pour le détail (page parcelle)."""
    owner = UserPublicSerializer(read_only=True)
    medias = ParcelleMediaSerializer(many=True, read_only=True)
    zone_name = serializers.SerializerMethodField()
    ilot_name = serializers.SerializerMethodField()

    class Meta:
        model = Parcelle
        geo_field = "geometry"
        fields = [
            "id", "lot_number", "title", "description", "status",
            "price", "surface_m2", "price_per_m2", "land_type",
            "address", "owner", "zone", "zone_name", "ilot", "ilot_name",
            "is_validated", "trust_badge", "title_holder_name",
            "views_count", "medias", "created_at", "updated_at",
        ]

    def get_zone_name(self, obj):
        try: return obj.zone.name if obj.zone else ""
        except Exception: return ""

    def get_ilot_name(self, obj):
        try: return obj.ilot.name if obj.ilot else ""
        except Exception: return ""
