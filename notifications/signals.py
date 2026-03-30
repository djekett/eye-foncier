"""
Signaux Notifications — EYE-FONCIER
Auto-création des préférences et déclenchement des notifications
sur les événements principaux de la plateforme.
"""
import logging

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import NotificationPreference

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Préférences automatiques à l'inscription
# ──────────────────────────────────────────────

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_notification_preferences(sender, instance, created, **kwargs):
    """Crée les préférences de notification et envoie le mail de bienvenue."""
    if created:
        NotificationPreference.objects.get_or_create(user=instance)
        # Notification de bienvenue (asynchrone si Celery dispo)
        try:
            from .tasks import send_welcome_notification
            send_welcome_notification.delay(str(instance.pk))
        except Exception:
            # Fallback synchrone
            _send_welcome_sync(instance)


# ──────────────────────────────────────────────
# Parcelle : publiée, validée, rejetée
# ──────────────────────────────────────────────

@receiver(post_save, sender="parcelles.Parcelle")
def notify_on_parcelle_change(sender, instance, created, **kwargs):
    """Notifie lors de la publication ou validation/rejet d'une parcelle."""
    if created:
        _notify_parcelle_published(instance)
    else:
        _check_parcelle_validation(instance)


# ──────────────────────────────────────────────
# Réactions sur les parcelles
# ──────────────────────────────────────────────

@receiver(post_save, sender="parcelles.ParcelleReaction")
def notify_on_parcelle_reaction(sender, instance, created, **kwargs):
    """Notifie le propriétaire quand quelqu'un réagit à sa parcelle."""
    if not created:
        return

    parcelle = instance.parcelle
    owner = parcelle.owner

    # Ne pas notifier si l'utilisateur réagit à sa propre parcelle
    if instance.user == owner:
        return

    user_name = instance.user.get_full_name() or instance.user.email
    reaction_label = instance.get_reaction_type_display()

    if instance.reaction_type == "interested":
        notification_type = "parcelle_interest"
        title = f"Nouvel intérêt pour {parcelle.lot_number}"
        message = (
            f"{user_name} est intéressé(e) par votre parcelle {parcelle.lot_number} "
            f"({parcelle.title})."
        )
        priority = "high"
    else:
        notification_type = "new_review"
        title = f"Nouvelle réaction sur {parcelle.lot_number}"
        message = (
            f"{user_name} a réagi ({reaction_label}) à votre parcelle "
            f"{parcelle.lot_number}."
        )
        priority = "normal"

    _send_notification_safe(
        recipient=owner,
        notification_type=notification_type,
        title=title,
        message=message,
        data={
            "parcelle_id": str(parcelle.pk),
            "parcelle_lot": parcelle.lot_number,
            "user_name": user_name,
            "reaction_type": instance.reaction_type,
            "action_url": f"/parcelles/{parcelle.pk}/",
        },
        priority=priority,
    )


# ──────────────────────────────────────────────
# KYC / Profil
# ──────────────────────────────────────────────

@receiver(post_save, sender="accounts.Profile")
def notify_on_kyc_update(sender, instance, **kwargs):
    """Notifie l'utilisateur sur les changements de statut KYC."""
    if not hasattr(instance, '_kyc_status_changed'):
        return

    user = instance.user
    status = instance.kyc_status

    status_messages = {
        "submitted": (
            "Vérification KYC en cours",
            "Vos documents de vérification ont été soumis et sont en cours d'examen.",
        ),
        "verified": (
            "Compte vérifié !",
            "Félicitations ! Votre vérification KYC a été approuvée. "
            "Vous avez maintenant accès à toutes les fonctionnalités.",
        ),
        "rejected": (
            "Vérification KYC rejetée",
            "Votre vérification KYC a été rejetée. "
            "Veuillez soumettre de nouveaux documents conformes.",
        ),
    }

    if status in status_messages:
        title, message = status_messages[status]
        _send_notification_safe(
            recipient=user,
            notification_type="kyc_update",
            title=title,
            message=message,
            data={
                "kyc_status": status,
                "action_url": "/compte/verification/",
                "email_template": "notifications/email/kyc_update.html",
            },
            priority="high" if status == "verified" else "normal",
        )


# ──────────────────────────────────────────────
# Fonctions internes
# ──────────────────────────────────────────────

def _notify_parcelle_published(parcelle):
    """Notifie le propriétaire que sa parcelle est publiée."""
    _send_notification_safe(
        recipient=parcelle.owner,
        notification_type="parcelle_published",
        title=f"Parcelle {parcelle.lot_number} publiée",
        message=(
            f"Votre parcelle {parcelle.lot_number} ({parcelle.title}) a été publiée "
            f"avec succès sur EYE-FONCIER. Elle est maintenant visible par les acheteurs."
        ),
        data={
            "parcelle_id": str(parcelle.pk),
            "parcelle_lot": parcelle.lot_number,
            "parcelle_title": parcelle.title,
            "surface": str(parcelle.surface_m2),
            "price": str(parcelle.price),
            "action_url": f"/parcelles/{parcelle.pk}/",
            "email_template": "notifications/email/parcelle_published.html",
        },
    )


def _check_parcelle_validation(parcelle):
    """Vérifie si la parcelle vient d'être validée ou rejetée."""
    if parcelle.is_validated and parcelle.validated_by:
        _send_notification_safe(
            recipient=parcelle.owner,
            notification_type="parcelle_validated",
            title=f"Parcelle {parcelle.lot_number} validée",
            message=(
                f"Votre parcelle {parcelle.lot_number} a été validée par un géomètre. "
                f"Elle bénéficie maintenant d'un badge de confiance supplémentaire."
            ),
            data={
                "parcelle_id": str(parcelle.pk),
                "parcelle_lot": parcelle.lot_number,
                "validated_by": parcelle.validated_by.get_full_name(),
                "action_url": f"/parcelles/{parcelle.pk}/",
                "email_template": "notifications/email/parcelle_validated.html",
            },
            priority="high",
        )


def _send_notification_safe(recipient, notification_type, title, message,
                            data=None, priority="normal"):
    """Envoie une notification de manière sécurisée (try/except)."""
    try:
        from .services import send_notification
        send_notification(
            recipient=recipient,
            notification_type=notification_type,
            title=title,
            message=message,
            data=data,
            priority=priority,
        )
    except Exception as e:
        logger.error(
            "Erreur notification %s pour %s : %s",
            notification_type, recipient, e,
        )


def _send_welcome_sync(user):
    """Envoie la notification de bienvenue en mode synchrone."""
    user_name = user.first_name or user.email.split("@")[0]
    _send_notification_safe(
        recipient=user,
        notification_type="welcome",
        title="Bienvenue sur EYE-FONCIER !",
        message=(
            f"Bonjour {user_name}, votre compte a été créé avec succès. "
            "Explorez notre plateforme pour découvrir des parcelles de qualité "
            "et gérer vos transactions foncières en toute sécurité."
        ),
        data={
            "action_url": "/compte/dashboard/",
            "email_template": "notifications/email/welcome.html",
        },
    )
