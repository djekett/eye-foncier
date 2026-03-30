"""
Serializers des litiges — EYE-FONCIER
"""
from rest_framework import serializers
from .dispute_models import Dispute, DisputeEvidence, DisputeMessage


class DisputeEvidenceSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = DisputeEvidence
        fields = [
            "id", "evidence_type", "title", "description", "file",
            "file_size", "uploaded_by", "uploaded_by_name",
            "verified", "created_at",
        ]
        read_only_fields = ["id", "uploaded_by", "file_size", "verified", "created_at"]

    def get_uploaded_by_name(self, obj):
        return obj.uploaded_by.get_full_name() or obj.uploaded_by.email


class DisputeMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()

    class Meta:
        model = DisputeMessage
        fields = [
            "id", "sender", "sender_name", "sender_role",
            "content", "attachment", "is_internal", "created_at",
        ]
        read_only_fields = ["id", "sender", "sender_role", "created_at"]

    def get_sender_name(self, obj):
        return obj.sender.get_full_name() or obj.sender.email


class DisputeListSerializer(serializers.ModelSerializer):
    """Serializer leger pour les listes de litiges."""
    transaction_reference = serializers.CharField(source="transaction.reference", read_only=True)
    parcelle_lot = serializers.CharField(source="transaction.parcelle.lot_number", read_only=True)
    opened_by_name = serializers.SerializerMethodField()
    assigned_to_name = serializers.SerializerMethodField()
    is_overdue = serializers.BooleanField(read_only=True)
    days_since_opened = serializers.IntegerField(read_only=True)
    evidence_count = serializers.SerializerMethodField()
    message_count = serializers.SerializerMethodField()

    class Meta:
        model = Dispute
        fields = [
            "id", "reference", "transaction", "transaction_reference",
            "parcelle_lot", "category", "priority", "status", "subject",
            "opened_by", "opened_by_name", "assigned_to", "assigned_to_name",
            "deadline", "is_overdue", "days_since_opened",
            "resolution_type", "refund_amount",
            "evidence_count", "message_count",
            "created_at", "updated_at",
        ]

    def get_opened_by_name(self, obj):
        return obj.opened_by.get_full_name() or obj.opened_by.email

    def get_assigned_to_name(self, obj):
        if obj.assigned_to:
            return obj.assigned_to.get_full_name() or obj.assigned_to.email
        return None

    def get_evidence_count(self, obj):
        return obj.evidences.count()

    def get_message_count(self, obj):
        return obj.messages.filter(is_internal=False).count()


class DisputeDetailSerializer(serializers.ModelSerializer):
    """Serializer complet pour le detail d'un litige."""
    transaction_reference = serializers.CharField(source="transaction.reference", read_only=True)
    parcelle_lot = serializers.CharField(source="transaction.parcelle.lot_number", read_only=True)
    parcelle_title = serializers.CharField(source="transaction.parcelle.title", read_only=True)
    buyer_name = serializers.SerializerMethodField()
    seller_name = serializers.SerializerMethodField()
    opened_by_name = serializers.SerializerMethodField()
    assigned_to_name = serializers.SerializerMethodField()
    evidences = DisputeEvidenceSerializer(many=True, read_only=True)
    messages = serializers.SerializerMethodField()
    is_overdue = serializers.BooleanField(read_only=True)
    days_since_opened = serializers.IntegerField(read_only=True)

    class Meta:
        model = Dispute
        fields = [
            "id", "reference", "transaction", "transaction_reference",
            "parcelle_lot", "parcelle_title",
            "buyer_name", "seller_name",
            "category", "priority", "status", "subject", "description",
            "opened_by", "opened_by_name", "assigned_to", "assigned_to_name",
            "deadline", "is_overdue", "days_since_opened",
            "resolution_type", "resolution_notes",
            "refund_amount", "refund_processed",
            "escalated_at", "resolved_at", "closed_at",
            "evidences", "messages",
            "created_at", "updated_at",
        ]

    def get_buyer_name(self, obj):
        u = obj.transaction.buyer
        return u.get_full_name() or u.email

    def get_seller_name(self, obj):
        u = obj.transaction.seller
        return u.get_full_name() or u.email

    def get_opened_by_name(self, obj):
        return obj.opened_by.get_full_name() or obj.opened_by.email

    def get_assigned_to_name(self, obj):
        if obj.assigned_to:
            return obj.assigned_to.get_full_name() or obj.assigned_to.email
        return None

    def get_messages(self, obj):
        """Filtre les messages internes pour les non-staff."""
        request = self.context.get("request")
        qs = obj.messages.all()
        if request and not request.user.is_staff:
            qs = qs.filter(is_internal=False)
        return DisputeMessageSerializer(qs, many=True).data


class OpenDisputeSerializer(serializers.Serializer):
    """Serializer pour ouvrir un nouveau litige."""
    transaction_id = serializers.UUIDField()
    category = serializers.ChoiceField(choices=Dispute.Category.choices)
    priority = serializers.ChoiceField(choices=Dispute.Priority.choices, default="normal")
    subject = serializers.CharField(max_length=200)
    description = serializers.CharField()


class ResolveDisputeSerializer(serializers.Serializer):
    """Serializer pour resoudre un litige."""
    resolution_type = serializers.ChoiceField(choices=Dispute.Resolution.choices)
    notes = serializers.CharField(required=False, default="")
    refund_amount = serializers.DecimalField(
        max_digits=15, decimal_places=0, required=False, allow_null=True,
    )


class DisputeMessageCreateSerializer(serializers.Serializer):
    """Serializer pour envoyer un message dans un litige."""
    content = serializers.CharField()
    is_internal = serializers.BooleanField(default=False)
