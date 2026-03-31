"""
Service de paiement — EYE-FONCIER.
Intégration CinetPay pour les paiements Mobile Money et Carte bancaire.

CinetPay est la passerelle de paiement de référence en Afrique de l'Ouest.
Supporte : MTN Mobile Money, Orange Money, Moov Money, Wave, Visa, Mastercard.

Configuration requise dans .env :
    CINETPAY_API_KEY=votre_cle_api
    CINETPAY_SITE_ID=votre_site_id
    CINETPAY_SECRET_KEY=votre_cle_secrete
    CINETPAY_MODE=PROD  # ou TEST
"""

import uuid
import json
import logging
import hashlib
import requests
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("payments")

# ── Configuration CinetPay ──
CINETPAY_API_KEY = getattr(settings, "CINETPAY_API_KEY", "")
CINETPAY_SITE_ID = getattr(settings, "CINETPAY_SITE_ID", "")
CINETPAY_SECRET_KEY = getattr(settings, "CINETPAY_SECRET_KEY", "")
CINETPAY_MODE = getattr(settings, "CINETPAY_MODE", "TEST")

BASE_URL = "https://api-checkout.cinetpay.com/v2"
NOTIFY_URL = getattr(settings, "CINETPAY_NOTIFY_URL", "")
RETURN_URL = getattr(settings, "CINETPAY_RETURN_URL", "")


class PaymentError(Exception):
    """Erreur de paiement."""
    pass


def generate_transaction_id():
    """Génère un ID de transaction unique."""
    return "EF-" + str(uuid.uuid4().hex[:12]).upper()


def initiate_payment(
    amount,
    description,
    customer_name="",
    customer_email="",
    customer_phone="",
    payment_type="promotion",
    metadata=None,
    return_url=None,
    notify_url=None,
):
    """Initie un paiement via CinetPay.

    Args:
        amount: Montant en FCFA (entier)
        description: Description du paiement
        customer_name: Nom du client
        customer_email: Email du client
        customer_phone: Téléphone du client (ex: +2250700000000)
        payment_type: Type (promotion, escrow, transaction, visite)
        metadata: Dict de données supplémentaires
        return_url: URL de retour après paiement
        notify_url: URL de notification (webhook)

    Returns:
        dict: {
            'transaction_id': str,
            'payment_url': str,
            'token': str,
        }
    """
    transaction_id = generate_transaction_id()
    amount_int = int(Decimal(str(amount)))

    if amount_int < 100:
        raise PaymentError("Le montant minimum est de 100 FCFA.")

    if not CINETPAY_API_KEY or not CINETPAY_SITE_ID:
        # Mode test / démo — simuler un paiement
        logger.warning("CinetPay non configuré — mode simulation activé")
        return {
            "transaction_id": transaction_id,
            "payment_url": "/paiement/simulation/{}/".format(transaction_id),
            "token": "DEMO-" + transaction_id,
            "mode": "simulation",
            "amount": amount_int,
        }

    payload = {
        "apikey": CINETPAY_API_KEY,
        "site_id": CINETPAY_SITE_ID,
        "transaction_id": transaction_id,
        "amount": amount_int,
        "currency": "XOF",
        "description": description[:255],
        "return_url": return_url or RETURN_URL,
        "notify_url": notify_url or NOTIFY_URL,
        "channels": "ALL",
        "lang": "fr",
        "metadata": json.dumps(metadata or {}),
        # Informations client
        "customer_name": customer_name[:100] if customer_name else "",
        "customer_email": customer_email[:100] if customer_email else "",
        "customer_phone_number": customer_phone[:20] if customer_phone else "",
        "customer_address": "Côte d'Ivoire",
        "customer_city": "Abidjan",
        "customer_country": "CI",
    }

    try:
        response = requests.post(
            BASE_URL + "/payment",
            json=payload,
            timeout=30,
            headers={"Content-Type": "application/json"},
        )
        data = response.json()

        if data.get("code") == "201":
            return {
                "transaction_id": transaction_id,
                "payment_url": data["data"]["payment_url"],
                "token": data["data"].get("payment_token", ""),
                "mode": CINETPAY_MODE,
                "amount": amount_int,
            }
        else:
            error_msg = data.get("message", "Erreur inconnue CinetPay")
            logger.error("CinetPay initiation error: %s", data)
            raise PaymentError(error_msg)

    except requests.Timeout:
        logger.error("CinetPay timeout after 30s for amount=%s", amount_int)
        raise PaymentError("Le service de paiement ne repond pas. Veuillez reessayer.")
    except requests.ConnectionError:
        logger.error("CinetPay connection failed")
        raise PaymentError("Impossible de se connecter au service de paiement. Verifiez votre connexion.")
    except requests.RequestException as e:
        logger.error("CinetPay network error: %s", e)
        raise PaymentError("Erreur reseau. Veuillez reessayer.")
    except json.JSONDecodeError:
        logger.error("CinetPay returned invalid JSON response")
        raise PaymentError("Erreur du service de paiement. Veuillez contacter le support.")
    except PaymentError:
        raise
    except Exception as e:
        logger.error("CinetPay unexpected error: %s", e, exc_info=True)
        raise PaymentError("Erreur inattendue lors de l'initiation du paiement.")


def verify_payment(transaction_id):
    """Vérifie le statut d'un paiement auprès de CinetPay.

    Returns:
        dict: {
            'status': 'success' | 'pending' | 'failed',
            'amount': int,
            'payment_method': str,
            'operator': str,
            'payment_date': str,
            'metadata': dict,
        }
    """
    if not CINETPAY_API_KEY or not CINETPAY_SITE_ID:
        # Mode simulation
        return {
            "status": "success",
            "amount": 0,
            "payment_method": "simulation",
            "operator": "DEMO",
            "payment_date": timezone.now().isoformat(),
            "metadata": {},
        }

    payload = {
        "apikey": CINETPAY_API_KEY,
        "site_id": CINETPAY_SITE_ID,
        "transaction_id": transaction_id,
    }

    try:
        response = requests.post(
            BASE_URL + "/payment/check",
            json=payload,
            timeout=30,
        )
        data = response.json()

        if data.get("code") == "00":
            tx_data = data.get("data", {})
            status_code = tx_data.get("status", "")

            if status_code == "ACCEPTED":
                status = "success"
            elif status_code in ("PENDING", "PROCESSING"):
                status = "pending"
            else:
                status = "failed"

            return {
                "status": status,
                "amount": int(tx_data.get("amount", 0)),
                "payment_method": tx_data.get("payment_method", ""),
                "operator": tx_data.get("operator_id", ""),
                "payment_date": tx_data.get("payment_date", ""),
                "metadata": json.loads(tx_data.get("metadata", "{}")),
            }
        else:
            return {
                "status": "failed",
                "amount": 0,
                "payment_method": "",
                "operator": "",
                "payment_date": "",
                "metadata": {},
            }

    except Exception as e:
        logger.error("CinetPay verify error: %s", e, exc_info=True)
        return {"status": "failed", "amount": 0, "payment_method": "", "operator": "", "payment_date": "", "metadata": {}}


def validate_webhook_signature(request_data, signature_header):
    """Valide la signature du webhook CinetPay.

    Utilise HMAC-SHA256 pour une validation cryptographiquement sure.
    Fallback MD5 pour compatibilite avec les anciens webhooks CinetPay.
    """
    import hmac

    if not CINETPAY_SECRET_KEY:
        return True  # Mode test

    trans_id = str(request_data.get("cpm_trans_id", ""))
    payload = (CINETPAY_SECRET_KEY + trans_id).encode()

    # Verification principale : HMAC-SHA256
    computed_sha256 = hmac.new(
        CINETPAY_SECRET_KEY.encode(), trans_id.encode(), hashlib.sha256
    ).hexdigest()
    if hmac.compare_digest(computed_sha256, signature_header or ""):
        return True

    # Fallback SHA-256 simple (sans HMAC)
    computed_simple = hashlib.sha256(payload).hexdigest()
    if hmac.compare_digest(computed_simple, signature_header or ""):
        return True

    # Dernier fallback : MD5 (compatibilite CinetPay legacy — a supprimer)
    computed_md5 = hashlib.md5(payload).hexdigest()
    if hmac.compare_digest(computed_md5, signature_header or ""):
        logger.warning(
            "Webhook signature validated with MD5 (deprecated) for trans_id=%s. "
            "CinetPay should migrate to SHA-256.",
            trans_id,
        )
        return True

    return False


# ── Tarification ──
PRICING = {
    "promotion": {
        "basic": {"label": "Standard", "price_week": 5000},
        "premium": {"label": "Premium", "price_week": 15000},
        "boost": {"label": "Boost", "price_week": 25000},
    },
    "certification": {
        "standard": {"label": "Certification standard", "price": 25000},
        "express": {"label": "Certification express", "price": 50000},
    },
    "visit": {
        "standard": {"label": "Bon de visite", "price": 5000},
    },
}

def get_validated_price(category, tier):
    """Retourne le prix serveur pour une categorie et un tier donnes.

    Empeche toute manipulation du montant par le client.

    Args:
        category: str — 'promotion', 'certification', 'visit'
        tier: str — 'basic', 'premium', 'standard', 'express', etc.

    Returns:
        int — prix en FCFA

    Raises:
        PaymentError — si la categorie ou le tier est invalide
    """
    cat = PRICING.get(category)
    if not cat:
        raise PaymentError(f"Categorie de paiement invalide : {category}")
    item = cat.get(tier)
    if not item:
        raise PaymentError(f"Option invalide : {tier} pour {category}")
    price = item.get("price") or item.get("price_week")
    if not price or price <= 0:
        raise PaymentError(f"Prix invalide pour {category}/{tier}")
    return int(price)


PAYMENT_METHODS = [
    {"id": "mobile_money_mtn", "name": "MTN Mobile Money", "icon": "bi-phone", "color": "#ffcc00"},
    {"id": "mobile_money_orange", "name": "Orange Money", "icon": "bi-phone", "color": "#ff6600"},
    {"id": "mobile_money_moov", "name": "Moov Money", "icon": "bi-phone", "color": "#0066cc"},
    {"id": "wave", "name": "Wave", "icon": "bi-tsunami", "color": "#1dc1e8"},
    {"id": "visa", "name": "Visa / Mastercard", "icon": "bi-credit-card", "color": "#1a1f71"},
]
