"""
Signals Transactions — EYE-FONCIER
Auto-notifications et effets de bord sur les événements transactionnels.
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import BonDeVisite, TransactionApproval

logger = logging.getLogger(__name__)


@receiver(post_save, sender=BonDeVisite)
def notify_on_visit_request(sender, instance, created, **kwargs):
    """Notifie le propriétaire quand un bon de visite est créé ou mis à jour."""
    try:
        from notifications.services import send_notification
    except ImportError:
        return

    parcelle = instance.parcelle
    owner = parcelle.owner
    visitor_name = instance.visitor.get_full_name() or instance.visitor.email

    if created:
        send_notification(
            recipient=owner,
            notification_type="visit_request",
            title="Nouvelle demande de visite",
            message=(
                f"{visitor_name} souhaite visiter votre parcelle {parcelle.lot_number} "
                f"le {instance.visit_date:%d/%m/%Y à %H:%M}."
            ),
            data={
                "parcelle_id": str(parcelle.pk),
                "parcelle_lot": parcelle.lot_number,
                "visitor_name": visitor_name,
                "visit_id": str(instance.pk),
                "action_url": f"/transactions/visite/{instance.pk}/",
            },
        )
        logger.info("Notification visite envoyée à %s pour parcelle %s", owner, parcelle.lot_number)

    elif instance.status == BonDeVisite.Status.APPROVED:
        send_notification(
            recipient=instance.visitor,
            notification_type="visit_confirmed",
            title="Visite approuvée",
            message=(
                f"Votre visite pour la parcelle {parcelle.lot_number} "
                f"le {instance.visit_date:%d/%m/%Y à %H:%M} a été approuvée."
            ),
            data={
                "parcelle_id": str(parcelle.pk),
                "parcelle_lot": parcelle.lot_number,
                "visit_id": str(instance.pk),
                "action_url": f"/transactions/visite/{instance.pk}/",
            },
        )


@receiver(post_save, sender=TransactionApproval)
def notify_on_approval_change(sender, instance, created, **kwargs):
    """Notifie les parties quand une approbation est créée ou traitée."""
    try:
        from notifications.services import send_notification
    except ImportError:
        return

    transaction = instance.transaction
    ref = transaction.reference
    lot = transaction.parcelle.lot_number
    operation_label = instance.get_operation_type_display()

    if created and instance.status == TransactionApproval.Status.PENDING:
        # Déterminer le destinataire de l'approbation
        if instance.operation_type == TransactionApproval.OperationType.COMPROMIS:
            recipient = transaction.buyer
        else:
            recipient = transaction.seller

        send_notification(
            recipient=recipient,
            notification_type="transaction_status",
            title=f"Approbation requise — {operation_label}",
            message=(
                f"Une approbation est requise pour l'opération « {operation_label} » "
                f"sur la transaction {ref} (parcelle {lot})."
            ),
            data={
                "transaction_id": str(transaction.pk),
                "reference": ref,
                "parcelle_lot": lot,
                "operation_label": operation_label,
                "approval_id": str(instance.pk),
                "action_url": f"/transactions/{transaction.pk}/",
                "email_template": "notifications/email/approval_requested.html",
            },
        )

    elif instance.status in (
        TransactionApproval.Status.APPROVED,
        TransactionApproval.Status.REJECTED,
    ):
        result = "approuvée" if instance.status == TransactionApproval.Status.APPROVED else "refusée"
        send_notification(
            recipient=instance.requested_by,
            notification_type="transaction_status",
            title=f"Approbation {result} — {operation_label}",
            message=(
                f"L'opération « {operation_label} » pour la transaction {ref} "
                f"(parcelle {lot}) a été {result}."
            ),
            data={
                "transaction_id": str(transaction.pk),
                "reference": ref,
                "parcelle_lot": lot,
                "operation_label": operation_label,
                "result": instance.status,
                "action_url": f"/transactions/{transaction.pk}/",
                "email_template": "notifications/email/approval_result.html",
            },
        )


@receiver(post_save, sender="transactions.Transaction")
def handle_transaction_completed(sender, instance, **kwargs):
    """Déclenche les actions post-finalisation (commissions ambassadeur)."""
    if instance.status != "completed":
        return

    # Calculer les commissions ambassadeur si applicable
    try:
        from accounts.ambassador_service import process_transaction_commission
        process_transaction_commission(instance)
    except ImportError:
        pass
    except Exception as e:
        logger.error("Erreur calcul commission ambassadeur pour %s : %s", instance.reference, e)


# ── Signals Cotation & Vérification ──

@receiver(post_save, sender="transactions.VerificationRequest")
def handle_verification_status_change(sender, instance, **kwargs):
    """
    Actions automatiques sur changement de statut de vérification :
    - docs_watermarked → appliquer le filigrane Eye-Africa sur les documents
    - completed → notifier les deux parties
    """
    if instance.status == "docs_watermarked":
        _apply_watermarks_to_parcelle_docs(instance)

    elif instance.status == "completed":
        _notify_verification_completed(instance)


def _apply_watermarks_to_parcelle_docs(verification):
    """Applique le filigrane Eye-Africa sur tous les documents de la parcelle."""
    try:
        from parcelles.watermark_service import apply_watermark
        from documents.models import ParcelleDocument
        import os

        parcelle = verification.parcelle
        docs = ParcelleDocument.objects.filter(parcelle=parcelle)

        watermarked_count = 0
        for doc in docs:
            if doc.file and os.path.isfile(doc.file.path):
                success = apply_watermark(doc.file.path)
                if success:
                    watermarked_count += 1

        logger.info(
            "Filigrane appliqué sur %d/%d documents de la parcelle %s",
            watermarked_count, docs.count(), parcelle.lot_number,
        )

    except Exception as e:
        logger.error(
            "Erreur application filigrane pour vérification %s : %s",
            verification.reference, e,
        )


def _notify_verification_completed(verification):
    """Notifie acheteur et vendeur que la vérification est terminée."""
    try:
        from notifications.services import send_notification

        parcelle = verification.parcelle

        # Notification acheteur
        send_notification(
            recipient=verification.buyer,
            notification_type="verification_completed",
            title=f"Vérification terminée — {parcelle.lot_number}",
            message=(
                f"La vérification de la parcelle {parcelle.lot_number} est terminée. "
                f"Rendez-vous dans les locaux Eye-Foncier pour l'achat définitif."
            ),
            data={
                "parcelle_id": str(parcelle.pk),
                "verification_id": str(verification.pk),
                "action_url": f"/transactions/verifications/{verification.pk}/",
                "email_template": "notifications/email/verification_completed.html",
            },
        )

        # Notification vendeur
        send_notification(
            recipient=verification.seller,
            notification_type="verification_completed",
            title=f"Vérification terminée — {parcelle.lot_number}",
            message=(
                f"La vérification de votre parcelle {parcelle.lot_number} est terminée. "
                f"L'acheteur sera convié dans les locaux Eye-Foncier pour finaliser."
            ),
            data={
                "parcelle_id": str(parcelle.pk),
                "verification_id": str(verification.pk),
                "email_template": "notifications/email/verification_completed.html",
            },
        )

    except Exception as e:
        logger.error("Erreur notification vérification complétée : %s", e)
