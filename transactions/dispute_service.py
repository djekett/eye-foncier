"""
Service de gestion des litiges — EYE-FONCIER
Machine d'etat, notifications automatiques, gestion des remboursements.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.db import transaction as db_transaction
from django.utils import timezone

from .dispute_models import Dispute, DisputeMessage
from .models import Transaction, TransactionEvent
from .transaction_service import transition_status

logger = logging.getLogger(__name__)

# Transitions autorisees pour les litiges
DISPUTE_TRANSITIONS = {
    "opened": ["under_review", "closed"],
    "under_review": ["mediation", "resolved", "escalated", "closed"],
    "mediation": ["resolved", "escalated", "closed"],
    "escalated": ["resolved", "closed"],
    "resolved": ["closed"],
    "closed": [],
}

# Delais par defaut selon la priorite (en jours)
DEADLINE_DAYS = {
    "low": 30,
    "normal": 15,
    "high": 7,
    "urgent": 3,
}


@db_transaction.atomic
def open_dispute(transaction, opened_by, category, subject, description, priority="normal"):
    """
    Ouvre un litige sur une transaction.

    Args:
        transaction: Transaction instance
        opened_by: User instance (acheteur ou vendeur)
        category: str — categorie du litige
        subject: str — sujet court
        description: str — description detaillee
        priority: str — priorite (low/normal/high/urgent)

    Returns:
        Dispute instance

    Raises:
        ValueError — si la transaction ne peut pas avoir de litige
    """
    # Verifier que l'utilisateur est partie prenante
    if opened_by not in (transaction.buyer, transaction.seller) and not opened_by.is_staff:
        raise ValueError("Seuls l'acheteur, le vendeur ou un admin peuvent ouvrir un litige.")

    # Verifier qu'il n'y a pas deja un litige ouvert
    existing = Dispute.objects.filter(
        transaction=transaction,
        status__in=["opened", "under_review", "mediation", "escalated"],
    ).exists()
    if existing:
        raise ValueError("Un litige est deja en cours pour cette transaction.")

    # Verifier que la transaction n'est pas terminee ou annulee
    if transaction.status in (Transaction.Status.CANCELLED,):
        raise ValueError("Impossible d'ouvrir un litige sur une transaction annulee.")

    # Calculer la deadline
    deadline = timezone.now() + timedelta(days=DEADLINE_DAYS.get(priority, 15))

    # Creer le litige
    dispute = Dispute.objects.create(
        transaction=transaction,
        opened_by=opened_by,
        category=category,
        priority=priority,
        subject=subject,
        description=description,
        deadline=deadline,
    )

    # Passer la transaction en statut "disputed" si ce n'est pas deja le cas
    if transaction.status != Transaction.Status.DISPUTED:
        try:
            transition_status(transaction, "disputed", opened_by, f"Litige ouvert : {subject}")
        except ValueError:
            # La transaction ne peut pas passer en disputed (deja cancelled par ex.)
            logger.warning(
                "Transaction %s ne peut pas passer en disputed (statut actuel: %s)",
                transaction.reference, transaction.status,
            )

    # Message systeme dans le fil
    DisputeMessage.objects.create(
        dispute=dispute,
        sender=opened_by,
        sender_role="system",
        content=f"Litige ouvert par {opened_by.get_full_name() or opened_by.email}. "
                f"Categorie : {dispute.get_category_display()}. "
                f"Priorite : {dispute.get_priority_display()}. "
                f"Date limite de resolution : {deadline.strftime('%d/%m/%Y')}.",
    )

    # Notifications
    _notify_dispute_opened(dispute)

    logger.info("Litige %s ouvert pour transaction %s", dispute.reference, transaction.reference)
    return dispute


@db_transaction.atomic
def transition_dispute(dispute, new_status, actor, notes=""):
    """
    Change le statut d'un litige avec validation et audit.

    Args:
        dispute: Dispute instance
        new_status: str — nouveau statut
        actor: User instance (mediateur ou admin)
        notes: str — commentaire

    Returns:
        Dispute — mis a jour

    Raises:
        ValueError — si la transition est interdite
    """
    old_status = dispute.status
    allowed = DISPUTE_TRANSITIONS.get(old_status, [])

    if new_status not in allowed:
        raise ValueError(
            f"Transition interdite : {old_status} -> {new_status}. "
            f"Transitions autorisees : {allowed}"
        )

    dispute.status = new_status

    if new_status == "escalated":
        dispute.escalated_at = timezone.now()
    elif new_status == "resolved":
        dispute.resolved_at = timezone.now()
    elif new_status == "closed":
        dispute.closed_at = timezone.now()

    dispute.save()

    # Message systeme
    DisputeMessage.objects.create(
        dispute=dispute,
        sender=actor,
        sender_role="mediator" if actor.is_staff else "system",
        content=f"Statut change : {old_status} -> {new_status}. {notes}",
    )

    # Notification
    _notify_dispute_status_change(dispute, old_status, new_status, notes)

    logger.info(
        "Litige %s : %s -> %s (par %s)",
        dispute.reference, old_status, new_status, actor,
    )
    return dispute


@db_transaction.atomic
def assign_mediator(dispute, mediator, actor):
    """Assigne un mediateur a un litige."""
    dispute.assigned_to = mediator
    if dispute.status == "opened":
        dispute.status = "under_review"
    dispute.save()

    DisputeMessage.objects.create(
        dispute=dispute,
        sender=actor,
        sender_role="system",
        content=f"Mediateur assigne : {mediator.get_full_name() or mediator.email}.",
    )

    _notify_mediator_assigned(dispute, mediator)
    return dispute


@db_transaction.atomic
def resolve_dispute(dispute, actor, resolution_type, notes="", refund_amount=None):
    """
    Resout un litige avec gestion du remboursement.

    Args:
        dispute: Dispute instance
        actor: User (admin/mediateur)
        resolution_type: str — type de resolution
        notes: str — explication
        refund_amount: Decimal | None

    Returns:
        Dispute — mis a jour
    """
    if not dispute.is_open:
        raise ValueError("Ce litige est deja clos.")

    dispute.resolution_type = resolution_type
    dispute.resolution_notes = notes
    dispute.resolved_at = timezone.now()
    dispute.status = Dispute.Status.RESOLVED

    # Gestion du remboursement
    if refund_amount and refund_amount > 0:
        dispute.refund_amount = Decimal(str(refund_amount))
        # Le remboursement sera traite separement
        _initiate_refund(dispute, actor)

    dispute.save()

    # Mettre a jour la transaction
    tx = dispute.transaction
    if resolution_type == Dispute.Resolution.TRANSACTION_RESUMED:
        # Reprendre la transaction a l'etat precedent
        _resume_transaction(tx, actor, notes)
    elif resolution_type in (
        Dispute.Resolution.FULL_REFUND,
        Dispute.Resolution.PARTIAL_REFUND,
        Dispute.Resolution.NO_REFUND,
    ):
        # Annuler la transaction si remboursement
        if tx.status == Transaction.Status.DISPUTED:
            try:
                transition_status(tx, "cancelled", actor, f"Litige resolu : {notes}")
            except ValueError:
                pass

    # Message systeme
    msg = f"Litige resolu : {dispute.get_resolution_type_display()}."
    if refund_amount:
        msg += f" Remboursement : {refund_amount:,.0f} FCFA."
    DisputeMessage.objects.create(
        dispute=dispute,
        sender=actor,
        sender_role="mediator",
        content=msg,
    )

    # Audit trail sur la transaction
    TransactionEvent.objects.create(
        transaction=tx,
        event_type=TransactionEvent.EventType.DISPUTE_RESOLVED,
        old_status="disputed",
        new_status=tx.status,
        actor=actor,
        description=f"Litige {dispute.reference} resolu : {resolution_type}",
        metadata={
            "dispute_id": str(dispute.pk),
            "resolution": resolution_type,
            "refund_amount": str(refund_amount) if refund_amount else None,
        },
    )

    # Notifications
    _notify_dispute_resolved(dispute)

    logger.info("Litige %s resolu : %s", dispute.reference, resolution_type)
    return dispute


def add_message(dispute, sender, content, sender_role=None, is_internal=False, attachment=None):
    """Ajoute un message dans le fil de discussion du litige."""
    if not dispute.is_open:
        raise ValueError("Impossible d'ajouter un message a un litige clos.")

    # Determiner le role automatiquement
    if not sender_role:
        tx = dispute.transaction
        if sender.is_staff:
            sender_role = "mediator"
        elif sender == tx.buyer:
            sender_role = "buyer"
        elif sender == tx.seller:
            sender_role = "seller"
        else:
            sender_role = "system"

    message = DisputeMessage.objects.create(
        dispute=dispute,
        sender=sender,
        sender_role=sender_role,
        content=content,
        is_internal=is_internal,
        attachment=attachment or "",
    )

    # Notifier les autres parties
    if not is_internal:
        _notify_new_dispute_message(dispute, sender)

    return message


def get_dispute_stats():
    """Retourne des statistiques sur les litiges pour le dashboard admin."""
    from django.db.models import Count, Q, Avg

    now = timezone.now()
    stats = Dispute.objects.aggregate(
        total=Count("id"),
        opened=Count("id", filter=Q(status="opened")),
        under_review=Count("id", filter=Q(status="under_review")),
        mediation=Count("id", filter=Q(status="mediation")),
        escalated=Count("id", filter=Q(status="escalated")),
        resolved=Count("id", filter=Q(status="resolved")),
        closed=Count("id", filter=Q(status="closed")),
        overdue=Count("id", filter=Q(
            deadline__lt=now,
            status__in=["opened", "under_review", "mediation", "escalated"],
        )),
        urgent=Count("id", filter=Q(
            priority="urgent",
            status__in=["opened", "under_review", "mediation", "escalated"],
        )),
    )

    # Temps moyen de resolution (en jours)
    resolved = Dispute.objects.filter(resolved_at__isnull=False)
    if resolved.exists():
        from django.db.models import F, ExpressionWrapper, DurationField
        avg_resolution = resolved.annotate(
            duration=ExpressionWrapper(
                F("resolved_at") - F("created_at"),
                output_field=DurationField(),
            )
        ).aggregate(avg=Avg("duration"))
        stats["avg_resolution_days"] = avg_resolution["avg"].days if avg_resolution["avg"] else 0
    else:
        stats["avg_resolution_days"] = 0

    return stats


# ──────────────────────────────────────────────
# Fonctions internes
# ──────────────────────────────────────────────

def _initiate_refund(dispute, actor):
    """Initie le processus de remboursement."""
    tx = dispute.transaction
    TransactionEvent.objects.create(
        transaction=tx,
        event_type=TransactionEvent.EventType.REFUND_INITIATED,
        old_status=tx.status,
        new_status=tx.status,
        actor=actor,
        description=f"Remboursement initie : {dispute.refund_amount:,.0f} FCFA (litige {dispute.reference})",
        metadata={
            "dispute_id": str(dispute.pk),
            "refund_amount": str(dispute.refund_amount),
        },
    )
    logger.info(
        "Remboursement initie pour litige %s : %s FCFA",
        dispute.reference, dispute.refund_amount,
    )


def _resume_transaction(transaction, actor, notes):
    """Reprend une transaction apres resolution de litige."""
    # Trouver le statut precedent avant le litige
    last_event = TransactionEvent.objects.filter(
        transaction=transaction,
        new_status="disputed",
    ).order_by("-created_at").first()

    previous_status = last_event.old_status if last_event else "reserved"

    # Verifier que la transition est possible
    from .transaction_service import VALID_TRANSITIONS
    allowed = VALID_TRANSITIONS.get("disputed", [])
    if previous_status not in allowed:
        # Fallback : completer la transaction
        previous_status = "completed"

    try:
        transition_status(
            transaction, previous_status, actor,
            f"Transaction reprise apres litige. {notes}",
        )
    except ValueError as e:
        logger.error("Impossible de reprendre la transaction %s : %s", transaction.reference, e)


def _notify_dispute_opened(dispute):
    """Notifie les parties d'un nouveau litige."""
    try:
        from notifications.services import send_notification

        tx = dispute.transaction
        parties = set()
        if dispute.opened_by != tx.buyer:
            parties.add(tx.buyer)
        if dispute.opened_by != tx.seller:
            parties.add(tx.seller)

        for user in parties:
            send_notification(
                recipient=user,
                notification_type="transaction_status",
                title=f"Litige ouvert — {tx.reference}",
                message=(
                    f"Un litige a ete ouvert pour la transaction {tx.reference} "
                    f"(parcelle {tx.parcelle.lot_number}). "
                    f"Sujet : {dispute.subject}. "
                    f"Consultez votre espace pour plus de details."
                ),
                data={
                    "dispute_id": str(dispute.pk),
                    "transaction_id": str(tx.pk),
                    "action_url": f"/transactions/{tx.pk}/litiges/{dispute.pk}/",
                },
            )

        # Notifier les admins
        from django.contrib.auth import get_user_model
        User = get_user_model()
        for admin_user in User.objects.filter(is_staff=True):
            send_notification(
                recipient=admin_user,
                notification_type="transaction_status",
                title=f"Nouveau litige — {dispute.reference}",
                message=(
                    f"Litige {dispute.reference} ouvert pour TX {tx.reference}. "
                    f"Categorie : {dispute.get_category_display()}. "
                    f"Priorite : {dispute.get_priority_display()}."
                ),
                data={
                    "dispute_id": str(dispute.pk),
                    "action_url": f"/admin/transactions/dispute/{dispute.pk}/change/",
                },
                channels=["inapp", "email"],
            )

    except Exception as e:
        logger.error("Erreur notification litige ouvert : %s", e)


def _notify_dispute_status_change(dispute, old_status, new_status, notes):
    """Notifie du changement de statut du litige."""
    try:
        from notifications.services import send_notification

        tx = dispute.transaction
        for user in [tx.buyer, tx.seller]:
            send_notification(
                recipient=user,
                notification_type="transaction_status",
                title=f"Litige {dispute.reference} — Mise a jour",
                message=(
                    f"Le litige {dispute.reference} est passe en statut : "
                    f"{dispute.get_status_display()}. {notes}"
                ),
                data={
                    "dispute_id": str(dispute.pk),
                    "transaction_id": str(tx.pk),
                },
            )
    except Exception as e:
        logger.error("Erreur notification changement statut litige : %s", e)


def _notify_mediator_assigned(dispute, mediator):
    """Notifie le mediateur de son assignation."""
    try:
        from notifications.services import send_notification

        tx = dispute.transaction
        send_notification(
            recipient=mediator,
            notification_type="transaction_status",
            title=f"Litige assigne — {dispute.reference}",
            message=(
                f"Vous avez ete assigne au litige {dispute.reference} "
                f"(transaction {tx.reference}). "
                f"Categorie : {dispute.get_category_display()}. "
                f"Priorite : {dispute.get_priority_display()}."
            ),
            data={
                "dispute_id": str(dispute.pk),
                "action_url": f"/admin/transactions/dispute/{dispute.pk}/change/",
            },
            channels=["inapp", "email"],
        )
    except Exception as e:
        logger.error("Erreur notification mediateur : %s", e)


def _notify_dispute_resolved(dispute):
    """Notifie de la resolution du litige."""
    try:
        from notifications.services import send_notification

        tx = dispute.transaction
        msg = (
            f"Le litige {dispute.reference} a ete resolu : "
            f"{dispute.get_resolution_type_display()}."
        )
        if dispute.refund_amount:
            msg += f" Remboursement prevu : {dispute.refund_amount:,.0f} FCFA."

        for user in [tx.buyer, tx.seller]:
            send_notification(
                recipient=user,
                notification_type="transaction_status",
                title=f"Litige resolu — {dispute.reference}",
                message=msg,
                data={
                    "dispute_id": str(dispute.pk),
                    "transaction_id": str(tx.pk),
                    "resolution": dispute.resolution_type,
                },
            )
    except Exception as e:
        logger.error("Erreur notification resolution litige : %s", e)


def _notify_new_dispute_message(dispute, sender):
    """Notifie les autres parties d'un nouveau message."""
    try:
        from notifications.services import send_notification

        tx = dispute.transaction
        recipients = set()
        if sender != tx.buyer:
            recipients.add(tx.buyer)
        if sender != tx.seller:
            recipients.add(tx.seller)
        if dispute.assigned_to and sender != dispute.assigned_to:
            recipients.add(dispute.assigned_to)

        sender_name = sender.get_full_name() or sender.email
        for user in recipients:
            send_notification(
                recipient=user,
                notification_type="new_message",
                title=f"Nouveau message — Litige {dispute.reference}",
                message=f"{sender_name} a envoye un message dans le litige {dispute.reference}.",
                data={
                    "dispute_id": str(dispute.pk),
                    "action_url": f"/transactions/{tx.pk}/litiges/{dispute.pk}/",
                },
                channels=["inapp"],
            )
    except Exception as e:
        logger.error("Erreur notification message litige : %s", e)
