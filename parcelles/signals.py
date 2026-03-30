"""Signals pour invalider le cache GeoJSON lors des modifications de parcelles."""
import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache

logger = logging.getLogger("parcelles")


def invalidate_geojson_cache():
    """Invalide tout le cache GeoJSON en incrémentant le compteur de version."""
    try:
        version = cache.get("geojson_version", 0)
        cache.set("geojson_version", version + 1, 3600)
        logger.info("Cache GeoJSON invalidé (version → %d)", version + 1)
    except Exception as e:
        logger.warning("Erreur invalidation cache GeoJSON: %s", e)


@receiver(post_save, sender="parcelles.Parcelle")
def parcelle_post_save(sender, instance, created, **kwargs):
    """Invalide le cache GeoJSON après création ou modification d'une parcelle."""
    action = "créée" if created else "modifiée"
    logger.info("Parcelle %s %s — invalidation cache", instance.pk, action)
    invalidate_geojson_cache()


@receiver(post_delete, sender="parcelles.Parcelle")
def parcelle_post_delete(sender, instance, **kwargs):
    """Invalide le cache GeoJSON après suppression d'une parcelle."""
    logger.info("Parcelle %s supprimée — invalidation cache", instance.pk)
    invalidate_geojson_cache()
