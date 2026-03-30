"""
Service WhatsApp — EYE-FONCIER
Envoi de messages WhatsApp via l'API Twilio.
"""
import logging

from django.conf import settings

from .models import Notification, NotificationLog, NotificationPreference

logger = logging.getLogger(__name__)

PLATFORM_URL = getattr(settings, "PLATFORM_URL", "https://eye-foncier.com")


def send_whatsapp(notification):
    """
    Envoie un message WhatsApp pour une notification donnée.
    Utilise Twilio WhatsApp API.

    Returns:
        bool — True si envoyé avec succès.
    """
    prefs = _get_whatsapp_prefs(notification.recipient)
    if not prefs:
        _log_failure(notification, "Pas de préférences WhatsApp ou consentement manquant")
        return False

    whatsapp_number = prefs.whatsapp_number
    if not whatsapp_number:
        _log_failure(notification, "Pas de numéro WhatsApp configuré")
        return False

    account_sid = getattr(settings, "TWILIO_ACCOUNT_SID", "")
    auth_token = getattr(settings, "TWILIO_AUTH_TOKEN", "")
    from_number = getattr(settings, "TWILIO_WHATSAPP_FROM", "")

    if not account_sid or not auth_token or not from_number:
        return _simulate_whatsapp(notification, whatsapp_number)

    body = _build_whatsapp_body(notification)
    to_number = f"whatsapp:{whatsapp_number}"
    from_whatsapp = f"whatsapp:{from_number}"

    try:
        from twilio.rest import Client

        client = Client(account_sid, auth_token)
        message = client.messages.create(
            body=body,
            from_=from_whatsapp,
            to=to_number,
        )

        notification.is_sent = True
        from django.utils import timezone
        notification.sent_at = timezone.now()
        notification.save(update_fields=["is_sent", "sent_at"])

        NotificationLog.objects.create(
            notification=notification,
            status=NotificationLog.Status.SENT,
            channel=Notification.Channel.WHATSAPP,
            provider="twilio",
            provider_message_id=message.sid,
        )
        logger.info("WhatsApp envoyé à %s (SID: %s)", whatsapp_number, message.sid)
        return True

    except Exception as e:
        notification.error_message = str(e)[:500]
        notification.retry_count += 1
        notification.save(update_fields=["error_message", "retry_count"])

        NotificationLog.objects.create(
            notification=notification,
            status=NotificationLog.Status.FAILED,
            channel=Notification.Channel.WHATSAPP,
            provider="twilio",
            error_detail=str(e),
        )
        logger.error("Échec envoi WhatsApp à %s : %s", whatsapp_number, e)
        return False


def send_whatsapp_template(notification, template_name, template_params=None):
    """
    Envoie un message WhatsApp basé sur un template approuvé par Meta.
    Les templates sont nécessaires pour les messages initiés par l'entreprise.

    Args:
        notification: Notification instance
        template_name: str — nom du template approuvé (ex: "parcelle_publiee")
        template_params: list — paramètres du template
    """
    prefs = _get_whatsapp_prefs(notification.recipient)
    if not prefs:
        return False

    whatsapp_number = prefs.whatsapp_number
    account_sid = getattr(settings, "TWILIO_ACCOUNT_SID", "")
    auth_token = getattr(settings, "TWILIO_AUTH_TOKEN", "")
    from_number = getattr(settings, "TWILIO_WHATSAPP_FROM", "")
    content_sid = getattr(settings, "TWILIO_CONTENT_SIDS", {}).get(template_name)

    if not all([account_sid, auth_token, from_number, content_sid]):
        return _simulate_whatsapp(notification, whatsapp_number)

    try:
        from twilio.rest import Client

        client = Client(account_sid, auth_token)

        message_kwargs = {
            "from_": f"whatsapp:{from_number}",
            "to": f"whatsapp:{whatsapp_number}",
            "content_sid": content_sid,
        }
        if template_params:
            message_kwargs["content_variables"] = str(template_params)

        message = client.messages.create(**message_kwargs)

        notification.is_sent = True
        from django.utils import timezone
        notification.sent_at = timezone.now()
        notification.save(update_fields=["is_sent", "sent_at"])

        NotificationLog.objects.create(
            notification=notification,
            status=NotificationLog.Status.SENT,
            channel=Notification.Channel.WHATSAPP,
            provider="twilio",
            provider_message_id=message.sid,
            response_data={"template": template_name},
        )
        return True

    except Exception as e:
        notification.error_message = str(e)[:500]
        notification.retry_count += 1
        notification.save(update_fields=["error_message", "retry_count"])

        NotificationLog.objects.create(
            notification=notification,
            status=NotificationLog.Status.FAILED,
            channel=Notification.Channel.WHATSAPP,
            provider="twilio",
            error_detail=str(e),
        )
        logger.error("Échec envoi template WhatsApp à %s : %s", whatsapp_number, e)
        return False


def verify_whatsapp_number(user, number):
    """
    Initie la vérification d'un numéro WhatsApp via Twilio Verify.

    Returns:
        str — verification SID ou None en cas d'erreur.
    """
    account_sid = getattr(settings, "TWILIO_ACCOUNT_SID", "")
    auth_token = getattr(settings, "TWILIO_AUTH_TOKEN", "")
    verify_sid = getattr(settings, "TWILIO_VERIFY_SERVICE_SID", "")

    if not all([account_sid, auth_token, verify_sid]):
        logger.info("[SIMULATION] Vérification WhatsApp pour %s : %s", user.email, number)
        return "SIMULATED_VERIFICATION"

    try:
        from twilio.rest import Client

        client = Client(account_sid, auth_token)
        verification = client.verify.v2.services(verify_sid).verifications.create(
            to=number,
            channel="whatsapp",
        )
        logger.info("Vérification WhatsApp initiée pour %s (SID: %s)", user.email, verification.sid)
        return verification.sid

    except Exception as e:
        logger.error("Échec vérification WhatsApp pour %s : %s", user.email, e)
        return None


def confirm_whatsapp_verification(user, number, code):
    """
    Confirme le code de vérification WhatsApp.

    Returns:
        bool — True si le code est valide.
    """
    account_sid = getattr(settings, "TWILIO_ACCOUNT_SID", "")
    auth_token = getattr(settings, "TWILIO_AUTH_TOKEN", "")
    verify_sid = getattr(settings, "TWILIO_VERIFY_SERVICE_SID", "")

    if not all([account_sid, auth_token, verify_sid]):
        # Mode simulation : accepte le code "000000"
        if code == "000000":
            _mark_whatsapp_verified(user, number)
            return True
        return False

    try:
        from twilio.rest import Client

        client = Client(account_sid, auth_token)
        check = client.verify.v2.services(verify_sid).verification_checks.create(
            to=number,
            code=code,
        )
        if check.status == "approved":
            _mark_whatsapp_verified(user, number)
            return True
        return False

    except Exception as e:
        logger.error("Échec confirmation WhatsApp pour %s : %s", user.email, e)
        return False


# ──────────────────────────────────────────────
# Fonctions internes
# ──────────────────────────────────────────────


def _get_whatsapp_prefs(user):
    """Récupère les préférences WhatsApp si le consentement est donné."""
    try:
        prefs = NotificationPreference.objects.get(user=user)
        if prefs.whatsapp_enabled and prefs.whatsapp_consent:
            return prefs
    except NotificationPreference.DoesNotExist:
        pass
    return None


def _mark_whatsapp_verified(user, number):
    """Marque le numéro WhatsApp comme vérifié."""
    prefs, _ = NotificationPreference.objects.get_or_create(user=user)
    prefs.whatsapp_number = number
    prefs.whatsapp_verified = True
    prefs.whatsapp_consent = True
    prefs.whatsapp_enabled = True
    prefs.save(update_fields=[
        "whatsapp_number", "whatsapp_verified",
        "whatsapp_consent", "whatsapp_enabled",
    ])


def _build_whatsapp_body(notification):
    """Construit le corps du message WhatsApp (court et professionnel)."""
    data = notification.data or {}
    parts = [f"*EYE-FONCIER*\n\n{notification.title}"]

    # Infos contextuelles
    ref = data.get("reference")
    parcelle_lot = data.get("parcelle_lot")
    amount = data.get("amount")

    if parcelle_lot:
        parts.append(f"Parcelle : Lot {parcelle_lot}")
    if ref:
        parts.append(f"Réf : {ref}")
    if amount:
        parts.append(f"Montant : {amount:,} FCFA".replace(",", " ") if isinstance(amount, (int, float)) else f"Montant : {amount} FCFA")

    # Message principal (tronqué)
    msg = notification.message[:200]
    parts.append(f"\n{msg}")

    # Lien vers la plateforme
    action_url = data.get("action_url", "")
    if action_url:
        full_url = f"{PLATFORM_URL}{action_url}" if action_url.startswith("/") else action_url
        parts.append(f"\nVoir : {full_url}")
    else:
        parts.append(f"\n{PLATFORM_URL}")

    return "\n".join(parts)


def _simulate_whatsapp(notification, whatsapp_number):
    """Simule l'envoi en mode développement."""
    body = _build_whatsapp_body(notification)
    logger.info("[WHATSAPP SIMULATION] → %s :\n%s", whatsapp_number, body[:300])

    from django.utils import timezone
    notification.is_sent = True
    notification.sent_at = timezone.now()
    notification.error_message = "WhatsApp simulé (pas de clés API Twilio)"
    notification.save(update_fields=["is_sent", "sent_at", "error_message"])

    NotificationLog.objects.create(
        notification=notification,
        status=NotificationLog.Status.SENT,
        channel=Notification.Channel.WHATSAPP,
        provider="twilio_simulation",
    )
    return True


def _log_failure(notification, reason):
    """Log un échec d'envoi WhatsApp."""
    notification.error_message = reason
    notification.save(update_fields=["error_message"])
    NotificationLog.objects.create(
        notification=notification,
        status=NotificationLog.Status.FAILED,
        channel=Notification.Channel.WHATSAPP,
        error_detail=reason,
    )
    logger.warning("WhatsApp non envoyé à %s : %s", notification.recipient, reason)
