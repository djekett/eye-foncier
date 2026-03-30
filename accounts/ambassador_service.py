"""
Service Ambassadeur — EYE-FONCIER
Calcul des commissions, mise à jour des tiers et statistiques.
"""
import logging
from decimal import Decimal

from django.db import transaction as db_transaction
from django.db.models import Sum, Count, Q

from .models import AmbassadorProfile, ReferralProgram

logger = logging.getLogger(__name__)

# Seuils de tier basés sur le nombre de conversions
TIER_THRESHOLDS = {
    "bronze": 0,
    "silver": 5,
    "gold": 15,
    "platinum": 30,
}

# Taux de commission par tier (%)
TIER_COMMISSION_RATES = {
    "bronze": Decimal("2.00"),
    "silver": Decimal("2.50"),
    "gold": Decimal("3.00"),
    "platinum": Decimal("3.50"),
}


def process_transaction_commission(transaction):
    """
    Calcule et crédite la commission ambassadeur lors de la finalisation
    d'une transaction dont l'acheteur a été référé.

    Appelé depuis transactions/signals.py quand status → completed.
    """
    buyer = transaction.buyer

    # Vérifier si l'acheteur a été référé
    try:
        referral = ReferralProgram.objects.get(referred=buyer)
    except ReferralProgram.DoesNotExist:
        return

    # Vérifier si le référent est ambassadeur
    try:
        ambassador = AmbassadorProfile.objects.get(user=referral.referrer, is_active=True)
    except AmbassadorProfile.DoesNotExist:
        return

    # Calculer la commission
    commission = (transaction.amount * ambassador.commission_rate) / Decimal("100")

    with db_transaction.atomic():
        # Créditer l'ambassadeur
        ambassador.total_earnings += commission
        ambassador.total_conversions += 1
        ambassador.save(update_fields=["total_earnings", "total_conversions"])

        # Mettre à jour le referral
        if referral.status != ReferralProgram.Status.CONVERTED:
            referral.status = ReferralProgram.Status.CONVERTED
            referral.reward_amount += commission
            referral.save(update_fields=["status", "reward_amount"])

        # Mettre à jour le tier
        update_ambassador_tier(ambassador)

    # Notifier l'ambassadeur
    try:
        from notifications.services import send_notification
        send_notification(
            recipient=ambassador.user,
            notification_type="payment_confirmed",
            title="Commission gagnée",
            message=(
                f"Félicitations ! Vous avez gagné {commission:,.0f} FCFA de commission "
                f"sur la transaction {transaction.reference} de votre filleul "
                f"{buyer.get_full_name() or buyer.email}."
            ),
            data={
                "transaction_id": str(transaction.pk),
                "commission": str(commission),
                "reference": transaction.reference,
            },
        )
    except Exception as e:
        logger.error("Erreur notification commission ambassadeur : %s", e)

    logger.info(
        "Commission %s FCFA créditée à ambassadeur %s (TX: %s)",
        commission, ambassador.user.email, transaction.reference,
    )


def update_ambassador_tier(ambassador):
    """Recalcule le tier d'un ambassadeur selon ses conversions."""
    conversions = ambassador.total_conversions
    new_tier = AmbassadorProfile.Tier.BRONZE

    if conversions >= TIER_THRESHOLDS["platinum"]:
        new_tier = AmbassadorProfile.Tier.PLATINUM
    elif conversions >= TIER_THRESHOLDS["gold"]:
        new_tier = AmbassadorProfile.Tier.GOLD
    elif conversions >= TIER_THRESHOLDS["silver"]:
        new_tier = AmbassadorProfile.Tier.SILVER

    old_tier = ambassador.tier
    if new_tier != old_tier:
        ambassador.tier = new_tier
        ambassador.commission_rate = TIER_COMMISSION_RATES[new_tier]
        ambassador.save(update_fields=["tier", "commission_rate"])

        # Notifier la promotion
        try:
            from notifications.services import send_notification
            send_notification(
                recipient=ambassador.user,
                notification_type="system",
                title=f"Promotion au rang {ambassador.get_tier_display()}",
                message=(
                    f"Bravo ! Vous passez au rang {ambassador.get_tier_display()} "
                    f"avec un taux de commission de {ambassador.commission_rate}%. "
                    f"Continuez à parrainer pour atteindre le prochain niveau !"
                ),
            )
        except Exception as e:
            logger.error("Erreur notification promotion tier : %s", e)

        logger.info(
            "Ambassadeur %s promu : %s → %s",
            ambassador.user.email, old_tier, new_tier,
        )


def get_ambassador_stats(ambassador):
    """Retourne des statistiques détaillées pour un ambassadeur."""
    referrals = ReferralProgram.objects.filter(referrer=ambassador.user)

    stats = referrals.aggregate(
        total=Count("id"),
        pending=Count("id", filter=Q(status=ReferralProgram.Status.PENDING)),
        registered=Count("id", filter=Q(status=ReferralProgram.Status.REGISTERED)),
        converted=Count("id", filter=Q(status=ReferralProgram.Status.CONVERTED)),
        total_rewards=Sum("reward_amount"),
    )

    # Calcul du prochain tier
    conversions = ambassador.total_conversions
    next_tier = None
    conversions_needed = 0

    if ambassador.tier == AmbassadorProfile.Tier.BRONZE:
        next_tier = "Argent"
        conversions_needed = max(0, TIER_THRESHOLDS["silver"] - conversions)
    elif ambassador.tier == AmbassadorProfile.Tier.SILVER:
        next_tier = "Or"
        conversions_needed = max(0, TIER_THRESHOLDS["gold"] - conversions)
    elif ambassador.tier == AmbassadorProfile.Tier.GOLD:
        next_tier = "Platine"
        conversions_needed = max(0, TIER_THRESHOLDS["platinum"] - conversions)

    return {
        "referrals": stats,
        "total_earnings": ambassador.total_earnings,
        "commission_rate": ambassador.commission_rate,
        "tier": ambassador.get_tier_display(),
        "conversion_rate": ambassador.conversion_rate,
        "next_tier": next_tier,
        "conversions_needed": conversions_needed,
    }
