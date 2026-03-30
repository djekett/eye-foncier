"""
Signaux Analysis — EYE-FONCIER
Auto-trigger du matching quand une parcelle ou un profil acheteur est modifié.
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger("analysis")


@receiver(post_save, sender="parcelles.Parcelle")
def trigger_matching_on_parcelle_save(sender, instance, created, **kwargs):
    """Recalcule les scores de matching quand une parcelle est créée ou devient disponible."""
    if not instance.is_validated:
        return

    if instance.status != "disponible":
        return

    try:
        from .services.matching_engine import compute_match_for_parcelle

        scores = compute_match_for_parcelle(instance)
        logger.info(
            "Matching recalculé pour parcelle %s : %d scores",
            instance.lot_number, len(scores),
        )
    except Exception as e:
        logger.error("Erreur matching auto parcelle %s : %s", instance.lot_number, e)


@receiver(post_save, sender="analysis.BuyerProfile")
def trigger_matching_on_buyer_profile_save(sender, instance, **kwargs):
    """Recalcule les scores quand un profil acheteur est mis à jour."""
    if not instance.is_active:
        return

    try:
        from .services.matching_engine import compute_match_for_buyer

        scores = compute_match_for_buyer(instance)
        logger.info(
            "Matching recalculé pour acheteur %s : %d scores",
            instance.user.email, len(scores),
        )
    except Exception as e:
        logger.error("Erreur matching auto acheteur %s : %s", instance.user.email, e)
