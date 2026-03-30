"""
Smart Matching Engine — EYE-FONCIER
Module 1 : Algorithme de compatibilité Vendeur-Client.

Score final : S = (Wp × Sprix) + (Wl × Sloc) + (Wt × Stech) + (Wv × Svendeur)

Calcul déclenché :
  - À chaque ajout de parcelle (pour tous les acheteurs actifs)
  - À chaque mise à jour de profil acheteur (pour toutes les parcelles dispo)
"""
import logging
import math

from django.utils import timezone
from django.contrib.gis.geos import Point

logger = logging.getLogger("analysis")


def compute_match_for_buyer(buyer_profile, parcelles=None):
    """Calcule les scores pour un acheteur contre toutes les parcelles disponibles.

    Args:
        buyer_profile: BuyerProfile instance
        parcelles: queryset de Parcelle (optionnel, toutes dispo par défaut)

    Returns:
        list[MatchScore]: scores calculés/mis à jour
    """
    from parcelles.models import Parcelle
    from analysis.models import MatchScore

    if parcelles is None:
        parcelles = Parcelle.objects.filter(
            status="disponible", is_validated=True,
        ).select_related("owner", "owner__profile", "zone")

    scores = []
    for parcelle in parcelles:
        score = _compute_single_match(buyer_profile, parcelle)
        if score:
            scores.append(score)

    logger.info(
        "Matching calculé: %s — %d parcelles, meilleur score: %s%%",
        buyer_profile.user.get_full_name(),
        len(scores),
        int(scores[0].final_score) if scores else "N/A",
    )
    return scores


def compute_match_for_parcelle(parcelle, buyer_profiles=None):
    """Calcule les scores pour une parcelle contre tous les acheteurs actifs.

    Args:
        parcelle: Parcelle instance
        buyer_profiles: queryset de BuyerProfile (optionnel)

    Returns:
        list[MatchScore]: scores calculés/mis à jour
    """
    from analysis.models import BuyerProfile, MatchScore

    if buyer_profiles is None:
        buyer_profiles = BuyerProfile.objects.filter(
            is_active=True,
        ).select_related("user", "user__profile")

    scores = []
    for bp in buyer_profiles:
        score = _compute_single_match(bp, parcelle)
        if score:
            scores.append(score)

    # Envoyer les notifications pour les scores élevés
    _send_golden_notifications(scores)

    return scores


def _compute_single_match(buyer_profile, parcelle):
    """Calcule le score entre un acheteur et une parcelle.

    S = (Wp × Sprix) + (Wl × Sloc) + (Wt × Stech) + (Wv × Svendeur)
    """
    from analysis.models import MatchScore

    bp = buyer_profile

    # ═══ Score Prix (Sprix) ═══
    s_price, price_detail = _score_price(bp, parcelle)

    # ═══ Score Localisation (Sloc) ═══
    s_location, loc_detail = _score_location(bp, parcelle)

    # ═══ Score Technique (Stech) ═══
    s_technical, tech_detail = _score_technical(parcelle)

    # ═══ Score Vendeur (Svendeur) ═══
    s_seller, seller_detail = _score_seller(parcelle)

    # ═══ Score pondéré final ═══
    final = (
        bp.weight_price * s_price
        + bp.weight_location * s_location
        + bp.weight_technical * s_technical
        + bp.weight_seller * s_seller
    )
    final = round(min(100, max(0, final)), 1)

    breakdown = {
        "price": {"score": s_price, "weight": bp.weight_price, "detail": price_detail},
        "location": {"score": s_location, "weight": bp.weight_location, "detail": loc_detail},
        "technical": {"score": s_technical, "weight": bp.weight_technical, "detail": tech_detail},
        "seller": {"score": s_seller, "weight": bp.weight_seller, "detail": seller_detail},
        "formula": "S = ({w_p}×{s_p:.0f}) + ({w_l}×{s_l:.0f}) + ({w_t}×{s_t:.0f}) + ({w_v}×{s_v:.0f}) = {f:.1f}".format(
            w_p=bp.weight_price, s_p=s_price,
            w_l=bp.weight_location, s_l=s_location,
            w_t=bp.weight_technical, s_t=s_technical,
            w_v=bp.weight_seller, s_v=s_seller,
            f=final,
        ),
    }

    match_score, _ = MatchScore.objects.update_or_create(
        buyer_profile=bp,
        parcelle=parcelle,
        defaults={
            "score_price": s_price,
            "score_location": s_location,
            "score_technical": s_technical,
            "score_seller": s_seller,
            "final_score": final,
            "breakdown": breakdown,
        },
    )
    return match_score


# ─── Composants du score ───────────────────────────────────

def _score_price(bp, parcelle):
    """Score prix (0-100).
    Analyse budget + rapport prix/marché.
    """
    detail = {}
    score = 50.0  # Base neutre

    price = float(parcelle.price) if parcelle.price else 0
    if price == 0:
        return 50, {"reason": "Prix non renseigné"}

    # 1. Dans le budget ?
    budget_min = float(bp.budget_min) if bp.budget_min else 0
    budget_max = float(bp.budget_max) if bp.budget_max else float("inf")

    if budget_min <= price <= budget_max:
        # Dans le budget — bonus progressif (plus c'est en dessous du max, mieux c'est)
        if budget_max and budget_max > 0:
            ratio = price / budget_max
            score = 70 + (1 - ratio) * 30  # 70-100
            detail["budget"] = "Dans le budget ({:.0f}% du max)".format(ratio * 100)
        else:
            score = 80
            detail["budget"] = "Dans le budget"
    elif price < budget_min:
        # Sous le budget — suspicieux mais intéressant
        score = 60
        detail["budget"] = "Sous le budget minimum"
    else:
        # Hors budget
        overshoot = (price - budget_max) / max(budget_max, 1) * 100
        score = max(0, 50 - overshoot)
        detail["budget"] = "Hors budget (+{:.0f}%)".format(overshoot)

    # 2. Rapport prix/marché local (bonus si sous le marché)
    from parcelles.models import Parcelle
    zone_avg = _get_zone_avg_price(parcelle)
    if zone_avg and parcelle.price_per_m2:
        market_ratio = float(parcelle.price_per_m2) / zone_avg
        if market_ratio < 0.9:
            score = min(100, score + 15)
            detail["market"] = "Sous le marché local ({:.0f}%)".format((1 - market_ratio) * 100)
        elif market_ratio > 1.1:
            score = max(0, score - 10)
            detail["market"] = "Au-dessus du marché (+{:.0f}%)".format((market_ratio - 1) * 100)
        else:
            detail["market"] = "Prix conforme au marché"

    return round(score, 1), detail


def _score_location(bp, parcelle):
    """Score localisation (0-100).
    Zone préférée + distance au point de référence + zone de recherche.
    """
    detail = {}
    score = 50.0

    # 1. Zone préférée
    if bp.preferred_zones.exists():
        if parcelle.zone and bp.preferred_zones.filter(pk=parcelle.zone.pk).exists():
            score += 25
            detail["zone"] = "Zone préférée"
        else:
            score -= 10
            detail["zone"] = "Zone non préférée"

    # 2. Type de terrain préféré
    if bp.preferred_land_types:
        if parcelle.land_type in bp.preferred_land_types:
            score += 10
            detail["land_type"] = "Type de terrain souhaité"
        else:
            score -= 5
            detail["land_type"] = "Type de terrain non souhaité"

    # 3. Surface souhaitée
    surface = float(parcelle.surface_m2) if parcelle.surface_m2 else 0
    surf_min = float(bp.surface_min) if bp.surface_min else 0
    surf_max = float(bp.surface_max) if bp.surface_max else float("inf")
    if surf_min <= surface <= surf_max:
        score += 10
        detail["surface"] = "Surface dans la fourchette"
    elif surface > 0:
        score -= 10
        detail["surface"] = "Surface hors fourchette"

    # 4. Distance au point de référence
    if bp.reference_point and parcelle.centroid:
        dist_deg = bp.reference_point.distance(parcelle.centroid)
        dist_km = dist_deg * 111.32
        # Estimer temps de trajet (~30 km/h en ville Abidjan)
        travel_min = dist_km / 0.5  # 30 km/h
        max_travel = bp.max_travel_minutes or 60

        if travel_min <= max_travel:
            ratio = travel_min / max_travel
            score += 15 * (1 - ratio)
            detail["travel"] = "{:.0f} min (max: {} min)".format(travel_min, max_travel)
        else:
            overshoot = (travel_min - max_travel) / max_travel
            score -= min(20, overshoot * 20)
            detail["travel"] = "Trop loin ({:.0f} min > {} min)".format(travel_min, max_travel)

    # 5. Zone de recherche géographique
    if bp.search_area and parcelle.geometry:
        if bp.search_area.contains(parcelle.centroid or parcelle.geometry.centroid):
            score += 15
            detail["search_area"] = "Dans la zone de recherche"
        else:
            score -= 5
            detail["search_area"] = "Hors zone de recherche"

    return round(min(100, max(0, score)), 1), detail


def _score_technical(parcelle):
    """Score technique (0-100) basé sur l'analyse terrain."""
    detail = {}

    try:
        terrain = parcelle.terrain_analysis
        score = terrain.technical_score or 50
        detail["slope"] = "{:.1f}% ({})".format(
            terrain.slope_mean or 0,
            terrain.get_slope_category_display() if terrain.slope_category else "N/A",
        )
        detail["drainage"] = terrain.drainage_quality or "N/A"
        detail["constructible"] = terrain.slope_is_constructible
    except Exception:
        score = 50
        detail["note"] = "Pas d'analyse terrain disponible"

    # Pénalité pour contraintes critiques
    constraints = list(parcelle.spatial_constraints.all())
    critical = sum(1 for c in constraints if c.severity == "critical")
    if critical > 0:
        score = max(0, score - critical * 20)
        detail["constraints"] = "{} contrainte(s) critique(s)".format(critical)

    return round(score, 1), detail


def _score_seller(parcelle):
    """Score fiabilité vendeur (0-100)."""
    detail = {}
    score = 50.0

    owner = parcelle.owner
    if not owner:
        return 50, {"note": "Vendeur inconnu"}

    # 1. Badge de confiance
    if parcelle.trust_badge:
        score += 20
        detail["trust_badge"] = True

    # 2. Compte vérifié
    if owner.is_verified:
        score += 15
        detail["verified"] = True

    # 3. Profil KYC
    try:
        profile = owner.profile
        if profile.is_kyc_verified:
            score += 15
            detail["kyc"] = "Vérifié"
        elif profile.kyc_status == "submitted":
            score += 5
            detail["kyc"] = "Soumis"

        # Trust score du profil
        trust = float(profile.trust_score or 0)
        score += trust * 3  # 0-10 → 0-30
        detail["trust_score"] = trust

        # Historique de ventes
        if profile.total_sales > 5:
            score += 10
            detail["sales"] = "{} ventes".format(profile.total_sales)
    except Exception:
        pass

    # 4. Parcelle validée par géomètre
    if parcelle.is_validated:
        score += 10
        detail["validated"] = True

    # 5. Documents
    doc_count = parcelle.documents.filter(is_verified=True).count()
    if doc_count >= 3:
        score += 10
        detail["docs"] = "{} docs vérifiés".format(doc_count)
    elif doc_count > 0:
        score += 5
        detail["docs"] = "{} doc(s) vérifié(s)".format(doc_count)

    return round(min(100, max(0, score)), 1), detail


def _get_zone_avg_price(parcelle):
    """Prix moyen au m² dans la zone."""
    from parcelles.models import Parcelle
    if not parcelle.zone:
        return None

    prices = Parcelle.objects.filter(
        zone=parcelle.zone,
        status="disponible",
        price_per_m2__isnull=False,
    ).exclude(pk=parcelle.pk).values_list("price_per_m2", flat=True)

    if not prices:
        return None
    return sum(float(p) for p in prices) / len(prices)


# ═══════════════════════════════════════════════════════════
# NOTIFICATIONS "OPPORTUNITÉ EN OR"
# ═══════════════════════════════════════════════════════════

def _send_golden_notifications(match_scores):
    """Envoie des notifications pour les scores au-dessus du seuil."""
    from analysis.models import MatchNotification

    for ms in match_scores:
        if not ms.is_golden_opportunity or ms.is_notified:
            continue

        title = "Opportunité en Or — {:.0f}% de compatibilité !".format(ms.final_score)
        message = (
            "Le terrain « {lot} » à {zone} correspond à {score:.0f}% "
            "de vos critères ! "
            "Prix : {price} FCFA — Surface : {surface} m²."
        ).format(
            lot=ms.parcelle.lot_number,
            zone=ms.parcelle.zone.name if ms.parcelle.zone else "N/A",
            score=ms.final_score,
            price="{:,.0f}".format(float(ms.parcelle.price)) if ms.parcelle.price else "N/A",
            surface="{:,.0f}".format(float(ms.parcelle.surface_m2)) if ms.parcelle.surface_m2 else "N/A",
        )

        MatchNotification.objects.create(
            match_score=ms,
            channel="inapp",
            title=title,
            message=message,
        )
        ms.is_notified = True
        ms.save(update_fields=["is_notified"])

        # Dispatch via le système de notifications unifié
        try:
            from notifications.services import send_notification

            send_notification(
                recipient=ms.buyer_profile.user,
                notification_type="match_found",
                title=title,
                message=message,
                data={
                    "parcelle_id": str(ms.parcelle.pk),
                    "match_score_id": str(ms.pk),
                    "final_score": ms.final_score,
                },
            )
        except Exception as e:
            logger.warning("Notification unifiée échouée: %s", e)

        logger.info(
            "Notification envoyée: %s → %s (%s%%)",
            ms.parcelle.lot_number,
            ms.buyer_profile.user.email,
            int(ms.final_score),
        )
