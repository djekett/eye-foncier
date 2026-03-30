from rest_framework import serializers
from .models import FinancialScore, SimulationResult, Transaction, TransactionEvent


class TransactionSerializer(serializers.ModelSerializer):
    buyer_name = serializers.CharField(source="buyer.get_full_name", read_only=True)
    seller_name = serializers.CharField(source="seller.get_full_name", read_only=True)
    parcelle_lot = serializers.CharField(source="parcelle.lot_number", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Transaction
        fields = [
            "id", "reference", "parcelle", "parcelle_lot",
            "buyer", "buyer_name", "seller", "seller_name",
            "amount", "status", "status_display", "payment_method",
            "notes", "reserved_at", "completed_at", "created_at",
        ]
        read_only_fields = ["id", "reference", "created_at"]


class TransactionEventSerializer(serializers.ModelSerializer):
    event_type_display = serializers.CharField(
        source="get_event_type_display", read_only=True
    )
    actor_name = serializers.CharField(
        source="actor.get_full_name", read_only=True, default=""
    )

    class Meta:
        model = TransactionEvent
        fields = [
            "id", "event_type", "event_type_display",
            "old_status", "new_status", "actor_name",
            "description", "created_at",
        ]


class FinancialScoreSerializer(serializers.ModelSerializer):
    grade_display = serializers.CharField(
        source="get_grade_display", read_only=True
    )
    employment_display = serializers.CharField(
        source="get_employment_type_display", read_only=True
    )

    class Meta:
        model = FinancialScore
        fields = [
            "overall_score", "grade", "grade_display",
            "score_kyc", "score_revenue", "score_history", "score_mobile_money",
            "max_purchase_capacity", "monthly_capacity",
            "revenue_declared", "employment_type", "employment_display",
            "mobile_money_verified", "breakdown", "computed_at",
        ]
        read_only_fields = fields


class SimulatorInputSerializer(serializers.Serializer):
    property_price = serializers.DecimalField(max_digits=15, decimal_places=0, min_value=100000)
    down_payment = serializers.DecimalField(max_digits=15, decimal_places=0, min_value=0)
    duration_months = serializers.IntegerField(min_value=6, max_value=240)
    interest_rate = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=30)

    def validate(self, data):
        if data["down_payment"] >= data["property_price"]:
            raise serializers.ValidationError(
                "L'apport initial doit être inférieur au prix du bien."
            )
        return data


class SimulationResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = SimulationResult
        fields = [
            "id", "property_price", "down_payment", "loan_amount",
            "duration_months", "interest_rate", "monthly_payment",
            "total_cost", "total_interest", "amortization_table",
            "is_feasible", "feasibility_notes", "created_at",
        ]
        read_only_fields = fields
