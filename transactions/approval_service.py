"""
Service d'approbation bipartite — EYE-FONCIER
Gère les demandes de validation entre acheteur et vendeur.
"""
import logging

from django.db import transaction as db_transaction
from django.utils import timezone

from .models import Transaction, TransactionApproval, TransactionEvent

logger = logging.getLogger(__name__)

# Opération → qui doit approuver (buyer ou seller)
APPROVER_ROLE = {
    "reserve": "seller",
    "escrow_fund": "seller",
    "docs_confirm": "seller",
    "compromis": "buyer",
}

OPERATION_LABELS = {
    "reserve": "Réservation de la parcelle",
    "escrow_fund": "Alimentation du séquestre",
    "docs_confirm": "Confirmation de réception des documents",
    "compromis": "Compromis de vente",
}


def _get_counterparty(transaction, operation_type):
    """Retourne l'utilisateur qui doit approuver l'opération."""
    role = APPROVER_ROLE.get(operation_type)
    if role == "seller":
        return transaction.seller
    return transaction.buyer


def request_approval(transaction, operation_type, requested_by, metadata=None):
    """
    Crée une demande d'approbation pour une opération.

    Returns:
        TransactionApproval

    Raises:
        ValueError si une approbation pending existe déjà
    """
    if metadata is None:
        metadata = {}

    counterparty = _get_counterparty(transaction, operation_type)
    label = OPERATION_LABELS.get(operation_type, operation_type)

    # Vérifier qu'il n'y a pas déjà une demande pending
    existing = TransactionApproval.objects.filter(
        transaction=transaction,
        operation_type=operation_type,
        status=TransactionApproval.Status.PENDING,
    ).exists()
    if existing:
        raise ValueError(f"Une demande d'approbation est déjà en attente pour : {label}")

    approval = TransactionApproval.objects.create(
        transaction=transaction,
        operation_type=operation_type,
        status=TransactionApproval.Status.PENDING,
        requested_by=requested_by,
        metadata=metadata,
    )

    # Audit trail
    TransactionEvent.objects.create(
        transaction=transaction,
        event_type=TransactionEvent.EventType.APPROVAL_REQUESTED,
        old_status=transaction.status,
        new_status=transaction.status,
        actor=requested_by,
        description=f"Demande d'approbation : {label}",
        metadata={"approval_id": str(approval.pk), "operation_type": operation_type},
    )

    # Notification à la contrepartie
    try:
        from notifications.services import send_notification

        amount_str = "{:,.0f}".format(transaction.amount) if transaction.amount else "0"
        send_notification(
            recipient=counterparty,
            notification_type="transaction_status",
            title=f"Approbation requise — {label}",
            message=(
                f"{requested_by.get_full_name()} demande votre approbation pour : "
                f"{label} (parcelle {transaction.parcelle.lot_number}, Ref: {transaction.reference}). "
                f"Montant : {amount_str} FCFA. Connectez-vous pour valider ou refuser."
            ),
            data={
                "transaction_id": str(transaction.pk),
                "approval_id": str(approval.pk),
                "operation_type": operation_type,
                "operation_label": label,
                "reference": transaction.reference,
                "parcelle_lot": transaction.parcelle.lot_number,
                "parcelle_title": transaction.parcelle.title,
                "amount": amount_str,
                "requester_name": requested_by.get_full_name() or requested_by.email,
                "action_url": f"/transactions/approbation/{approval.pk}/approuver/",
                "reject_url": f"/transactions/approbation/{approval.pk}/refuser/",
                "email_template": "notifications/email/approval_requested.html",
            },
        )
    except Exception as e:
        logger.error("Erreur notification approbation : %s", e)

    logger.info(
        "Approbation demandée : %s pour TX %s par %s",
        operation_type, transaction.reference, requested_by,
    )
    return approval


@db_transaction.atomic
def approve_operation(approval, reviewed_by):
    """
    Approuve une opération et l'exécute.

    Returns:
        TransactionApproval

    Raises:
        ValueError si l'approbation n'est plus pending ou si l'utilisateur
        n'est pas la bonne contrepartie.
    """
    # Lock pour éviter les race conditions
    approval = TransactionApproval.objects.select_for_update().get(pk=approval.pk)

    if approval.status != TransactionApproval.Status.PENDING:
        raise ValueError("Cette demande a déjà été traitée.")

    tx = approval.transaction
    counterparty = _get_counterparty(tx, approval.operation_type)
    if reviewed_by != counterparty:
        raise ValueError("Vous n'êtes pas autorisé à approuver cette opération.")

    # Vérifier que la transaction n'a pas été annulée entre-temps
    if tx.status in ("cancelled", "completed"):
        approval.status = TransactionApproval.Status.REJECTED
        approval.reason = "Transaction terminée"
        approval.reviewed_by = reviewed_by
        approval.reviewed_at = timezone.now()
        approval.save()
        raise ValueError("La transaction a été clôturée entre-temps.")

    # Marquer comme approuvé
    approval.status = TransactionApproval.Status.APPROVED
    approval.reviewed_by = reviewed_by
    approval.reviewed_at = timezone.now()
    approval.save()

    # Exécuter l'opération
    _execute_operation(approval)

    # Audit trail
    label = OPERATION_LABELS.get(approval.operation_type, approval.operation_type)
    TransactionEvent.objects.create(
        transaction=tx,
        event_type=TransactionEvent.EventType.APPROVAL_APPROVED,
        old_status=tx.status,
        new_status=tx.status,
        actor=reviewed_by,
        description=f"Approbation accordée : {label}",
        metadata={"approval_id": str(approval.pk), "operation_type": approval.operation_type},
    )

    # Notification au demandeur
    try:
        from notifications.services import send_notification

        amount_str = "{:,.0f}".format(tx.amount) if tx.amount else "0"
        send_notification(
            recipient=approval.requested_by,
            notification_type="transaction_status",
            title=f"Opération approuvée — {label}",
            message=(
                f"{reviewed_by.get_full_name()} a approuvé : {label} "
                f"pour la parcelle {tx.parcelle.lot_number} (Ref: {tx.reference}). "
                f"Montant : {amount_str} FCFA."
            ),
            data={
                "transaction_id": str(tx.pk),
                "approval_id": str(approval.pk),
                "operation_label": label,
                "reference": tx.reference,
                "parcelle_lot": tx.parcelle.lot_number,
                "parcelle_title": tx.parcelle.title,
                "amount": amount_str,
                "reviewer_name": reviewed_by.get_full_name() or reviewed_by.email,
                "action_url": f"/transactions/{tx.pk}/",
                "result": "approved",
                "email_template": "notifications/email/approval_result.html",
            },
        )
    except Exception as e:
        logger.error("Erreur notification approbation approuvée : %s", e)

    logger.info(
        "Approbation accordée : %s pour TX %s par %s",
        approval.operation_type, tx.reference, reviewed_by,
    )
    return approval


def reject_operation(approval, reviewed_by, reason=""):
    """
    Rejette une demande d'approbation.
    Le demandeur pourra réessayer (nouvelle demande).
    """
    if approval.status != TransactionApproval.Status.PENDING:
        raise ValueError("Cette demande a déjà été traitée.")

    tx = approval.transaction
    counterparty = _get_counterparty(tx, approval.operation_type)
    if reviewed_by != counterparty:
        raise ValueError("Vous n'êtes pas autorisé à traiter cette demande.")

    approval.status = TransactionApproval.Status.REJECTED
    approval.reviewed_by = reviewed_by
    approval.reviewed_at = timezone.now()
    approval.reason = reason
    approval.save()

    label = OPERATION_LABELS.get(approval.operation_type, approval.operation_type)

    # Audit trail
    TransactionEvent.objects.create(
        transaction=tx,
        event_type=TransactionEvent.EventType.APPROVAL_REJECTED,
        old_status=tx.status,
        new_status=tx.status,
        actor=reviewed_by,
        description=f"Approbation refusée : {label}. Motif : {reason or '—'}",
        metadata={
            "approval_id": str(approval.pk),
            "operation_type": approval.operation_type,
            "reason": reason,
        },
    )

    # Notification au demandeur
    try:
        from notifications.services import send_notification

        amount_str = "{:,.0f}".format(tx.amount) if tx.amount else "0"
        msg = (
            f"{reviewed_by.get_full_name()} a refusé : {label} "
            f"pour la parcelle {tx.parcelle.lot_number} (Ref: {tx.reference})."
        )
        if reason:
            msg += f" Motif : {reason}"
        msg += " Vous pouvez soumettre une nouvelle demande."

        send_notification(
            recipient=approval.requested_by,
            notification_type="transaction_status",
            title=f"Opération refusée — {label}",
            message=msg,
            data={
                "transaction_id": str(tx.pk),
                "approval_id": str(approval.pk),
                "operation_label": label,
                "reference": tx.reference,
                "parcelle_lot": tx.parcelle.lot_number,
                "parcelle_title": tx.parcelle.title,
                "amount": amount_str,
                "reviewer_name": reviewed_by.get_full_name() or reviewed_by.email,
                "reason": reason,
                "action_url": f"/transactions/{tx.pk}/",
                "result": "rejected",
                "email_template": "notifications/email/approval_result.html",
            },
        )
    except Exception as e:
        logger.error("Erreur notification approbation refusée : %s", e)

    logger.info(
        "Approbation refusée : %s pour TX %s par %s — %s",
        approval.operation_type, tx.reference, reviewed_by, reason,
    )
    return approval


def _execute_operation(approval):
    """Exécute l'opération après approbation."""
    from .transaction_service import transition_status

    tx = approval.transaction
    op = approval.operation_type
    actor = approval.requested_by

    if op == "reserve":
        transition_status(tx, "reserved", actor, "Réservation approuvée par le vendeur")

    elif op == "escrow_fund":
        tx.escrow_amount = tx.amount
        tx.payment_method = "escrow"
        tx.save(update_fields=["escrow_amount", "payment_method"])
        transition_status(tx, "escrow_funded", actor, "Séquestre approuvé par le vendeur")
        tx.escrow_funded = True
        tx.escrow_funded_at = timezone.now()
        tx.save(update_fields=["escrow_funded", "escrow_funded_at"])

    elif op == "docs_confirm":
        transition_status(tx, "docs_validated", actor, "Confirmation documents approuvée par le vendeur")
        tx.buyer_docs_confirmed = True
        tx.buyer_docs_confirmed_at = timezone.now()
        tx.save(update_fields=["buyer_docs_confirmed", "buyer_docs_confirmed_at"])

    elif op == "compromis":
        tx.compromis_generated = True
        tx.compromis_generated_at = timezone.now()
        tx.save(update_fields=["compromis_generated", "compromis_generated_at"])
