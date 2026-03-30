"""
Service centralisé des transactions — EYE-FONCIER
Machine d'état avec audit trail et notifications automatiques.
"""
import logging

from django.utils import timezone

from .models import Transaction, TransactionEvent

logger = logging.getLogger(__name__)

# Transitions autorisées : {statut_actuel: [statuts_possibles]}
VALID_TRANSITIONS = {
    "pending": ["reserved", "cancelled"],
    "reserved": ["escrow_funded", "cancelled", "disputed"],
    "escrow_funded": ["docs_validated", "cancelled", "disputed"],
    "docs_validated": ["paid", "completed", "cancelled", "disputed"],
    "paid": ["completed", "disputed"],
    "completed": ["disputed"],
    "cancelled": [],
    "disputed": ["completed", "cancelled"],
}

# Mapping statut → type de notification + email template
STATUS_NOTIFICATIONS = {
    "reserved": {
        "type": "transaction_status",
        "email_template": "notifications/email/transaction_status.html",
        "title": "Parcelle réservée",
        "buyer_msg": (
            "Votre réservation pour la parcelle {lot} (Ref: {reference}) a été enregistrée. "
            "Montant : {amount} FCFA. Le vendeur {seller_name} a été notifié."
        ),
        "seller_msg": (
            "L'acheteur {buyer_name} a réservé votre parcelle {lot} (Ref: {reference}). "
            "Montant : {amount} FCFA. Consultez les détails sur votre espace."
        ),
    },
    "escrow_funded": {
        "type": "escrow_update",
        "email_template": "notifications/email/escrow_update.html",
        "title": "Séquestre alimenté",
        "buyer_msg": (
            "Le séquestre pour la parcelle {lot} (Ref: {reference}) a été alimenté avec {amount} FCFA. "
            "Les fonds sont sécurisés jusqu'à la finalisation."
        ),
        "seller_msg": (
            "Le séquestre pour la parcelle {lot} (Ref: {reference}) a été alimenté par {buyer_name} : "
            "{amount} FCFA. Les fonds seront libérés à la finalisation."
        ),
    },
    "docs_validated": {
        "type": "transaction_status",
        "email_template": "notifications/email/transaction_status.html",
        "title": "Documents validés",
        "buyer_msg": (
            "Vous avez confirmé la réception des documents pour la parcelle {lot} (Ref: {reference}). "
            "La prochaine étape est le compromis de vente."
        ),
        "seller_msg": (
            "L'acheteur {buyer_name} a confirmé la réception des documents pour la parcelle {lot} "
            "(Ref: {reference}). Vous pouvez initier le compromis de vente."
        ),
    },
    "completed": {
        "type": "payment_confirmed",
        "email_template": "notifications/email/transaction_status.html",
        "title": "Transaction finalisée",
        "buyer_msg": (
            "Félicitations ! La transaction pour la parcelle {lot} (Ref: {reference}) est finalisée. "
            "Montant : {amount} FCFA. Votre propriété est maintenant enregistrée."
        ),
        "seller_msg": (
            "La vente de la parcelle {lot} (Ref: {reference}) est finalisée. "
            "Le séquestre de {amount} FCFA sera libéré sur votre compte."
        ),
    },
    "cancelled": {
        "type": "transaction_status",
        "email_template": "notifications/email/transaction_status.html",
        "title": "Transaction annulée",
        "buyer_msg": "La transaction pour la parcelle {lot} (Ref: {reference}) a été annulée. Montant : {amount} FCFA.",
        "seller_msg": "La transaction pour la parcelle {lot} (Ref: {reference}) a été annulée. La parcelle est de nouveau disponible.",
    },
    "disputed": {
        "type": "transaction_status",
        "email_template": "notifications/email/transaction_status.html",
        "title": "Litige ouvert",
        "buyer_msg": "Un litige a été ouvert pour la transaction {lot} (Ref: {reference}). Le séquestre est gelé.",
        "seller_msg": "Un litige a été ouvert pour la transaction {lot} (Ref: {reference}). Le séquestre est gelé.",
    },
}


def transition_status(transaction, new_status, actor, notes=""):
    """
    Effectue une transition de statut avec validation, audit et notifications.

    Args:
        transaction: Transaction instance
        new_status: str — nouveau statut
        actor: User instance
        notes: str — description optionnelle

    Returns:
        TransactionEvent — événement créé

    Raises:
        ValueError — si la transition n'est pas autorisée
    """
    old_status = transaction.status

    # Valider la transition
    allowed = VALID_TRANSITIONS.get(old_status, [])
    if new_status not in allowed:
        raise ValueError(
            f"Transition interdite : {old_status} → {new_status}. "
            f"Transitions autorisées : {allowed}"
        )

    # Créer l'événement d'audit
    event = TransactionEvent.objects.create(
        transaction=transaction,
        event_type=new_status,
        old_status=old_status,
        new_status=new_status,
        actor=actor,
        description=notes,
    )

    # Mettre à jour le statut
    transaction.status = new_status

    # Effets de bord par statut
    _handle_side_effects(transaction, new_status, actor)

    transaction.save()

    # Envoyer les notifications
    _send_transition_notifications(transaction, new_status)

    logger.info(
        "Transaction %s : %s → %s (par %s)",
        transaction.reference, old_status, new_status, actor,
    )

    return event


def cancel_transaction(transaction, actor, reason=""):
    """Annule une transaction avec gestion du remboursement séquestre."""
    if transaction.status == Transaction.Status.COMPLETED:
        raise ValueError("Impossible d'annuler une transaction finalisée.")

    if transaction.status == Transaction.Status.CANCELLED:
        raise ValueError("Cette transaction est déjà annulée.")

    notes = reason or "Annulation de la transaction"

    # Si séquestre alimenté, initier le remboursement
    if transaction.escrow_funded and not transaction.escrow_released:
        TransactionEvent.objects.create(
            transaction=transaction,
            event_type=TransactionEvent.EventType.REFUND_INITIATED,
            old_status=transaction.status,
            new_status="cancelled",
            actor=actor,
            description=f"Remboursement séquestre initié : {transaction.escrow_amount} FCFA",
            metadata={"escrow_amount": str(transaction.escrow_amount)},
        )

    return transition_status(transaction, "cancelled", actor, notes)


def initiate_dispute(transaction, actor, reason):
    """Ouvre un litige sur une transaction."""
    event = transition_status(transaction, "disputed", actor, reason)

    # Notifier les admins
    _notify_admins_dispute(transaction, reason)

    return event


def resolve_dispute(transaction, actor, resolution, refund_amount=None):
    """
    Résout un litige.

    Args:
        resolution: "completed" ou "cancelled"
        refund_amount: Decimal | None — montant à rembourser si annulation
    """
    if transaction.status != Transaction.Status.DISPUTED:
        raise ValueError("Cette transaction n'est pas en litige.")

    notes = f"Litige résolu → {resolution}"
    if refund_amount:
        notes += f" | Remboursement : {refund_amount} FCFA"

    event = transition_status(transaction, resolution, actor, notes)

    # Événement de résolution
    TransactionEvent.objects.create(
        transaction=transaction,
        event_type=TransactionEvent.EventType.DISPUTE_RESOLVED,
        old_status="disputed",
        new_status=resolution,
        actor=actor,
        description=notes,
        metadata={
            "resolution": resolution,
            "refund_amount": str(refund_amount) if refund_amount else None,
        },
    )

    return event


def get_transaction_timeline(transaction):
    """Retourne la timeline ordonnée d'une transaction."""
    return transaction.events.all().order_by("created_at")


# ──────────────────────────────────────────────
# Fonctions internes
# ──────────────────────────────────────────────


def _handle_side_effects(transaction, new_status, actor):
    """Gère les effets de bord pour chaque changement de statut."""
    parcelle = transaction.parcelle
    parcelle_changed = False

    if new_status == "reserved":
        transaction.reserved_at = timezone.now()
        parcelle.status = "reserve"
        parcelle.save(update_fields=["status"])
        parcelle_changed = True

    elif new_status == "completed":
        transaction.completed_at = timezone.now()
        if transaction.escrow_funded and not transaction.escrow_released:
            transaction.escrow_released = True
            transaction.escrow_released_at = timezone.now()
        parcelle.status = "vendu"
        parcelle.save(update_fields=["status"])
        parcelle_changed = True
        # Incrémenter les ventes du vendeur
        profile = getattr(transaction.seller, "profile", None)
        if profile:
            profile.total_sales += 1
            profile.save(update_fields=["total_sales"])

    elif new_status == "cancelled":
        transaction.cancelled_at = timezone.now()
        # Remettre la parcelle disponible si elle était réservée par cette transaction
        if parcelle.status == "reserve":
            parcelle.status = "disponible"
            parcelle.save(update_fields=["status"])
            parcelle_changed = True

    elif new_status == "disputed":
        # Geler le séquestre (pas de libération possible)
        pass

    # Invalider le cache GeoJSON si le statut parcelle a changé
    if parcelle_changed:
        try:
            from parcelles.signals import invalidate_geojson_cache
            invalidate_geojson_cache()
        except Exception:
            pass


def _send_transition_notifications(transaction, new_status):
    """Envoie les notifications enrichies pour un changement de statut."""
    try:
        from notifications.services import send_notification
    except ImportError:
        logger.warning("Module notifications non disponible")
        return

    config = STATUS_NOTIFICATIONS.get(new_status)
    if not config:
        return

    lot = transaction.parcelle.lot_number
    amount_str = "{:,.0f}".format(transaction.amount) if transaction.amount else "0"
    buyer_name = transaction.buyer.get_full_name() or transaction.buyer.email
    seller_name = transaction.seller.get_full_name() or transaction.seller.email

    fmt_vars = {
        "lot": lot,
        "amount": amount_str,
        "reference": transaction.reference,
        "buyer_name": buyer_name,
        "seller_name": seller_name,
    }

    data = {
        "transaction_id": str(transaction.pk),
        "parcelle_id": str(transaction.parcelle.pk),
        "reference": transaction.reference,
        "status": new_status,
        "parcelle_lot": lot,
        "parcelle_title": transaction.parcelle.title,
        "amount": amount_str,
        "buyer_name": buyer_name,
        "seller_name": seller_name,
        "action_url": f"/transactions/{transaction.pk}/",
        "email_template": config.get("email_template"),
    }

    # Notification acheteur
    buyer_msg = config.get("buyer_msg")
    if buyer_msg:
        send_notification(
            recipient=transaction.buyer,
            notification_type=config["type"],
            title=config["title"],
            message=buyer_msg.format(**fmt_vars),
            data=data,
        )

    # Notification vendeur
    seller_msg = config.get("seller_msg")
    if seller_msg:
        send_notification(
            recipient=transaction.seller,
            notification_type=config["type"],
            title=config["title"],
            message=seller_msg.format(**fmt_vars),
            data=data,
        )


def _notify_admins_dispute(transaction, reason):
    """Notifie les administrateurs d'un nouveau litige."""
    try:
        from notifications.services import send_notification
        from django.contrib.auth import get_user_model

        User = get_user_model()
        admins = User.objects.filter(is_staff=True)

        for admin_user in admins:
            send_notification(
                recipient=admin_user,
                notification_type="transaction_status",
                title=f"Litige ouvert — {transaction.reference}",
                message=f"Un litige a été ouvert pour la transaction {transaction.reference} "
                        f"(parcelle {transaction.parcelle.lot_number}). Raison : {reason}",
                data={
                    "transaction_id": str(transaction.pk),
                    "reference": transaction.reference,
                    "reason": reason,
                },
                channels=["inapp", "email"],
            )
    except Exception as e:
        logger.error("Erreur notification admins litige : %s", e)
