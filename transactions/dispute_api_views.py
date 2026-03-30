"""
API REST des litiges — EYE-FONCIER
Endpoints pour la gestion des litiges via l'API.
"""
import logging

from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .dispute_models import Dispute, DisputeEvidence
from .dispute_serializers import (
    DisputeListSerializer,
    DisputeDetailSerializer,
    DisputeEvidenceSerializer,
    OpenDisputeSerializer,
    ResolveDisputeSerializer,
    DisputeMessageCreateSerializer,
)
from .dispute_service import (
    open_dispute, resolve_dispute, add_message,
    transition_dispute, get_dispute_stats,
)
from .models import Transaction

logger = logging.getLogger(__name__)


class DisputeListAPIView(generics.ListAPIView):
    """
    GET /api/v1/transactions/litiges/
    Liste les litiges de l'utilisateur connecte.
    Les admins voient tous les litiges.
    """
    serializer_class = DisputeListSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Dispute.objects.select_related(
            "transaction", "transaction__parcelle",
            "opened_by", "assigned_to",
        )
        if user.is_staff:
            return qs
        return qs.filter(
            models__isnull=True,  # fallback
        ).none() | qs.filter(
            transaction__buyer=user,
        ) | qs.filter(
            transaction__seller=user,
        ) | qs.filter(
            opened_by=user,
        )

    def get_queryset(self):
        user = self.request.user
        qs = Dispute.objects.select_related(
            "transaction", "transaction__parcelle",
            "opened_by", "assigned_to",
        )
        if user.is_staff:
            return qs

        from django.db.models import Q
        return qs.filter(
            Q(transaction__buyer=user)
            | Q(transaction__seller=user)
            | Q(opened_by=user)
        ).distinct()


class DisputeDetailAPIView(generics.RetrieveAPIView):
    """
    GET /api/v1/transactions/litiges/<uuid:pk>/
    Detail d'un litige avec messages et preuves.
    """
    serializer_class = DisputeDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "pk"

    def get_queryset(self):
        user = self.request.user
        qs = Dispute.objects.select_related(
            "transaction", "transaction__parcelle",
            "transaction__buyer", "transaction__seller",
            "opened_by", "assigned_to",
        ).prefetch_related("evidences", "messages")

        if user.is_staff:
            return qs

        from django.db.models import Q
        return qs.filter(
            Q(transaction__buyer=user)
            | Q(transaction__seller=user)
            | Q(opened_by=user)
        )


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def api_open_dispute(request):
    """
    POST /api/v1/transactions/litiges/ouvrir/
    Ouvre un nouveau litige sur une transaction.
    """
    serializer = OpenDisputeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    try:
        transaction = Transaction.objects.get(pk=data["transaction_id"])
    except Transaction.DoesNotExist:
        return Response(
            {"error": "Transaction introuvable."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Verifier que l'utilisateur est partie prenante
    user = request.user
    if user not in (transaction.buyer, transaction.seller) and not user.is_staff:
        return Response(
            {"error": "Vous n'etes pas autorise a ouvrir un litige sur cette transaction."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        dispute = open_dispute(
            transaction=transaction,
            opened_by=user,
            category=data["category"],
            subject=data["subject"],
            description=data["description"],
            priority=data.get("priority", "normal"),
        )
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(
        DisputeDetailSerializer(dispute, context={"request": request}).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def api_resolve_dispute(request, pk):
    """
    POST /api/v1/transactions/litiges/<uuid:pk>/resoudre/
    Resout un litige (admin/mediateur uniquement).
    """
    if not request.user.is_staff:
        return Response(
            {"error": "Seuls les administrateurs peuvent resoudre un litige."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        dispute = Dispute.objects.get(pk=pk)
    except Dispute.DoesNotExist:
        return Response({"error": "Litige introuvable."}, status=status.HTTP_404_NOT_FOUND)

    serializer = ResolveDisputeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    try:
        dispute = resolve_dispute(
            dispute=dispute,
            actor=request.user,
            resolution_type=data["resolution_type"],
            notes=data.get("notes", ""),
            refund_amount=data.get("refund_amount"),
        )
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(
        DisputeDetailSerializer(dispute, context={"request": request}).data,
    )


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def api_add_dispute_message(request, pk):
    """
    POST /api/v1/transactions/litiges/<uuid:pk>/messages/
    Ajoute un message au fil de discussion du litige.
    """
    try:
        dispute = Dispute.objects.select_related("transaction").get(pk=pk)
    except Dispute.DoesNotExist:
        return Response({"error": "Litige introuvable."}, status=status.HTTP_404_NOT_FOUND)

    # Verifier l'acces
    user = request.user
    tx = dispute.transaction
    if user not in (tx.buyer, tx.seller) and not user.is_staff:
        return Response(
            {"error": "Acces refuse."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = DisputeMessageCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    # Les notes internes ne sont possibles que pour les staff
    if data.get("is_internal") and not user.is_staff:
        data["is_internal"] = False

    try:
        message = add_message(
            dispute=dispute,
            sender=user,
            content=data["content"],
            is_internal=data.get("is_internal", False),
        )
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    from .dispute_serializers import DisputeMessageSerializer
    return Response(
        DisputeMessageSerializer(message).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def api_add_dispute_evidence(request, pk):
    """
    POST /api/v1/transactions/litiges/<uuid:pk>/preuves/
    Upload une piece a conviction pour un litige.
    """
    try:
        dispute = Dispute.objects.select_related("transaction").get(pk=pk)
    except Dispute.DoesNotExist:
        return Response({"error": "Litige introuvable."}, status=status.HTTP_404_NOT_FOUND)

    if not dispute.is_open:
        return Response(
            {"error": "Impossible d'ajouter des preuves a un litige clos."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = request.user
    tx = dispute.transaction
    if user not in (tx.buyer, tx.seller) and not user.is_staff:
        return Response({"error": "Acces refuse."}, status=status.HTTP_403_FORBIDDEN)

    serializer = DisputeEvidenceSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    evidence = serializer.save(dispute=dispute, uploaded_by=user)

    return Response(
        DisputeEvidenceSerializer(evidence).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([permissions.IsAdminUser])
def api_dispute_stats(request):
    """
    GET /api/v1/transactions/litiges/stats/
    Statistiques des litiges (admin uniquement).
    """
    stats = get_dispute_stats()
    return Response(stats)
