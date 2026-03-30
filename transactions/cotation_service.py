"""
Service de Cotation — EYE-FONCIER
===================================
Logique métier centralisée pour le flux cotation :
  1. Calcul du montant (10 % du prix du bien)
  2. Initiation du paiement CinetPay
  3. Validation après paiement confirmé
  4. Déblocage des droits (visite + documents filigranés)
  5. Déclenchement du workflow de vérification
  6. Gestion de la cotation boutique (vendeurs / promoteurs)
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.db import transaction as db_transaction
from django.utils import timezone

from .cotation_models import Cotation, Boutique, VerificationRequest

logger = logging.getLogger("cotation")


# ═══════════════════════════════════════════════════════════
# COTATION D'ACHAT (CLIENT → PARCELLE)
# ═══════════════════════════════════════════════════════════

@db_transaction.atomic
def create_achat_cotation(buyer, parcelle):
    """
    Cree une cotation d'achat (10 % du prix de la parcelle).
    Protege contre les doubles cotations via select_for_update.

    Args:
        buyer: User — l'acheteur
        parcelle: Parcelle — la parcelle visee

    Returns:
        Cotation

    Raises:
        ValueError — si la parcelle n'est pas disponible ou si
                      l'acheteur a deja une cotation active
    """
    # Verifications metier
    if parcelle.status != "disponible":
        raise ValueError("Cette parcelle n'est plus disponible.")

    if not buyer.is_acheteur:
        raise ValueError("Seuls les acheteurs peuvent payer une cotation d'achat.")

    # Verifier qu'il n'y a pas deja une cotation active (avec verrou)
    existing = (
        Cotation.objects
        .select_for_update()
        .filter(
            payer=buyer,
            parcelle=parcelle,
            status__in=[Cotation.Status.PAID, Cotation.Status.VALIDATED],
        )
        .exists()
    )
    if existing:
        raise ValueError("Vous avez deja une cotation active pour cette parcelle.")

    # Calcul du montant (10 %)
    amount = Cotation.compute_cotation_amount(parcelle.price)

    cotation = Cotation.objects.create(
        payer=buyer,
        parcelle=parcelle,
        cotation_type=Cotation.CotationType.ACHAT,
        amount=amount,
        property_price=parcelle.price,
        status=Cotation.Status.PENDING,
    )

    logger.info(
        "Cotation d'achat creee : %s par %s pour parcelle %s — %s FCFA",
        cotation.reference, buyer, parcelle.lot_number, amount,
    )
    return cotation


def initiate_cotation_payment(cotation, payment_method="mobile_money"):
    """
    Initie le paiement de la cotation via CinetPay.

    Args:
        cotation: Cotation instance
        payment_method: str

    Returns:
        dict — résultat de l'initiation (payment_url, transaction_id, etc.)
    """
    from .payment_service import initiate_payment

    payer = cotation.payer
    description = (
        f"Cotation Eye-Foncier — {cotation.get_cotation_type_display()}"
    )
    if cotation.parcelle:
        description += f" — Parcelle {cotation.parcelle.lot_number}"

    result = initiate_payment(
        amount=cotation.amount,
        description=description,
        customer_name=payer.get_full_name(),
        customer_email=payer.email,
        customer_phone=getattr(payer, "phone", ""),
        payment_type="cotation",
        metadata={
            "cotation_id": str(cotation.pk),
            "cotation_type": cotation.cotation_type,
            "parcelle_id": str(cotation.parcelle.pk) if cotation.parcelle else "",
        },
    )

    # Enregistrer la référence de paiement
    cotation.payment_reference = result.get("transaction_id", "")
    cotation.payment_method = payment_method
    cotation.save(update_fields=["payment_reference", "payment_method"])

    logger.info(
        "Paiement cotation initié : %s — %s FCFA via %s",
        cotation.reference, cotation.amount, payment_method,
    )
    return result


@db_transaction.atomic
def confirm_cotation_payment(cotation, payment_data=None):
    """
    Confirme le paiement d'une cotation (appelé après webhook CinetPay).

    Workflow :
      1. Marque la cotation comme PAID
      2. La passe en VALIDATED
      3. Déclenche le workflow de vérification (si cotation d'achat)
      4. Active la boutique (si cotation boutique)
      5. Envoie les notifications

    Args:
        cotation: Cotation instance
        payment_data: dict — données de paiement CinetPay

    Returns:
        Cotation
    """
    if cotation.status not in [Cotation.Status.PENDING, Cotation.Status.PAID]:
        raise ValueError(f"Cotation déjà traitée (statut : {cotation.get_status_display()}).")

    now = timezone.now()

    # Marquer comme payée puis validée
    cotation.status = Cotation.Status.VALIDATED
    cotation.paid_at = now
    cotation.validated_at = now
    cotation.expires_at = now + timedelta(days=Cotation.VALIDITY_DAYS)
    cotation.save()

    # Actions selon le type de cotation
    if cotation.cotation_type == Cotation.CotationType.ACHAT:
        _handle_achat_cotation_validated(cotation)
    elif cotation.cotation_type == Cotation.CotationType.BOUTIQUE:
        _handle_boutique_cotation_validated(cotation)

    # Notifications
    _send_cotation_notifications(cotation)

    # Génération automatique de la facture
    try:
        from .invoice_service import create_invoice_for_cotation
        invoice = create_invoice_for_cotation(cotation)
        logger.info("Facture %s générée pour cotation %s", invoice.invoice_number, cotation.reference)
    except Exception as e:
        logger.warning("Erreur génération facture pour cotation %s: %s", cotation.reference, e)

    logger.info(
        "Cotation validée : %s — %s FCFA — Type: %s",
        cotation.reference, cotation.amount, cotation.cotation_type,
    )
    return cotation


def check_cotation_access(user, parcelle):
    """
    Vérifie si un utilisateur a une cotation validée pour une parcelle.

    Returns:
        Cotation | None — la cotation validée, ou None
    """
    try:
        return Cotation.objects.get(
            payer=user,
            parcelle=parcelle,
            status=Cotation.Status.VALIDATED,
        )
    except Cotation.DoesNotExist:
        return None


def has_valid_cotation(user, parcelle):
    """
    Raccourci booléen pour vérifier l'accès cotation.

    Returns:
        bool
    """
    cotation = check_cotation_access(user, parcelle)
    return cotation is not None and cotation.is_valid


# ═══════════════════════════════════════════════════════════
# COTATION BOUTIQUE (VENDEUR / PROMOTEUR)
# ═══════════════════════════════════════════════════════════

def create_boutique_cotation(seller, boutique_name):
    """
    Crée une cotation boutique pour un vendeur ou promoteur.

    Args:
        seller: User — le vendeur/promoteur
        boutique_name: str — nom de la boutique

    Returns:
        Cotation
    """
    if seller.role not in ["vendeur", "promoteur"]:
        raise ValueError(
            "Seuls les vendeurs et promoteurs peuvent créer une boutique."
        )

    # Vérifier qu'il n'a pas déjà une boutique active
    if hasattr(seller, "boutique") and seller.boutique.is_active:
        raise ValueError("Vous avez déjà une boutique active.")

    cotation = Cotation.objects.create(
        payer=seller,
        cotation_type=Cotation.CotationType.BOUTIQUE,
        amount=Cotation.BOUTIQUE_COTATION_PRICE,
        status=Cotation.Status.PENDING,
        notes=f"Création boutique : {boutique_name}",
    )

    logger.info(
        "Cotation boutique créée : %s par %s — %s FCFA",
        cotation.reference, seller, Cotation.BOUTIQUE_COTATION_PRICE,
    )
    return cotation


# ═══════════════════════════════════════════════════════════
# WORKFLOW DE VÉRIFICATION
# ═══════════════════════════════════════════════════════════

VERIFICATION_TRANSITIONS = {
    "created": ["assigned", "cancelled"],
    "assigned": ["seller_contacted", "cancelled"],
    "seller_contacted": ["docs_received", "cancelled"],
    "docs_received": ["docs_verified", "cancelled"],
    "docs_verified": ["docs_watermarked", "cancelled"],
    "docs_watermarked": ["client_contacted", "cancelled"],
    "client_contacted": ["rdv_scheduled", "cancelled"],
    "rdv_scheduled": ["completed", "cancelled"],
    "completed": [],
    "cancelled": [],
}


def advance_verification(verification, new_status, actor, notes=""):
    """
    Fait avancer le workflow de vérification.

    Args:
        verification: VerificationRequest instance
        new_status: str
        actor: User — le vérificateur
        notes: str

    Returns:
        VerificationRequest

    Raises:
        ValueError — si la transition n'est pas autorisée
    """
    allowed = VERIFICATION_TRANSITIONS.get(verification.status, [])
    if new_status not in allowed:
        raise ValueError(
            f"Transition interdite : {verification.status} → {new_status}. "
            f"Autorisées : {allowed}"
        )

    now = timezone.now()
    old_status = verification.status
    verification.status = new_status

    # Horodatages automatiques
    timestamp_map = {
        "seller_contacted": "seller_contacted_at",
        "docs_received": "docs_received_at",
        "docs_verified": "docs_verified_at",
        "client_contacted": "client_contacted_at",
        "completed": "completed_at",
    }
    ts_field = timestamp_map.get(new_status)
    if ts_field:
        setattr(verification, ts_field, now)

    if notes:
        verification.verification_notes += f"\n[{now:%d/%m/%Y %H:%M}] {notes}"

    verification.save()

    # Notifications à chaque étape
    _send_verification_notification(verification, old_status, new_status, actor)

    logger.info(
        "Vérification %s : %s → %s par %s",
        verification.reference, old_status, new_status, actor,
    )
    return verification


# ═══════════════════════════════════════════════════════════
# FONCTIONS INTERNES
# ═══════════════════════════════════════════════════════════

def _handle_achat_cotation_validated(cotation):
    """
    Actions après validation d'une cotation d'achat :
    - Créer la demande de vérification
    - Le vérificateur sera assigné par l'admin
    """
    parcelle = cotation.parcelle
    if not parcelle:
        return

    VerificationRequest.objects.create(
        cotation=cotation,
        buyer=cotation.payer,
        seller=parcelle.owner,
        parcelle=parcelle,
        status=VerificationRequest.Status.CREATED,
    )

    logger.info(
        "Vérification créée automatiquement pour cotation %s",
        cotation.reference,
    )


def _handle_boutique_cotation_validated(cotation):
    """
    Actions après validation d'une cotation boutique :
    - Créer/activer la boutique
    - Mettre à jour le rôle si nécessaire
    """
    from django.utils.text import slugify

    seller = cotation.payer
    boutique_name = cotation.notes.replace("Création boutique : ", "")

    boutique, created = Boutique.objects.get_or_create(
        owner=seller,
        defaults={
            "name": boutique_name,
            "slug": slugify(boutique_name) or f"boutique-{seller.pk.hex[:8]}",
            "cotation": cotation,
            "status": Boutique.Status.ACTIVE,
        },
    )
    if not created:
        boutique.status = Boutique.Status.ACTIVE
        boutique.cotation = cotation
        boutique.save(update_fields=["status", "cotation"])

    logger.info("Boutique activée : %s pour %s", boutique.name, seller)


def _send_cotation_notifications(cotation):
    """Envoie les notifications après validation de cotation."""
    try:
        from notifications.services import send_notification

        payer = cotation.payer
        amount_str = "{:,.0f}".format(cotation.amount)

        if cotation.cotation_type == Cotation.CotationType.ACHAT:
            parcelle = cotation.parcelle
            send_notification(
                recipient=payer,
                notification_type="cotation_validated",
                title="Cotation validée — Droits débloqués",
                message=(
                    f"Votre cotation de {amount_str} FCFA pour la parcelle "
                    f"{parcelle.lot_number} a été validée. "
                    f"Vous pouvez maintenant :\n"
                    f"• Demander une visite de la parcelle\n"
                    f"• Consulter les documents filigranés\n"
                    f"• Procéder à la réservation définitive\n"
                    f"Un vérificateur Eye-Foncier va contacter le vendeur."
                ),
                data={
                    "cotation_id": str(cotation.pk),
                    "parcelle_id": str(parcelle.pk),
                    "parcelle_lot": parcelle.lot_number,
                    "action_url": f"/parcelles/{parcelle.pk}/",
                    "email_template": "notifications/email/cotation_validated.html",
                },
            )

            # Notifier le vendeur
            send_notification(
                recipient=parcelle.owner,
                notification_type="cotation_validated",
                title=f"Nouveau client intéressé — {parcelle.lot_number}",
                message=(
                    f"{payer.get_full_name()} a payé une cotation de "
                    f"{amount_str} FCFA pour votre parcelle {parcelle.lot_number}. "
                    f"Un vérificateur Eye-Foncier vous contactera bientôt "
                    f"pour la collecte des documents."
                ),
                data={
                    "cotation_id": str(cotation.pk),
                    "parcelle_id": str(parcelle.pk),
                    "buyer_name": payer.get_full_name(),
                    "email_template": "notifications/email/cotation_seller_notice.html",
                },
            )

        elif cotation.cotation_type == Cotation.CotationType.BOUTIQUE:
            send_notification(
                recipient=payer,
                notification_type="boutique_activated",
                title="Boutique activée",
                message=(
                    f"Votre cotation boutique de {amount_str} FCFA a été validée. "
                    f"Votre boutique est maintenant active ! "
                    f"Vous pouvez publier vos parcelles."
                ),
                data={
                    "cotation_id": str(cotation.pk),
                    "action_url": "/mon-espace/boutique/",
                    "email_template": "notifications/email/boutique_activated.html",
                },
            )

    except Exception as e:
        logger.error("Erreur notification cotation : %s", e)


def _send_verification_notification(verification, old_status, new_status, actor):
    """Notifications pour chaque étape du workflow de vérification."""
    try:
        from notifications.services import send_notification

        parcelle = verification.parcelle
        messages_map = {
            "seller_contacted": {
                "recipient": verification.seller,
                "title": f"Eye-Foncier vous contacte — {parcelle.lot_number}",
                "message": (
                    f"Le vérificateur Eye-Foncier {actor.get_full_name()} vous contacte "
                    f"concernant votre parcelle {parcelle.lot_number}. "
                    f"Merci de préparer les documents physiques pour dépôt dans nos locaux."
                ),
            },
            "docs_received": {
                "recipient": verification.buyer,
                "title": f"Documents reçus — {parcelle.lot_number}",
                "message": (
                    f"Les documents physiques de la parcelle {parcelle.lot_number} "
                    f"ont été reçus dans nos locaux. L'analyse est en cours."
                ),
            },
            "docs_verified": {
                "recipient": verification.buyer,
                "title": f"Documents vérifiés — {parcelle.lot_number}",
                "message": (
                    f"Les documents de la parcelle {parcelle.lot_number} ont été "
                    f"vérifiés et analysés par Eye-Foncier. "
                    f"Vous pouvez maintenant consulter les documents filigranés."
                ),
            },
            "client_contacted": {
                "recipient": verification.buyer,
                "title": f"Rendez-vous Eye-Foncier — {parcelle.lot_number}",
                "message": (
                    f"Eye-Foncier vous invite à vous rendre dans nos locaux "
                    f"pour finaliser l'achat de la parcelle {parcelle.lot_number}. "
                    f"Apportez votre pièce d'identité et le solde restant."
                ),
            },
        }

        notif = messages_map.get(new_status)
        if notif:
            send_notification(
                recipient=notif["recipient"],
                notification_type="verification_update",
                title=notif["title"],
                message=notif["message"],
                data={
                    "verification_id": str(verification.pk),
                    "parcelle_id": str(parcelle.pk),
                    "parcelle_lot": parcelle.lot_number,
                    "status": new_status,
                    "email_template": "notifications/email/verification_update.html",
                },
            )

    except Exception as e:
        logger.error("Erreur notification vérification : %s", e)
