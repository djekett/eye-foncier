from decimal import Decimal

from django.db.models import Q
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from parcelles.models import Parcelle

from .models import FinancialScore, SimulationResult, Transaction
from .scoring_service import check_buyer_eligibility, compute_financial_score, simulate_purchase
from .serializers import (
    FinancialScoreSerializer,
    SimulationResultSerializer,
    SimulatorInputSerializer,
    TransactionSerializer,
)


class TransactionListAPIView(generics.ListAPIView):
    serializer_class = TransactionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_admin_role:
            return Transaction.objects.all()
        return Transaction.objects.filter(Q(buyer=user) | Q(seller=user))


class TransactionDetailAPIView(generics.RetrieveAPIView):
    serializer_class = TransactionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_admin_role:
            return Transaction.objects.all()
        return Transaction.objects.filter(Q(buyer=user) | Q(seller=user))


class FinancialScoreAPIView(APIView):
    """GET : score actuel. POST : recalculer."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            score = request.user.financial_score
            return Response(FinancialScoreSerializer(score).data)
        except FinancialScore.DoesNotExist:
            return Response({"detail": "Aucun score calculé."}, status=404)

    def post(self, request):
        score = compute_financial_score(request.user)
        return Response(FinancialScoreSerializer(score).data)


class SimulatorAPIView(APIView):
    """POST : calcul de simulation d'achat-vente."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = SimulatorInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        result = simulate_purchase(
            property_price=data["property_price"],
            down_payment=data["down_payment"],
            duration_months=data["duration_months"],
            interest_rate=data["interest_rate"],
        )

        # Sauvegarder si utilisateur authentifié
        if request.user.is_authenticated:
            SimulationResult.objects.create(
                user=request.user,
                property_price=data["property_price"],
                down_payment=data["down_payment"],
                loan_amount=result["loan_amount"],
                duration_months=data["duration_months"],
                interest_rate=data["interest_rate"],
                monthly_payment=result["monthly_payment"],
                total_cost=result["total_cost"],
                total_interest=result["total_interest"],
                amortization_table=result["amortization_table"],
            )

        return Response(result)


class EligibilityCheckAPIView(APIView):
    """GET : vérifie l'éligibilité d'un acheteur pour une parcelle."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, parcelle_pk):
        try:
            parcelle = Parcelle.objects.get(pk=parcelle_pk)
        except Parcelle.DoesNotExist:
            return Response({"detail": "Parcelle introuvable."}, status=404)

        result = check_buyer_eligibility(request.user, parcelle)
        return Response({
            "eligible": result["eligible"],
            "grade": result["grade"],
            "overall_score": result["overall_score"],
            "reason": result["reason"],
            "recommended_down_payment": result["recommended_down_payment"],
        })
