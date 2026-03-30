"""
Tâches Celery — Notifications EYE-FONCIER
Envoi asynchrone des notifications via tous les canaux.
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)

# Retry : 3 tentatives avec backoff exponentiel (30s, 60s, 120s)
RETRY_KWARGS = {
    "max_retries": 3,
    "default_retry_delay": 30,
    "retry_backoff": True,
    "retry_backoff_max": 300,
}


@shared_task(bind=True, ignore_result=True, **RETRY_KWARGS)
def send_notification_async(self, recipient_id, notification_type, title, message,
                            data=None, channels=None, priority="normal"):
    """
    Tâche principale : envoie une notification via les canaux activés.
    Appelée en asynchrone depuis les signaux et services.
    """
    try:
        from .services import send_notification
        from django.contrib.auth import get_user_model

        User = get_user_model()
        recipient = User.objects.get(pk=recipient_id)

        send_notification(
            recipient=recipient,
            notification_type=notification_type,
            title=title,
            message=message,
            data=data,
            channels=channels,
            priority=priority,
        )

    except Exception as exc:
        logger.error("Échec tâche notification pour %s : %s", recipient_id, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, ignore_result=True, **RETRY_KWARGS)
def send_email_notification(self, notification_id):
    """Envoie un email pour une notification existante."""
    try:
        from .models import Notification
        from .services import _dispatch_email

        notification = Notification.objects.get(pk=notification_id)
        _dispatch_email(notification)

    except Exception as exc:
        logger.error("Échec envoi email pour notification %s : %s", notification_id, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, ignore_result=True, **RETRY_KWARGS)
def send_whatsapp_notification(self, notification_id):
    """Envoie un message WhatsApp pour une notification existante."""
    try:
        from .models import Notification
        from .whatsapp_service import send_whatsapp

        notification = Notification.objects.get(pk=notification_id)
        success = send_whatsapp(notification)
        if not success and notification.retry_count < 3:
            raise Exception("WhatsApp non envoyé, retry programmé")

    except Exception as exc:
        logger.error("Échec envoi WhatsApp pour notification %s : %s", notification_id, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, ignore_result=True, **RETRY_KWARGS)
def send_sms_notification(self, notification_id):
    """Envoie un SMS pour une notification existante."""
    try:
        from .models import Notification
        from .services import _dispatch_sms

        notification = Notification.objects.get(pk=notification_id)
        _dispatch_sms(notification)

    except Exception as exc:
        logger.error("Échec envoi SMS pour notification %s : %s", notification_id, exc)
        raise self.retry(exc=exc)


@shared_task(ignore_result=True)
def send_welcome_notification(user_id):
    """Envoie les notifications de bienvenue à un nouvel utilisateur."""
    try:
        from django.contrib.auth import get_user_model
        from .services import send_notification

        User = get_user_model()
        user = User.objects.get(pk=user_id)
        user_name = user.first_name or user.email.split("@")[0]

        send_notification(
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

    except Exception as exc:
        logger.error("Échec notification bienvenue pour %s : %s", user_id, exc)


@shared_task(ignore_result=True)
def retry_failed_notifications():
    """
    Tâche périodique : retente les notifications échouées.
    Exécutée toutes les 5 minutes via Celery Beat.
    """
    from .models import Notification

    failed = Notification.objects.filter(
        is_sent=False,
        retry_count__lt=3,
        error_message__gt="",
    ).exclude(
        channel=Notification.Channel.INAPP,
    ).order_by("created_at")[:50]

    for notif in failed:
        channel = notif.channel
        if channel == Notification.Channel.EMAIL:
            send_email_notification.delay(str(notif.pk))
        elif channel == Notification.Channel.WHATSAPP:
            send_whatsapp_notification.delay(str(notif.pk))
        elif channel == Notification.Channel.SMS:
            send_sms_notification.delay(str(notif.pk))

    if failed:
        logger.info("Retry programmé pour %d notifications échouées", len(failed))


@shared_task(ignore_result=True)
def cleanup_old_notifications():
    """
    Tâche périodique : supprime les notifications lues de plus de 90 jours.
    Exécutée une fois par jour via Celery Beat.
    """
    from datetime import timedelta
    from django.utils import timezone
    from .models import Notification

    cutoff = timezone.now() - timedelta(days=90)
    deleted_count, _ = Notification.objects.filter(
        is_read=True,
        created_at__lt=cutoff,
    ).delete()

    if deleted_count:
        logger.info("Nettoyage : %d anciennes notifications supprimées", deleted_count)


@shared_task(ignore_result=True)
def cleanup_old_logs():
    """Supprime les logs de notification de plus de 180 jours."""
    from datetime import timedelta
    from django.utils import timezone
    from .models import NotificationLog

    cutoff = timezone.now() - timedelta(days=180)
    deleted_count, _ = NotificationLog.objects.filter(
        created_at__lt=cutoff,
    ).delete()

    if deleted_count:
        logger.info("Nettoyage : %d anciens logs supprimés", deleted_count)
