"""
Signaux Notifications — EYE-FONCIER
Auto-creation des preferences et declenchement des notifications
sur les evenements principaux de la plateforme.
"""
import logging

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import NotificationPreference

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Preferences automatiques a l'inscription
# ──────────────────────────────────────────────

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_notification_preferences(sender, instance, created, **kwargs):
    """Cree les preferences de notification et envoie le mail de bienvenue."""
    if created:
        NotificationPreference.objects.get_or_create(user=instance)
        # Notification de bienvenue (asynchrone si Celery dispo)
        try:
            from .tasks import send_welcome_notification
            send_welcome_notification.delay(str(instance.pk))
        except Exception:
            # Fallback synchrone
            _send_welcome_sync(instance)


# ──────────────────────────────────────────────
# Parcelle : publiee, validee, rejetee
# ──────────────────────────────────────────────

@receiver(post_save, sender="parcelles.Parcelle")
def notify_on_parcelle_change(sender, instance, created, **kwargs):
    """Notifie lors de la publication ou validation/rejet d'une parcelle."""
    if created:
        _notify_parcelle_published(instance)
    else:
        _check_parcelle_validation(instance)


# ──────────────────────────────────────────────
# Reactions sur les parcelles
# ──────────────────────────────────────────────

@receiver(post_save, sender="parcelles.ParcelleReaction")
def notify_on_parcelle_reaction(sender, instance, created, **kwargs):
    """Notifie le proprietaire quand quelqu'un reagit a sa parcelle."""
    if not created:
        return

    parcelle = instance.parcelle
    owner = parcelle.owner

    # Ne pas notifier si l'utilisateur reagit a sa propre parcelle
    if instance.user == owner:
        return

    user_name = instance.user.get_full_name() or instance.user.email
    reaction_label = instance.get_reaction_type_display()

    if instance.reaction_type == "interested":
        notification_type = "parcelle_interest"
        title = f"Nouvel interet pour {parcelle.lot_number}"
        message = (
            f"{user_name} est interesse(e) par votre parcelle {parcelle.lot_number} "
            f"({parcelle.title})."
        )
        priority = "high"
    else:
        notification_type = "new_review"
        title = f"Nouvelle reaction sur {parcelle.lot_number}"
        message = (
            f"{user_name} a reagi ({reaction_label}) a votre parcelle "
            f"{parcelle.lot_number}."
        )
        priority = "normal"

    _send_notification_safe(
        recipient=owner,
        notification_type=notification_type,
        title=title,
        message=message,
        data={
            "parcelle_id": str(parcelle.pk),
            "parcelle_lot": parcelle.lot_number,
            "user_name": user_name,
            "reaction_type": instance.reaction_type,
            "action_url": f"/parcelles/{parcelle.pk}/",
        },
        priority=priority,
    )


# ──────────────────────────────────────────────
# KYC / Profil
# ──────────────────────────────────────────────

@receiver(post_save, sender="accounts.Profile")
def notify_on_kyc_update(sender, instance, **kwargs):
    """Notifie l'utilisateur sur les changements de statut KYC."""
    if not hasattr(instance, '_kyc_status_changed'):
        return

    user = instance.user
    status = instance.kyc_status

    status_messages = {
        "submitted": (
            "Verification KYC en cours",
            "Vos documents de verification ont ete soumis et sont en cours d'examen.",
        ),
        "verified": (
            "Compte verifie !",
            "Felicitations ! Votre verification KYC a ete approuvee. "
            "Vous avez maintenant acces a toutes les fonctionnalites.",
        ),
        "rejected": (
            "Verification KYC rejetee",
            "Votre verification KYC a ete rejetee. "
            "Veuillez soumettre de nouveaux documents conformes.",
        ),
    }

    if status in status_messages:
        title, message = status_messages[status]
        _send_notification_safe(
            recipient=user,
            notification_type="kyc_update",
            title=title,
            message=message,
            data={
                "kyc_status": status,
                "action_url": "/compte/verification/",
                "email_template": "notifications/email/kyc_update.html",
            },
            priority="high" if status == "verified" else "normal",
        )


# ──────────────────────────────────────────────
# Transaction : changements de statut
# ──────────────────────────────────────────────

@receiver(post_save, sender="transactions.Transaction")
def notify_on_transaction_change(sender, instance, created, **kwargs):
    """Notifie l'acheteur et le vendeur lors des changements de statut d'une transaction."""
    if created:
        _notify_new_order(instance)
    else:
        _check_transaction_status(instance)


def _notify_new_order(transaction):
    """Notifie le vendeur qu'une nouvelle commande/reservation a ete creee."""
    parcelle = transaction.parcelle
    buyer_name = transaction.buyer.get_full_name() or transaction.buyer.email

    # Notifier le vendeur
    _send_notification_safe(
        recipient=transaction.seller,
        notification_type="new_order",
        title=f"Nouvelle reservation - {parcelle.lot_number}",
        message=(
            f"{buyer_name} souhaite reserver votre parcelle {parcelle.lot_number} "
            f"({parcelle.title}) pour {transaction.amount:,.0f} FCFA.".replace(",", " ")
        ),
        data={
            "transaction_id": str(transaction.pk),
            "reference": transaction.reference,
            "parcelle_id": str(parcelle.pk),
            "parcelle_lot": parcelle.lot_number,
            "amount": str(transaction.amount),
            "buyer_name": buyer_name,
            "action_url": f"/transactions/{transaction.pk}/",
            "email_template": "notifications/email/new_order.html",
        },
        priority="high",
    )

    # Confirmer a l'acheteur
    _send_notification_safe(
        recipient=transaction.buyer,
        notification_type="transaction_status",
        title=f"Reservation initiee - {parcelle.lot_number}",
        message=(
            f"Votre demande de reservation pour la parcelle {parcelle.lot_number} "
            f"({parcelle.title}) a ete enregistree. Ref: {transaction.reference}."
        ),
        data={
            "transaction_id": str(transaction.pk),
            "reference": transaction.reference,
            "parcelle_id": str(parcelle.pk),
            "parcelle_lot": parcelle.lot_number,
            "amount": str(transaction.amount),
            "action_url": f"/transactions/{transaction.pk}/",
            "email_template": "notifications/email/transaction_status.html",
        },
    )


def _check_transaction_status(transaction):
    """Gere les notifications selon le statut de la transaction."""
    status = transaction.status
    parcelle = transaction.parcelle
    ref = transaction.reference

    status_config = {
        "reserved": {
            "buyer": (
                f"Parcelle {parcelle.lot_number} reservee",
                f"Votre reservation pour la parcelle {parcelle.lot_number} est confirmee. "
                f"Ref: {ref}. Procedez au paiement du sequestre.",
                "high",
            ),
            "seller": (
                f"Parcelle {parcelle.lot_number} reservee",
                f"Votre parcelle {parcelle.lot_number} a ete reservee. Ref: {ref}.",
                "high",
            ),
        },
        "escrow_funded": {
            "buyer": (
                f"Sequestre alimente - {ref}",
                f"Le sequestre pour la parcelle {parcelle.lot_number} a ete alimente. "
                f"Les documents sont en cours de validation.",
                "high",
            ),
            "seller": (
                f"Sequestre alimente - {ref}",
                f"Le sequestre pour votre parcelle {parcelle.lot_number} a ete alimente "
                f"par l'acheteur. Ref: {ref}.",
                "high",
            ),
        },
        "paid": {
            "buyer": (
                f"Paiement confirme - {ref}",
                f"Votre paiement pour la parcelle {parcelle.lot_number} a ete confirme. "
                f"Montant: {transaction.amount:,.0f} FCFA.".replace(",", " "),
                "high",
            ),
            "seller": (
                f"Paiement recu - {ref}",
                f"Le paiement de {transaction.amount:,.0f} FCFA pour votre parcelle "
                f"{parcelle.lot_number} a ete confirme. Ref: {ref}.".replace(",", " "),
                "high",
            ),
        },
        "completed": {
            "buyer": (
                f"Transaction finalisee - {ref}",
                f"La transaction pour la parcelle {parcelle.lot_number} est finalisee. "
                f"Felicitations pour votre acquisition !",
                "high",
            ),
            "seller": (
                f"Vente finalisee - {ref}",
                f"La vente de votre parcelle {parcelle.lot_number} est finalisee. "
                f"Montant: {transaction.amount:,.0f} FCFA. Ref: {ref}.".replace(",", " "),
                "high",
            ),
        },
        "cancelled": {
            "buyer": (
                f"Transaction annulee - {ref}",
                f"La transaction pour la parcelle {parcelle.lot_number} a ete annulee. "
                f"Ref: {ref}.",
                "normal",
            ),
            "seller": (
                f"Transaction annulee - {ref}",
                f"La transaction pour votre parcelle {parcelle.lot_number} a ete annulee. "
                f"Ref: {ref}. Votre parcelle est de nouveau disponible.",
                "normal",
            ),
        },
        "disputed": {
            "buyer": (
                f"Litige ouvert - {ref}",
                f"Un litige a ete ouvert sur la transaction {ref} "
                f"(parcelle {parcelle.lot_number}). Notre equipe va traiter votre dossier.",
                "urgent",
            ),
            "seller": (
                f"Litige ouvert - {ref}",
                f"Un litige a ete ouvert sur la transaction {ref} "
                f"(parcelle {parcelle.lot_number}). Notre equipe va vous contacter.",
                "urgent",
            ),
        },
    }

    config = status_config.get(status)
    if not config:
        return

    base_data = {
        "transaction_id": str(transaction.pk),
        "reference": ref,
        "parcelle_id": str(parcelle.pk),
        "parcelle_lot": parcelle.lot_number,
        "amount": str(transaction.amount),
        "status": status,
        "action_url": f"/transactions/{transaction.pk}/",
    }

    notification_type_map = {
        "paid": "payment_confirmed",
        "escrow_funded": "escrow_update",
    }
    notification_type = notification_type_map.get(status, "transaction_status")

    # Notifier l'acheteur
    if "buyer" in config:
        buyer_title, buyer_msg, buyer_priority = config["buyer"]
        buyer_data = {**base_data, "email_template": "notifications/email/transaction_status.html"}
        if status == "paid":
            buyer_data["email_template"] = "notifications/email/payment_confirmed.html"
        elif status == "escrow_funded":
            buyer_data["email_template"] = "notifications/email/escrow_update.html"
        _send_notification_safe(
            recipient=transaction.buyer,
            notification_type=notification_type,
            title=buyer_title,
            message=buyer_msg,
            data=buyer_data,
            priority=buyer_priority,
        )

    # Notifier le vendeur
    if "seller" in config:
        seller_title, seller_msg, seller_priority = config["seller"]
        seller_data = {**base_data, "email_template": "notifications/email/transaction_status.html"}
        if status == "paid":
            seller_data["email_template"] = "notifications/email/payment_confirmed.html"
        _send_notification_safe(
            recipient=transaction.seller,
            notification_type=notification_type,
            title=seller_title,
            message=seller_msg,
            data=seller_data,
            priority=seller_priority,
        )


# ──────────────────────────────────────────────
# Boutique : activation, suspension
# ──────────────────────────────────────────────

@receiver(post_save, sender="transactions.Boutique")
def notify_on_boutique_change(sender, instance, created, **kwargs):
    """Notifie le proprietaire quand sa boutique change de statut."""
    if created and instance.status == "active":
        _notify_boutique_activated(instance)
    elif not created:
        _check_boutique_status(instance)


def _notify_boutique_activated(boutique):
    """Notifie le proprietaire que sa boutique est activee."""
    _send_notification_safe(
        recipient=boutique.owner,
        notification_type="boutique_activated",
        title=f"Boutique \"{boutique.name}\" activee !",
        message=(
            f"Felicitations ! Votre boutique \"{boutique.name}\" est maintenant active sur "
            f"EYE-FONCIER. Vous pouvez desormais publier vos parcelles et recevoir "
            f"des demandes de clients."
        ),
        data={
            "boutique_id": str(boutique.pk),
            "boutique_name": boutique.name,
            "boutique_slug": boutique.slug,
            "action_url": f"/compte/boutique/{boutique.slug}/",
            "email_template": "notifications/email/boutique_activated.html",
        },
        priority="high",
    )


def _check_boutique_status(boutique):
    """Verifie les changements de statut de la boutique."""
    status = boutique.status

    if status == "active":
        _notify_boutique_activated(boutique)
    elif status == "suspended":
        _send_notification_safe(
            recipient=boutique.owner,
            notification_type="boutique_update",
            title=f"Boutique \"{boutique.name}\" suspendue",
            message=(
                f"Votre boutique \"{boutique.name}\" a ete suspendue. "
                f"Veuillez contacter notre support pour plus d'informations."
            ),
            data={
                "boutique_id": str(boutique.pk),
                "boutique_name": boutique.name,
                "status": status,
                "action_url": "/compte/dashboard/",
                "email_template": "notifications/email/boutique_activated.html",
            },
            priority="urgent",
        )


# ──────────────────────────────────────────────
# Fonctions internes
# ──────────────────────────────────────────────

def _notify_parcelle_published(parcelle):
    """Notifie le proprietaire que sa parcelle est publiee."""
    _send_notification_safe(
        recipient=parcelle.owner,
        notification_type="parcelle_published",
        title=f"Parcelle {parcelle.lot_number} publiee",
        message=(
            f"Votre parcelle {parcelle.lot_number} ({parcelle.title}) a ete publiee "
            f"avec succes sur EYE-FONCIER. Elle est maintenant visible par les acheteurs."
        ),
        data={
            "parcelle_id": str(parcelle.pk),
            "parcelle_lot": parcelle.lot_number,
            "parcelle_title": parcelle.title,
            "surface": str(parcelle.surface_m2),
            "price": str(parcelle.price),
            "action_url": f"/parcelles/{parcelle.pk}/",
            "email_template": "notifications/email/parcelle_published.html",
        },
    )


def _check_parcelle_validation(parcelle):
    """Verifie si la parcelle vient d'etre validee ou rejetee."""
    # Parcelle validee
    if parcelle.is_validated and parcelle.validated_by:
        _send_notification_safe(
            recipient=parcelle.owner,
            notification_type="parcelle_validated",
            title=f"Parcelle {parcelle.lot_number} validee",
            message=(
                f"Votre parcelle {parcelle.lot_number} a ete validee par un geometre. "
                f"Elle beneficie maintenant d'un badge de confiance supplementaire."
            ),
            data={
                "parcelle_id": str(parcelle.pk),
                "parcelle_lot": parcelle.lot_number,
                "validated_by": parcelle.validated_by.get_full_name(),
                "action_url": f"/parcelles/{parcelle.pk}/",
                "email_template": "notifications/email/parcelle_validated.html",
            },
            priority="high",
        )

    # Parcelle rejetee (status = vendu avec is_validated=False, ou via _rejection_reason)
    elif hasattr(parcelle, '_rejection_reason') or (
        not parcelle.is_validated and hasattr(parcelle, '_was_pending_validation')
    ):
        reason = getattr(parcelle, '_rejection_reason', "Motif non precise.")
        _send_notification_safe(
            recipient=parcelle.owner,
            notification_type="parcelle_rejected",
            title=f"Parcelle {parcelle.lot_number} rejetee",
            message=(
                f"Votre parcelle {parcelle.lot_number} n'a pas ete validee. "
                f"Motif : {reason} "
                f"Veuillez corriger les informations et soumettre a nouveau."
            ),
            data={
                "parcelle_id": str(parcelle.pk),
                "parcelle_lot": parcelle.lot_number,
                "rejection_reason": reason,
                "action_url": f"/parcelles/{parcelle.pk}/edit/",
                "email_template": "notifications/email/parcelle_rejected.html",
            },
            priority="high",
        )


def _send_notification_safe(recipient, notification_type, title, message,
                            data=None, priority="normal"):
    """Envoie une notification de maniere securisee (try/except)."""
    try:
        from .services import send_notification
        send_notification(
            recipient=recipient,
            notification_type=notification_type,
            title=title,
            message=message,
            data=data,
            priority=priority,
        )
    except Exception as e:
        logger.error(
            "Erreur notification %s pour %s : %s",
            notification_type, recipient, e,
        )


def _send_welcome_sync(user):
    """Envoie la notification de bienvenue en mode synchrone."""
    user_name = user.first_name or user.email.split("@")[0]
    _send_notification_safe(
        recipient=user,
        notification_type="welcome",
        title="Bienvenue sur EYE-FONCIER !",
        message=(
            f"Bonjour {user_name}, votre compte a ete cree avec succes. "
            "Explorez notre plateforme pour decouvrir des parcelles de qualite "
            "et gerer vos transactions foncieres en toute securite."
        ),
        data={
            "action_url": "/compte/dashboard/",
            "email_template": "notifications/email/welcome.html",
        },
    )
