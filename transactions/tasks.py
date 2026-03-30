"""
Taches Celery — Transactions EYE-FONCIER
Gestion automatique des delais, expirations et rappels.
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════
# ESCROW TIMEOUT — Expiration automatique
# ══════════════════════════════════════════════════

@shared_task(ignore_result=True)
def check_escrow_timeouts():
    """
    Tache periodique : verifie les transactions avec sequestre en attente.

    Regles :
    1. Reservation sans escrow > 7 jours → rappel
    2. Reservation sans escrow > 14 jours → annulation automatique
    3. Escrow fonde sans confirmation docs > 30 jours → rappel
    4. Escrow fonde sans confirmation docs > 60 jours → escalade admin
    """
    from .models import Transaction
    now = timezone.now()

    # ── 1. Reservations sans escrow (rappel a J+7) ──
    seven_days_ago = now - timedelta(days=7)
    stale_reservations = Transaction.objects.filter(
        status="reserved",
        escrow_funded=False,
        reserved_at__lt=seven_days_ago,
        reserved_at__gt=seven_days_ago - timedelta(days=1),  # Rappel une seule fois
    ).select_related("buyer", "seller", "parcelle")

    for tx in stale_reservations:
        _send_escrow_reminder(tx, days=7)
        logger.info("Rappel escrow envoye pour TX %s (J+7)", tx.reference)

    # ── 2. Reservations sans escrow > 14 jours → annulation ──
    fourteen_days_ago = now - timedelta(days=14)
    expired_reservations = Transaction.objects.filter(
        status="reserved",
        escrow_funded=False,
        reserved_at__lt=fourteen_days_ago,
    ).select_related("buyer", "seller", "parcelle")

    for tx in expired_reservations:
        _auto_cancel_reservation(tx)
        logger.info("Reservation expiree, TX %s annulee automatiquement", tx.reference)

    # ── 3. Escrow fonde, docs non confirmes > 30 jours → rappel ──
    thirty_days_ago = now - timedelta(days=30)
    stale_escrows = Transaction.objects.filter(
        status="escrow_funded",
        buyer_docs_confirmed=False,
        escrow_funded_at__lt=thirty_days_ago,
        escrow_funded_at__gt=thirty_days_ago - timedelta(days=1),
    ).select_related("buyer", "seller", "parcelle")

    for tx in stale_escrows:
        _send_docs_reminder(tx, days=30)
        logger.info("Rappel docs envoye pour TX %s (J+30 escrow)", tx.reference)

    # ── 4. Escrow fonde, docs non confirmes > 60 jours → escalade ──
    sixty_days_ago = now - timedelta(days=60)
    critical_escrows = Transaction.objects.filter(
        status="escrow_funded",
        buyer_docs_confirmed=False,
        escrow_funded_at__lt=sixty_days_ago,
    ).select_related("buyer", "seller", "parcelle")

    for tx in critical_escrows:
        _escalate_stale_escrow(tx)
        logger.info("Escalade admin pour TX %s (J+60 escrow sans docs)", tx.reference)

    total = (
        stale_reservations.count()
        + expired_reservations.count()
        + stale_escrows.count()
        + critical_escrows.count()
    )
    if total:
        logger.info("check_escrow_timeouts : %d transactions traitees", total)


@shared_task(ignore_result=True)
def check_dispute_deadlines():
    """
    Tache periodique : verifie les deadlines des litiges.

    Regles :
    1. Litige a J-2 de la deadline → rappel mediateur
    2. Litige depasse la deadline → escalade automatique
    """
    from .dispute_models import Dispute
    now = timezone.now()

    # ── 1. Rappel J-2 avant deadline ──
    warning_date = now + timedelta(days=2)
    upcoming_deadlines = Dispute.objects.filter(
        deadline__lte=warning_date,
        deadline__gt=now,
        status__in=["opened", "under_review", "mediation"],
    ).select_related("transaction", "assigned_to")

    for dispute in upcoming_deadlines:
        _send_deadline_reminder(dispute)
        logger.info("Rappel deadline envoye pour litige %s", dispute.reference)

    # ── 2. Litiges en retard → escalade ──
    overdue_disputes = Dispute.objects.filter(
        deadline__lt=now,
        status__in=["opened", "under_review", "mediation"],
    ).exclude(
        status="escalated",
    ).select_related("transaction", "assigned_to")

    for dispute in overdue_disputes:
        _auto_escalate_dispute(dispute)
        logger.info("Litige %s escalade automatiquement (deadline depassee)", dispute.reference)


@shared_task(ignore_result=True)
def check_cotation_expiration():
    """
    Tache periodique : expire les cotations non payees apres 48h.
    """
    from .cotation_models import Cotation
    now = timezone.now()
    cutoff = now - timedelta(hours=48)

    expired = Cotation.objects.filter(
        status="pending",
        created_at__lt=cutoff,
    )
    count = expired.update(status="expired")

    if count:
        logger.info("check_cotation_expiration : %d cotation(s) expiree(s)", count)


@shared_task(ignore_result=True)
def generate_daily_transaction_report():
    """
    Tache quotidienne : genere un rapport des transactions du jour.
    Envoye aux administrateurs.
    """
    from django.contrib.auth import get_user_model
    from django.db.models import Count, Sum
    from .models import Transaction

    User = get_user_model()
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Statistiques du jour
    stats = Transaction.objects.filter(
        created_at__gte=today_start,
    ).aggregate(
        total=Count("id"),
        total_amount=Sum("amount"),
    )

    status_counts = {}
    for s in Transaction.Status.values:
        count = Transaction.objects.filter(
            updated_at__gte=today_start,
            status=s,
        ).count()
        if count:
            status_counts[s] = count

    # Litiges ouverts aujourd'hui
    from .dispute_models import Dispute
    new_disputes = Dispute.objects.filter(created_at__gte=today_start).count()

    # Envoyer aux admins
    try:
        from notifications.services import send_notification

        message = (
            f"Rapport transactions du {now.strftime('%d/%m/%Y')} :\n"
            f"- Nouvelles transactions : {stats['total'] or 0}\n"
            f"- Volume : {stats['total_amount'] or 0:,.0f} FCFA\n"
        )
        for s, c in status_counts.items():
            message += f"- {s} : {c}\n"
        if new_disputes:
            message += f"- Nouveaux litiges : {new_disputes}\n"

        for admin_user in User.objects.filter(is_staff=True, is_active=True):
            send_notification(
                recipient=admin_user,
                notification_type="system",
                title=f"Rapport transactions — {now.strftime('%d/%m/%Y')}",
                message=message,
                channels=["inapp", "email"],
            )
    except Exception as e:
        logger.error("Erreur envoi rapport quotidien : %s", e)


# ══════════════════════════════════════════════════
# Fonctions internes
# ══════════════════════════════════════════════════

def _send_escrow_reminder(tx, days):
    """Envoie un rappel pour alimenter le sequestre."""
    try:
        from notifications.services import send_notification

        send_notification(
            recipient=tx.buyer,
            notification_type="transaction_status",
            title=f"Rappel — Sequestre en attente ({days}j)",
            message=(
                f"Votre reservation pour la parcelle {tx.parcelle.lot_number} "
                f"(Ref: {tx.reference}) attend l'alimentation du sequestre depuis {days} jours. "
                f"Montant : {tx.amount:,.0f} FCFA. "
                f"Sans action sous 7 jours, la reservation sera annulee automatiquement."
            ),
            data={
                "transaction_id": str(tx.pk),
                "action_url": f"/transactions/{tx.pk}/",
            },
        )
    except Exception as e:
        logger.error("Erreur envoi rappel escrow TX %s : %s", tx.reference, e)


def _auto_cancel_reservation(tx):
    """Annule automatiquement une reservation expiree."""
    from django.db import transaction as db_transaction
    from .transaction_service import cancel_transaction
    from .models import TransactionEvent

    try:
        with db_transaction.atomic():
            cancel_transaction(
                tx, actor=None,
                reason="Annulation automatique : sequestre non alimente sous 14 jours.",
            )
            # Creer un evenement systeme
            TransactionEvent.objects.create(
                transaction=tx,
                event_type="cancelled",
                old_status="reserved",
                new_status="cancelled",
                description="Annulation automatique : delai escrow depasse (14 jours).",
                metadata={"auto_cancelled": True, "reason": "escrow_timeout"},
            )

        # Notifier les deux parties
        from notifications.services import send_notification
        for user in [tx.buyer, tx.seller]:
            send_notification(
                recipient=user,
                notification_type="transaction_status",
                title=f"Reservation annulee — {tx.reference}",
                message=(
                    f"La reservation de la parcelle {tx.parcelle.lot_number} "
                    f"(Ref: {tx.reference}) a ete annulee automatiquement car le sequestre "
                    f"n'a pas ete alimente dans les 14 jours. "
                    f"La parcelle est de nouveau disponible."
                ),
                data={
                    "transaction_id": str(tx.pk),
                    "auto_cancelled": True,
                },
            )
    except Exception as e:
        logger.error("Erreur annulation auto TX %s : %s", tx.reference, e)


def _send_docs_reminder(tx, days):
    """Rappel pour confirmer la reception des documents."""
    try:
        from notifications.services import send_notification

        send_notification(
            recipient=tx.buyer,
            notification_type="transaction_status",
            title=f"Rappel — Confirmation documents en attente ({days}j)",
            message=(
                f"Le sequestre pour la parcelle {tx.parcelle.lot_number} "
                f"(Ref: {tx.reference}) est alimente depuis {days} jours. "
                f"Veuillez confirmer la reception des documents pour poursuivre la transaction."
            ),
            data={
                "transaction_id": str(tx.pk),
                "action_url": f"/transactions/{tx.pk}/",
            },
        )

        # Rappel au vendeur aussi
        send_notification(
            recipient=tx.seller,
            notification_type="transaction_status",
            title=f"Rappel — Documents en attente ({days}j)",
            message=(
                f"La transaction {tx.reference} attend la confirmation des documents "
                f"depuis {days} jours. Assurez-vous que les documents ont ete transmis a l'acheteur."
            ),
            data={"transaction_id": str(tx.pk)},
        )
    except Exception as e:
        logger.error("Erreur envoi rappel docs TX %s : %s", tx.reference, e)


def _escalate_stale_escrow(tx):
    """Escalade une transaction bloquee aux admins."""
    try:
        from notifications.services import send_notification
        from django.contrib.auth import get_user_model

        User = get_user_model()
        for admin_user in User.objects.filter(is_staff=True, is_active=True):
            send_notification(
                recipient=admin_user,
                notification_type="transaction_status",
                title=f"ALERTE — Transaction bloquee {tx.reference}",
                message=(
                    f"La transaction {tx.reference} (parcelle {tx.parcelle.lot_number}) "
                    f"est bloquee depuis plus de 60 jours avec un sequestre de "
                    f"{tx.escrow_amount or tx.amount:,.0f} FCFA alimente. "
                    f"Les documents n'ont pas ete confirmes. Intervention requise."
                ),
                data={
                    "transaction_id": str(tx.pk),
                    "action_url": f"/admin/transactions/transaction/{tx.pk}/change/",
                    "escalation": True,
                },
                channels=["inapp", "email"],
            )
    except Exception as e:
        logger.error("Erreur escalade TX %s : %s", tx.reference, e)


def _send_deadline_reminder(dispute):
    """Rappel de deadline pour un litige."""
    try:
        from notifications.services import send_notification

        if dispute.assigned_to:
            send_notification(
                recipient=dispute.assigned_to,
                notification_type="transaction_status",
                title=f"URGENT — Deadline litige {dispute.reference}",
                message=(
                    f"Le litige {dispute.reference} arrive a echeance le "
                    f"{dispute.deadline.strftime('%d/%m/%Y')}. "
                    f"Priorite : {dispute.get_priority_display()}."
                ),
                data={
                    "dispute_id": str(dispute.pk),
                    "action_url": f"/admin/transactions/dispute/{dispute.pk}/change/",
                },
                channels=["inapp", "email"],
            )
    except Exception as e:
        logger.error("Erreur rappel deadline litige %s : %s", dispute.reference, e)


def _auto_escalate_dispute(dispute):
    """Escalade automatique d'un litige en retard."""
    from .dispute_service import transition_dispute

    try:
        # Creer un utilisateur systeme ou utiliser None
        dispute.status = "escalated"
        dispute.escalated_at = timezone.now()
        dispute.save(update_fields=["status", "escalated_at", "updated_at"])

        # Notifier les admins
        from notifications.services import send_notification
        from django.contrib.auth import get_user_model

        User = get_user_model()
        for admin_user in User.objects.filter(is_staff=True, is_active=True):
            send_notification(
                recipient=admin_user,
                notification_type="transaction_status",
                title=f"ESCALADE AUTO — Litige {dispute.reference}",
                message=(
                    f"Le litige {dispute.reference} a ete escalade automatiquement "
                    f"(deadline depassee : {dispute.deadline.strftime('%d/%m/%Y')}). "
                    f"Transaction : {dispute.transaction.reference}."
                ),
                data={
                    "dispute_id": str(dispute.pk),
                    "action_url": f"/admin/transactions/dispute/{dispute.pk}/change/",
                },
                channels=["inapp", "email"],
            )
    except Exception as e:
        logger.error("Erreur escalade auto litige %s : %s", dispute.reference, e)
