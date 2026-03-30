"""
API Cotation — EYE-FONCIER
Endpoints REST pour le flux cotation mobile/SPA.
"""
import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from parcelles.models import Parcelle
from .cotation_models import Cotation, Boutique, VerificationRequest
from .cotation_serializers import (
    CotationSerializer,
    CotationCreateSerializer,
    BoutiqueCotationCreateSerializer,
    BoutiqueSerializer,
    VerificationRequestSerializer,
    VerificationAdvanceSerializer,
    CotationCheckSerializer,
)
from .cotation_service import (
    create_achat_cotation,
    initiate_cotation_payment,
    confirm_cotation_payment,
    check_cotation_access,
    has_valid_cotation,
    create_boutique_cotation,
    advance_verification,
)

logger = logging.getLogger("cotation")


# ═══════════════════════════════════════════════════════════
# COTATION D'ACHAT
# ═══════════════════════════════════════════════════════════

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_cotation_create(request):
    """Créer et initier le paiement d'une cotation d'achat."""
    serializer = CotationCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    parcelle_id = serializer.validated_data["parcelle_id"]
    payment_method = serializer.validated_data["payment_method"]

    try:
        parcelle = Parcelle.objects.get(pk=parcelle_id)
    except Parcelle.DoesNotExist:
        return Response(
            {"error": "Parcelle introuvable."},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        cotation = create_achat_cotation(request.user, parcelle)
        payment_result = initiate_cotation_payment(cotation, payment_method)

        # Si mode simulation, confirmer directement
        if payment_result.get("mode") == "simulation":
            confirm_cotation_payment(cotation)

        return Response({
            "cotation": CotationSerializer(cotation).data,
            "payment": payment_result,
        }, status=status.HTTP_201_CREATED)

    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_cotation_check(request, parcelle_pk):
    """Vérifier si l'utilisateur a une cotation validée pour une parcelle."""
    try:
        parcelle = Parcelle.objects.get(pk=parcelle_pk)
    except Parcelle.DoesNotExist:
        return Response(
            {"error": "Parcelle introuvable."},
            status=status.HTTP_404_NOT_FOUND,
        )

    cotation = check_cotation_access(request.user, parcelle)
    valid = cotation is not None and cotation.is_valid

    data = {
        "has_cotation": valid,
        "cotation": CotationSerializer(cotation).data if cotation else None,
        "can_visit": valid,
        "can_view_docs": valid,
        "can_reserve": valid,
    }
    return Response(data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_cotation_detail(request, pk):
    """Détail d'une cotation."""
    try:
        cotation = Cotation.objects.get(pk=pk)
    except Cotation.DoesNotExist:
        return Response(
            {"error": "Cotation introuvable."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if cotation.payer != request.user and not request.user.is_admin_role:
        return Response(
            {"error": "Non autorisé."},
            status=status.HTTP_403_FORBIDDEN,
        )

    return Response(CotationSerializer(cotation).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_my_cotations(request):
    """Liste des cotations de l'utilisateur connecté."""
    cotations = Cotation.objects.filter(payer=request.user).select_related("parcelle")
    return Response(CotationSerializer(cotations, many=True).data)


# ═══════════════════════════════════════════════════════════
# BOUTIQUE
# ═══════════════════════════════════════════════════════════

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_boutique_cotation_create(request):
    """Créer une cotation boutique pour un vendeur/promoteur."""
    serializer = BoutiqueCotationCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    boutique_name = serializer.validated_data["boutique_name"]
    payment_method = serializer.validated_data["payment_method"]

    try:
        cotation = create_boutique_cotation(request.user, boutique_name)
        payment_result = initiate_cotation_payment(cotation, payment_method)

        if payment_result.get("mode") == "simulation":
            confirm_cotation_payment(cotation)

        return Response({
            "cotation": CotationSerializer(cotation).data,
            "payment": payment_result,
        }, status=status.HTTP_201_CREATED)

    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_my_boutique(request):
    """Récupérer la boutique de l'utilisateur connecté."""
    boutique = getattr(request.user, "boutique", None)
    if not boutique:
        return Response(
            {"error": "Aucune boutique trouvée."},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response(BoutiqueSerializer(boutique).data)


# ═══════════════════════════════════════════════════════════
# VÉRIFICATION
# ═══════════════════════════════════════════════════════════

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_verification_list(request):
    """Liste des vérifications (filtrée par rôle)."""
    user = request.user

    if user.is_admin_role:
        qs = VerificationRequest.objects.all()
    elif user.is_geometre:
        qs = VerificationRequest.objects.filter(verifier=user)
    elif user.is_acheteur:
        qs = VerificationRequest.objects.filter(buyer=user)
    elif user.is_vendeur:
        qs = VerificationRequest.objects.filter(seller=user)
    else:
        return Response([])

    qs = qs.select_related("buyer", "seller", "verifier", "parcelle")

    status_filter = request.query_params.get("status", "")
    if status_filter:
        qs = qs.filter(status=status_filter)

    return Response(VerificationRequestSerializer(qs, many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_verification_detail(request, pk):
    """Détail d'une vérification."""
    try:
        verification = VerificationRequest.objects.select_related(
            "buyer", "seller", "verifier", "parcelle", "cotation",
        ).get(pk=pk)
    except VerificationRequest.DoesNotExist:
        return Response(
            {"error": "Vérification introuvable."},
            status=status.HTTP_404_NOT_FOUND,
        )

    user = request.user
    authorized = any([
        user.is_admin_role,
        user == verification.verifier,
        user == verification.buyer,
        user == verification.seller,
    ])
    if not authorized:
        return Response(
            {"error": "Non autorisé."},
            status=status.HTTP_403_FORBIDDEN,
        )

    return Response(VerificationRequestSerializer(verification).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_verification_advance(request, pk):
    """Avancer le workflow de vérification."""
    try:
        verification = VerificationRequest.objects.get(pk=pk)
    except VerificationRequest.DoesNotExist:
        return Response(
            {"error": "Vérification introuvable."},
            status=status.HTTP_404_NOT_FOUND,
        )

    user = request.user
    if not (user.is_admin_role or user == verification.verifier):
        return Response(
            {"error": "Seul le vérificateur peut avancer."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = VerificationAdvanceSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        advance_verification(
            verification,
            serializer.validated_data["new_status"],
            user,
            serializer.validated_data.get("notes", ""),
        )
        return Response(VerificationRequestSerializer(verification).data)
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
