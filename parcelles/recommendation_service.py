"""
Service de recommandation personnalisée — EYE-FONCIER
Retourne les parcelles promues les plus pertinentes pour chaque profil utilisateur.
"""
import logging
from django.db.models import Q, F
from django.utils import timezone

logger = logging.getLogger(__name__)


def get_personalized_recommendations(user, limit=5):
    """
    Retourne les parcelles promues les plus pertinentes pour le profil utilisateur.

    Stratégie en 3 niveaux :
    1. Si BuyerProfile existe → utiliser les MatchScores avec PromotionCampaign active
    2. Sinon → utiliser l'historique de navigation (ParcelleReaction, AccessLog)
    3. Fallback → promotions actives triées par pertinence (impressions/clics)
    """
    from parcelles.models import Parcelle, PromotionCampaign, ParcelleReaction

    now = timezone.now()
    # Parcelles avec promotion active
    promoted_parcelle_ids = PromotionCampaign.objects.filter(
        status="active",
        start_date__lte=now,
        end_date__gte=now,
    ).values_list("parcelle_id", flat=True)

    if not promoted_parcelle_ids:
        # Fallback : parcelles disponibles récentes
        return _fallback_recommendations(limit)

    # ── Stratégie 1 : Smart Matching ──
    if user.is_authenticated:
        try:
            from analysis.models import BuyerProfile, MatchScore
            buyer_profile = BuyerProfile.objects.filter(user=user).first()
            if buyer_profile:
                matches = MatchScore.objects.filter(
                    buyer_profile=buyer_profile,
                    parcelle_id__in=promoted_parcelle_ids,
                    parcelle__status="disponible",
                    parcelle__is_validated=True,
                ).select_related(
                    "parcelle", "parcelle__owner"
                ).order_by("-final_score")[:limit]

                if matches.exists():
                    return [
                        _serialize_recommendation(m.parcelle, score=m.final_score)
                        for m in matches
                    ]
        except Exception as e:
            logger.debug("Smart matching fallback : %s", e)

        # ── Stratégie 2 : Historique de navigation ──
        try:
            liked_types = ParcelleReaction.objects.filter(
                user=user,
                reaction_type__in=["like", "favorite", "interested"],
            ).values_list("parcelle__land_type", flat=True).distinct()

            if liked_types:
                parcelles = Parcelle.objects.filter(
                    pk__in=promoted_parcelle_ids,
                    land_type__in=liked_types,
                    status="disponible",
                    is_validated=True,
                ).select_related("owner").order_by("-created_at")[:limit]

                if parcelles.exists():
                    return [_serialize_recommendation(p) for p in parcelles]
        except Exception as e:
            logger.debug("Historique fallback : %s", e)

    # ── Stratégie 3 : Fallback — promotions actives ──
    return _fallback_recommendations(limit, promoted_parcelle_ids)


def _fallback_recommendations(limit=5, promoted_ids=None):
    """Retourne les promotions actives les plus populaires."""
    from parcelles.models import Parcelle

    qs = Parcelle.objects.filter(
        status="disponible",
        is_validated=True,
    ).select_related("owner").order_by("-created_at")

    if promoted_ids is not None:
        qs = qs.filter(pk__in=promoted_ids)

    return [_serialize_recommendation(p) for p in qs[:limit]]


def _serialize_recommendation(parcelle, score=None):
    """Sérialise une parcelle pour l'API de recommandation."""
    data = {
        "id": str(parcelle.pk),
        "lot_number": parcelle.lot_number,
        "title": parcelle.title or f"Lot {parcelle.lot_number}",
        "land_type": parcelle.get_land_type_display() if hasattr(parcelle, "get_land_type_display") else parcelle.land_type,
        "surface_m2": parcelle.surface_m2,
        "price": str(parcelle.price) if parcelle.price else "0",
        "price_formatted": "{:,.0f}".format(parcelle.price) if parcelle.price else "N/A",
        "address": parcelle.address or "",
        "owner_name": parcelle.owner.get_full_name() if parcelle.owner else "",
        "status": parcelle.status,
    }
    if score is not None:
        data["match_score"] = round(float(score), 1)

    # Image
    if hasattr(parcelle, "medias"):
        first_media = parcelle.medias.filter(media_type="image").first()
        if first_media:
            data["image_url"] = first_media.file.url
    return data
