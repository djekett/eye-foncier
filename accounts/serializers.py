"""Sérialiseurs API pour les comptes."""
from rest_framework import serializers
from .models import User, Profile, Partner, PartnerReferral, AmbassadorProfile, ReferralProgram


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ["avatar", "bio", "city", "country", "trust_score", "total_sales", "kyc_status"]
        read_only_fields = ["trust_score", "total_sales", "kyc_status"]


class UserPublicSerializer(serializers.ModelSerializer):
    """Infos publiques d'un utilisateur (vendeur)."""
    profile = ProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "role", "is_verified", "profile"]


class UserPrivateSerializer(serializers.ModelSerializer):
    """Infos complètes (acheteur qualifié)."""
    profile = ProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name",
            "phone", "role", "is_verified", "created_at", "profile",
        ]
        read_only_fields = ["id", "email", "role", "is_verified", "created_at"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=10)

    class Meta:
        model = User
        fields = ["email", "username", "first_name", "last_name", "phone", "role", "password"]

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


# ─── Partenaires ──────────────────────────────────────────


class PartnerSerializer(serializers.ModelSerializer):
    partner_type_display = serializers.CharField(source="get_partner_type_display", read_only=True)

    class Meta:
        model = Partner
        fields = [
            "id", "name", "partner_type", "partner_type_display",
            "logo", "description", "contact_email", "contact_phone",
            "website", "is_active", "services", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class PartnerReferralSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source="partner.name", read_only=True)
    user_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = PartnerReferral
        fields = [
            "id", "partner", "partner_name", "user", "user_name",
            "transaction", "referral_type", "status", "status_display",
            "notes", "created_at",
        ]
        read_only_fields = ["id", "user", "user_name", "status", "created_at"]

    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.email


class PartnerReferralCreateSerializer(serializers.Serializer):
    partner_id = serializers.UUIDField()
    referral_type = serializers.CharField(max_length=50, required=False, default="")
    notes = serializers.CharField(required=False, default="")
    transaction_id = serializers.UUIDField(required=False, allow_null=True)


# ─── Ambassadeurs ────────────────────────────────────────


class AmbassadorProfileSerializer(serializers.ModelSerializer):
    tier_display = serializers.CharField(source="get_tier_display", read_only=True)
    conversion_rate = serializers.FloatField(read_only=True)
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = AmbassadorProfile
        fields = [
            "id", "user", "user_name", "ambassador_code", "tier", "tier_display",
            "total_referrals", "total_conversions", "total_earnings",
            "commission_rate", "conversion_rate", "is_active", "created_at",
        ]
        read_only_fields = [
            "id", "user", "ambassador_code", "tier", "total_referrals",
            "total_conversions", "total_earnings", "commission_rate",
            "is_active", "created_at",
        ]

    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.email


class ReferralProgramSerializer(serializers.ModelSerializer):
    referrer_name = serializers.SerializerMethodField()
    referred_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = ReferralProgram
        fields = [
            "id", "referrer", "referrer_name", "referred", "referred_name",
            "referral_code", "status", "status_display",
            "reward_type", "reward_amount", "reward_claimed", "created_at",
        ]
        read_only_fields = fields

    def get_referrer_name(self, obj):
        return obj.referrer.get_full_name() or obj.referrer.email

    def get_referred_name(self, obj):
        return obj.referred.get_full_name() or obj.referred.email
