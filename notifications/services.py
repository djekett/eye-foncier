"""
Service de notifications — EYE-FONCIER
Dispatch unifié vers tous les canaux (in-app, email, SMS, WhatsApp, push).
"""
import json
import logging
from urllib.request import Request, urlopen
from urllib.error import URLError

from django.conf import settings
from django.core.mail import send_mail
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from .models import Notification, NotificationLog, NotificationPreference

logger = logging.getLogger(__name__)

# Détermine si Celery est disponible
_CELERY_AVAILABLE = False
try:
    from celery import current_app
    _CELERY_AVAILABLE = bool(current_app.conf.broker_url)
except Exception:
    pass


def send_notification(
    recipient,
    notification_type,
    title,
    message,
    data=None,
    channels=None,
    priority="normal",
):
    """
    Envoie une notification via les canaux activés de l'utilisateur.

    Args:
        recipient: User instance
        notification_type: str (voir Notification.NotificationType)
        title: str — titre court
        message: str — corps du message
        data: dict — données structurées (parcelle_id, transaction_id, etc.)
        channels: list[str] | None — forcer certains canaux, sinon utilise les préférences
        priority: str — low, normal, high, urgent

    Returns:
        list[Notification] — notifications créées
    """
    if data is None:
        data = {}

    prefs = _get_preferences(recipient)

    # Vérifier si ce type est désactivé
    if notification_type in (prefs.disabled_types or []):
        logger.info(
            "Notification type %s désactivé pour %s", notification_type, recipient
        )
        return []

    # Déterminer les canaux
    if channels is None:
        channels = []
        if prefs.inapp_enabled:
            channels.append(Notification.Channel.INAPP)
        if prefs.email_enabled:
            channels.append(Notification.Channel.EMAIL)
        if prefs.sms_enabled:
            channels.append(Notification.Channel.SMS)
        if prefs.whatsapp_enabled and prefs.whatsapp_consent and prefs.whatsapp_number:
            channels.append(Notification.Channel.WHATSAPP)
        if prefs.push_enabled:
            channels.append(Notification.Channel.PUSH)

    created = []
    for channel in channels:
        notif = Notification.objects.create(
            recipient=recipient,
            notification_type=notification_type,
            channel=channel,
            priority=priority,
            title=title,
            message=message,
            data=data,
        )

        # Dispatch selon le canal
        if channel == Notification.Channel.INAPP:
            notif.is_sent = True
            notif.sent_at = timezone.now()
            notif.save(update_fields=["is_sent", "sent_at"])

        elif channel == Notification.Channel.EMAIL:
            _dispatch_async_or_sync("email", notif)

        elif channel == Notification.Channel.SMS:
            if not _is_quiet_hours(prefs):
                _dispatch_async_or_sync("sms", notif)
            else:
                logger.info("SMS différé (heures calmes) pour %s", recipient)

        elif channel == Notification.Channel.WHATSAPP:
            if not _is_quiet_hours(prefs):
                _dispatch_async_or_sync("whatsapp", notif)
            else:
                logger.info("WhatsApp différé (heures calmes) pour %s", recipient)

        elif channel == Notification.Channel.PUSH:
            if not _is_quiet_hours(prefs):
                _dispatch_async_or_sync("push", notif)
            else:
                logger.info("Push différée (heures calmes) pour %s", recipient)

        created.append(notif)

    return created


def get_unread_count(user):
    """Nombre de notifications in-app non lues."""
    return Notification.objects.filter(
        recipient=user,
        channel=Notification.Channel.INAPP,
        is_read=False,
    ).count()


def mark_as_read(notification_id, user):
    """Marque une notification comme lue."""
    return Notification.objects.filter(
        pk=notification_id, recipient=user, is_read=False
    ).update(is_read=True, read_at=timezone.now())


def mark_all_read(user):
    """Marque toutes les notifications in-app comme lues."""
    return Notification.objects.filter(
        recipient=user,
        channel=Notification.Channel.INAPP,
        is_read=False,
    ).update(is_read=True, read_at=timezone.now())


# ──────────────────────────────────────────────
# Fonctions internes
# ──────────────────────────────────────────────


def _get_preferences(user):
    """Récupère ou crée les préférences de notification."""
    prefs, _ = NotificationPreference.objects.get_or_create(user=user)
    return prefs


def _is_quiet_hours(prefs):
    """Vérifie si on est dans les heures calmes."""
    if not prefs.quiet_hours_start or not prefs.quiet_hours_end:
        return False
    now = timezone.localtime().time()
    start = prefs.quiet_hours_start
    end = prefs.quiet_hours_end
    if start <= end:
        return start <= now <= end
    # Période qui chevauche minuit (ex: 22:00 → 07:00)
    return now >= start or now <= end


def _dispatch_async_or_sync(channel_type, notification):
    """
    Dispatch via Celery si disponible, sinon en synchrone.
    Permet un fonctionnement dégradé sans Celery.
    """
    use_celery = getattr(settings, "CELERY_ALWAYS_EAGER", False) or _CELERY_AVAILABLE

    if use_celery:
        try:
            from . import tasks
            task_map = {
                "email": tasks.send_email_notification,
                "sms": tasks.send_sms_notification,
                "whatsapp": tasks.send_whatsapp_notification,
            }
            task = task_map.get(channel_type)
            if task:
                task.delay(str(notification.pk))
                return
        except Exception:
            pass

    # Fallback synchrone
    dispatch_map = {
        "email": _dispatch_email,
        "sms": _dispatch_sms,
        "whatsapp": _dispatch_whatsapp,
        "push": _dispatch_push,
    }
    handler = dispatch_map.get(channel_type)
    if handler:
        handler(notification)


def _dispatch_email(notification):
    """Envoie une notification par email avec template dynamique."""
    try:
        context = {
            "title": notification.title,
            "message": notification.message,
            "data": notification.data or {},
            "recipient": notification.recipient,
            "notification_type": notification.notification_type,
            "priority": notification.priority,
        }

        # Template spécifique si défini dans data, sinon fallback
        template_name = (notification.data or {}).get("email_template")
        if template_name:
            try:
                html_message = render_to_string(template_name, context)
            except TemplateDoesNotExist:
                logger.warning("Template %s introuvable, fallback email_base", template_name)
                html_message = render_to_string("notifications/email_base.html", context)
        else:
            html_message = render_to_string("notifications/email_base.html", context)

        plain_message = strip_tags(notification.message)

        send_mail(
            subject=f"[EYE-FONCIER] {notification.title}",
            message=plain_message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@eye-foncier.com"),
            recipient_list=[notification.recipient.email],
            html_message=html_message,
            fail_silently=False,
        )
        notification.is_sent = True
        notification.sent_at = timezone.now()
        notification.save(update_fields=["is_sent", "sent_at"])

        NotificationLog.objects.create(
            notification=notification,
            status=NotificationLog.Status.SENT,
            channel=Notification.Channel.EMAIL,
            provider="smtp",
        )
        logger.info("Email envoyé à %s : %s", notification.recipient.email, notification.title)

    except Exception as e:
        notification.error_message = str(e)[:500]
        notification.retry_count += 1
        notification.save(update_fields=["error_message", "retry_count"])

        NotificationLog.objects.create(
            notification=notification,
            status=NotificationLog.Status.FAILED,
            channel=Notification.Channel.EMAIL,
            provider="smtp",
            error_detail=str(e),
        )
        logger.error("Échec envoi email à %s : %s", notification.recipient.email, e)


def _dispatch_sms(notification):
    """Envoie un SMS via InfoBip."""
    api_key = getattr(settings, "INFOBIP_API_KEY", "")
    base_url = getattr(settings, "INFOBIP_BASE_URL", "")
    sender = getattr(settings, "INFOBIP_SENDER", "EYE-FONCIER")

    phone = getattr(notification.recipient, "phone", "")
    if not phone:
        notification.error_message = "Pas de numéro de téléphone"
        notification.save(update_fields=["error_message"])
        NotificationLog.objects.create(
            notification=notification,
            status=NotificationLog.Status.FAILED,
            channel=Notification.Channel.SMS,
            error_detail="Pas de numéro de téléphone",
        )
        return

    if not api_key or not base_url:
        # Mode développement : log seulement
        sms_preview = _build_sms_body(notification)
        logger.info("[SMS SIMULATION] → %s : %s", phone, sms_preview[:100])
        notification.is_sent = True
        notification.sent_at = timezone.now()
        notification.error_message = "SMS simulé (pas de clé API)"
        notification.save(update_fields=["is_sent", "sent_at", "error_message"])
        NotificationLog.objects.create(
            notification=notification,
            status=NotificationLog.Status.SENT,
            channel=Notification.Channel.SMS,
            provider="infobip_simulation",
        )
        return

    sms_body = _build_sms_body(notification)

    try:
        payload = json.dumps({
            "messages": [
                {
                    "from": sender,
                    "destinations": [{"to": phone}],
                    "text": sms_body,
                }
            ]
        }).encode("utf-8")

        req = Request(
            f"{base_url}/sms/2/text/advanced",
            data=payload,
            headers={
                "Authorization": f"App {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        urlopen(req, timeout=15)
        notification.is_sent = True
        notification.sent_at = timezone.now()
        notification.save(update_fields=["is_sent", "sent_at"])

        NotificationLog.objects.create(
            notification=notification,
            status=NotificationLog.Status.SENT,
            channel=Notification.Channel.SMS,
            provider="infobip",
        )
        logger.info("SMS envoyé à %s", phone)

    except (URLError, Exception) as e:
        notification.error_message = str(e)[:500]
        notification.retry_count += 1
        notification.save(update_fields=["error_message", "retry_count"])

        NotificationLog.objects.create(
            notification=notification,
            status=NotificationLog.Status.FAILED,
            channel=Notification.Channel.SMS,
            provider="infobip",
            error_detail=str(e),
        )
        logger.error("Échec envoi SMS à %s : %s", phone, e)


def _build_sms_body(notification):
    """Construit un corps SMS enrichi depuis les données contextuelles (≤300 chars)."""
    data = notification.data or {}
    parts = [f"[EYE-FONCIER] {notification.title}"]

    ref = data.get("reference")
    amount = data.get("amount")
    parcelle_lot = data.get("parcelle_lot")
    operation = data.get("operation_label")

    if ref:
        parts.append(f"Ref: {ref}")
    if parcelle_lot:
        parts.append(f"Lot {parcelle_lot}")
    if amount:
        parts.append(f"Montant: {amount} FCFA")
    if operation:
        parts.append(f"Op: {operation}")

    header = " | ".join(parts)
    remaining = 300 - len(header) - 1
    if remaining > 20:
        msg_part = notification.message[:remaining]
        return f"{header}\n{msg_part}"
    return header[:300]


def _dispatch_whatsapp(notification):
    """Envoie un message WhatsApp via Twilio."""
    from .whatsapp_service import send_whatsapp
    send_whatsapp(notification)


def _dispatch_push(notification):
    """Envoie une notification push via Firebase Cloud Messaging."""
    try:
        from .push_service import send_push_to_user

        success = send_push_to_user(
            user=notification.recipient,
            title=notification.title,
            message=notification.message,
            data=notification.data,
        )

        if success:
            notification.is_sent = True
            notification.sent_at = timezone.now()
            notification.save(update_fields=["is_sent", "sent_at"])
            NotificationLog.objects.create(
                notification=notification,
                status=NotificationLog.Status.SENT,
                channel=Notification.Channel.PUSH,
                provider="fcm",
            )
        else:
            notification.error_message = "Push non envoyée (pas de token ou échec)"
            notification.save(update_fields=["error_message"])
            NotificationLog.objects.create(
                notification=notification,
                status=NotificationLog.Status.FAILED,
                channel=Notification.Channel.PUSH,
                provider="fcm",
                error_detail="Pas de token ou échec",
            )

    except Exception as e:
        notification.error_message = str(e)[:500]
        notification.retry_count += 1
        notification.save(update_fields=["error_message", "retry_count"])

        NotificationLog.objects.create(
            notification=notification,
            status=NotificationLog.Status.FAILED,
            channel=Notification.Channel.PUSH,
            provider="fcm",
            error_detail=str(e),
        )
        logger.error("Échec envoi push à %s : %s", notification.recipient.email, e)
