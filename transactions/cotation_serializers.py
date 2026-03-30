"""
Sérialiseurs API — Cotation, Boutique, Vérification — EYE-FONCIER
"""
from rest_framework import serializers

from .cotation_models import Cotation, Boutique, VerificationRequest


class CotationSerializer(serializers.ModelSerializer):
    payer_name = serializers.SerializerMethodField()
    parcelle_lot = serializers.SerializerMethodField()
    is_valid = serializers.BooleanField(read_only=True)
    remaining_balance = serializers.DecimalField(
        max_digits=15, decimal_places=0, read_only=True,
    )
    status_display = serializers.CharField(
        source="get_status_display", read_only=True,
    )
    cotation_type_display = serializers.CharField(
        source="get_cotation_type_display", read_only=True,
    )

    class Meta:
        model = Cotation
        fields = [
            "id", "reference", "payer", "payer_name",
            "cotation_type", "cotation_type_display",
            "parcelle", "parcelle_lot",
            "amount", "property_price", "remaining_balance",
            "status", "status_display", "is_valid",
            "payment_reference", "payment_method",
            "paid_at", "validated_at", "expires_at",
            "created_at",
        ]
        read_only_fields = [
            "id", "reference", "amount", "property_price",
            "status", "payment_reference",
            "paid_at", "validated_at", "expires_at",
            "created_at",
        ]

    def get_payer_name(self, obj):
        return obj.payer.get_full_name() or obj.payer.email

    def get_parcelle_lot(self, obj):
        return obj.parcelle.lot_number if obj.parcelle else None


class CotationCreateSerializer(serializers.Serializer):
    """Sérialiseur pour initier une cotation d'achat."""
    parcelle_id = serializers.UUIDField()
    payment_method = serializers.ChoiceField(
        choices=["mobile_money", "wave", "carte", "virement"],
        default="mobile_money",
    )


class BoutiqueCotationCreateSerializer(serializers.Serializer):
    """Sérialiseur pour initier une cotation boutique."""
    boutique_name = serializers.CharField(max_length=200)
    payment_method = serializers.ChoiceField(
        choices=["mobile_money", "wave", "carte", "virement"],
        default="mobile_money",
    )


class BoutiqueSerializer(serializers.ModelSerializer):
    owner_name = serializers.SerializerMethodField()
    is_active = serializers.BooleanField(read_only=True)
    status_display = serializers.CharField(
        source="get_status_display", read_only=True,
    )

    class Meta:
        model = Boutique
        fields = [
            "id", "owner", "owner_name",
            "name", "slug", "description",
            "phone", "email", "address", "city",
            "status", "status_display", "is_active",
            "total_parcelles", "total_ventes", "rating",
            "created_at",
        ]
        read_only_fields = [
            "id", "owner", "slug", "status",
            "total_parcelles", "total_ventes", "rating",
            "created_at",
        ]

    def get_owner_name(self, obj):
        return obj.owner.get_full_name() or obj.owner.email


class VerificationRequestSerializer(serializers.ModelSerializer):
    buyer_name = serializers.SerializerMethodField()
    seller_name = serializers.SerializerMethodField()
    verifier_name = serializers.SerializerMethodField()
    parcelle_lot = serializers.SerializerMethodField()
    progress_percent = serializers.IntegerField(read_only=True)
    status_display = serializers.CharField(
        source="get_status_display", read_only=True,
    )

    class Meta:
        model = VerificationRequest
        fields = [
            "id", "reference",
            "buyer", "buyer_name",
            "seller", "seller_name",
            "verifier", "verifier_name",
            "parcelle", "parcelle_lot",
            "status", "status_display", "progress_percent",
            "seller_contacted_at", "docs_received_at",
            "docs_verified_at", "client_contacted_at",
            "rdv_date", "completed_at",
            "docs_are_authentic", "analysis_report",
            "verification_notes",
            "created_at",
        ]
        read_only_fields = [
            "id", "reference", "buyer", "seller", "parcelle",
            "seller_contacted_at", "docs_received_at",
            "docs_verified_at", "client_contacted_at",
            "completed_at", "created_at",
        ]

    def get_buyer_name(self, obj):
        return obj.buyer.get_full_name() or obj.buyer.email

    def get_seller_name(self, obj):
        return obj.seller.get_full_name() or obj.seller.email

    def get_verifier_name(self, obj):
        if obj.verifier:
            return obj.verifier.get_full_name() or obj.verifier.email
        return None

    def get_parcelle_lot(self, obj):
        return obj.parcelle.lot_number


class VerificationAdvanceSerializer(serializers.Serializer):
    """Sérialiseur pour avancer le workflow de vérification."""
    new_status = serializers.ChoiceField(
        choices=[s[0] for s in VerificationRequest.Status.choices],
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    rdv_date = serializers.DateTimeField(required=False, allow_null=True)


class CotationCheckSerializer(serializers.Serializer):
    """Réponse pour vérifier si un utilisateur a une cotation active."""
    has_cotation = serializers.BooleanField()
    cotation = CotationSerializer(allow_null=True)
    can_visit = serializers.BooleanField()
    can_view_docs = serializers.BooleanField()
    can_reserve = serializers.BooleanField()
