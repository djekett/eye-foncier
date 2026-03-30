"""
Service Push Notifications — EYE-FONCIER
Intégration Firebase Cloud Messaging (FCM) pour les notifications push.
"""
import json
import logging
from urllib.request import Request, urlopen
from urllib.error import URLError

from django.conf import settings

logger = logging.getLogger(__name__)


def send_push_notification(fcm_token, title, message, data=None):
    """
    Envoie une notification push via Firebase Cloud Messaging (HTTP v1 API).

    Args:
        fcm_token: str — Token FCM du device
        title: str — Titre de la notification
        message: str — Corps du message
        data: dict — Données supplémentaires (deep linking, etc.)

    Returns:
        bool — True si envoyé avec succès
    """
    server_key = getattr(settings, "FCM_SERVER_KEY", "")

    if not server_key:
        logger.info("[PUSH SIMULATION] → %s : %s — %s", fcm_token[:20], title, message[:80])
        return True

    if not fcm_token:
        logger.warning("Pas de token FCM, notification push ignorée")
        return False

    payload = {
        "to": fcm_token,
        "notification": {
            "title": title,
            "body": message[:500],
            "icon": "/static/images/logo-icon.png",
            "click_action": data.get("action_url", "/") if data else "/",
        },
    }

    if data:
        # Convertir toutes les valeurs en string (requis par FCM)
        payload["data"] = {k: str(v) for k, v in data.items()}

    try:
        req = Request(
            "https://fcm.googleapis.com/fcm/send",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"key={server_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        response = urlopen(req, timeout=10)
        result = json.loads(response.read().decode("utf-8"))

        if result.get("success", 0) > 0:
            logger.info("Push envoyée à %s : %s", fcm_token[:20], title)
            return True
        else:
            logger.warning("Push échouée : %s", result)
            return False

    except (URLError, Exception) as e:
        logger.error("Erreur envoi push : %s", e)
        return False


def send_push_to_user(user, title, message, data=None):
    """
    Envoie une notification push à un utilisateur via son token FCM enregistré.

    Returns:
        bool — True si envoyé avec succès
    """
    try:
        prefs = user.notification_preferences
    except Exception:
        logger.info("Pas de préférences de notification pour %s", user)
        return False

    fcm_token = getattr(prefs, "fcm_token", None)
    if not fcm_token:
        logger.info("Pas de token FCM pour %s", user)
        return False

    return send_push_notification(fcm_token, title, message, data)
