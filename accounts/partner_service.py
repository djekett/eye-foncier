"""
Service Partenaires — EYE-FONCIER
Workflow de leads (PartnerReferral) et calcul de commissions partenaires.
"""
import logging
from decimal import Decimal

from .models import Partner, PartnerReferral

logger = logging.getLogger(__name__)

# Transitions autorisées pour les referrals partenaires
VALID_TRANSITIONS = {
    "pending": ["contacted", "rejected"],
    "contacted": ["converted", "rejected"],
    "converted": [],
    "rejected": [],
}


def create_referral(partner, user, referral_type="", transaction=None, notes=""):
    """
    Crée une demande de mise en relation avec un partenaire.

    Returns:
        PartnerReferral instance
    """
    referral = PartnerReferral.objects.create(
        partner=partner,
        user=user,
        transaction=transaction,
        referral_type=referral_type,
        notes=notes,
    )

    # Notifier le partenaire par email
    _notify_partner_new_lead(referral)

    logger.info(
        "Referral créé : %s → %s (type: %s)",
        user.email, partner.name, referral_type,
    )
    return referral


def update_referral_status(referral, new_status, notes=""):
    """
    Met à jour le statut d'un referral avec validation des transitions.

    Raises:
        ValueError si la transition n'est pas autorisée.
    """
    old_status = referral.status
    allowed = VALID_TRANSITIONS.get(old_status, [])

    if new_status not in allowed:
        raise ValueError(
            f"Transition interdite : {old_status} → {new_status}. "
            f"Transitions autorisées : {allowed}"
        )

    referral.status = new_status
    if notes:
        referral.notes = f"{referral.notes}\n[{new_status}] {notes}".strip()
    referral.save()

    # Notifier l'utilisateur du changement
    _notify_user_referral_update(referral, new_status)

    # Si converti, calculer la commission partenaire
    if new_status == PartnerReferral.Status.CONVERTED:
        compute_partner_commission(referral)

    logger.info(
        "Referral %s : %s → %s (partenaire: %s)",
        referral.pk, old_status, new_status, referral.partner.name,
    )


def compute_partner_commission(referral):
    """
    Calcule la commission pour un lead converti.
    Basé sur le commission_rate du partenaire et le montant de la transaction.
    """
    if not referral.transaction:
        logger.info("Pas de transaction liée au referral %s, pas de commission", referral.pk)
        return Decimal("0")

    partner = referral.partner
    if partner.commission_rate <= 0:
        return Decimal("0")

    commission = (referral.transaction.amount * partner.commission_rate) / Decimal("100")

    logger.info(
        "Commission partenaire %s : %s FCFA (taux: %s%%, TX: %s)",
        partner.name, commission, partner.commission_rate,
        referral.transaction.reference,
    )
    return commission


def get_partner_stats(partner):
    """Statistiques d'un partenaire."""
    referrals = partner.referrals.all()

    return {
        "total_leads": referrals.count(),
        "pending": referrals.filter(status=PartnerReferral.Status.PENDING).count(),
        "contacted": referrals.filter(status=PartnerReferral.Status.CONTACTED).count(),
        "converted": referrals.filter(status=PartnerReferral.Status.CONVERTED).count(),
        "rejected": referrals.filter(status=PartnerReferral.Status.REJECTED).count(),
        "conversion_rate": _compute_conversion_rate(referrals),
    }


def _compute_conversion_rate(referrals):
    total = referrals.exclude(status=PartnerReferral.Status.PENDING).count()
    if total == 0:
        return 0
    converted = referrals.filter(status=PartnerReferral.Status.CONVERTED).count()
    return round((converted / total) * 100, 1)


def _notify_partner_new_lead(referral):
    """Notifie le partenaire d'un nouveau lead par email."""
    try:
        from django.core.mail import send_mail
        from django.conf import settings as django_settings

        if not referral.partner.contact_email:
            return

        user_name = referral.user.get_full_name() or referral.user.email
        send_mail(
            subject=f"[EYE-FONCIER] Nouveau lead — {referral.get_referral_type_display() if referral.referral_type else 'Contact'}",
            message=(
                f"Bonjour {referral.partner.name},\n\n"
                f"Un utilisateur souhaite être mis en relation avec vous.\n\n"
                f"Contact : {user_name}\n"
                f"Email : {referral.user.email}\n"
                f"Téléphone : {referral.user.phone or 'Non renseigné'}\n"
                f"Type : {referral.referral_type or 'Contact général'}\n"
                f"Notes : {referral.notes or 'Aucune'}\n\n"
                f"Connectez-vous à EYE-FONCIER pour gérer ce lead.\n\n"
                f"Cordialement,\nL'équipe EYE-FONCIER"
            ),
            from_email=getattr(django_settings, "DEFAULT_FROM_EMAIL", "noreply@eye-foncier.com"),
            recipient_list=[referral.partner.contact_email],
            fail_silently=True,
        )
    except Exception as e:
        logger.error("Erreur notification partenaire : %s", e)


def _notify_user_referral_update(referral, new_status):
    """Notifie l'utilisateur du changement de statut de sa demande."""
    try:
        from notifications.services import send_notification

        messages = {
            "contacted": (
                f"Le partenaire {referral.partner.name} a pris en charge votre demande. "
                f"Vous serez contacté prochainement."
            ),
            "converted": (
                f"Votre mise en relation avec {referral.partner.name} a abouti. "
                f"Merci de votre confiance !"
            ),
            "rejected": (
                f"Votre demande auprès de {referral.partner.name} n'a pas pu aboutir. "
                f"N'hésitez pas à consulter d'autres partenaires."
            ),
        }

        msg = messages.get(new_status)
        if msg:
            send_notification(
                recipient=referral.user,
                notification_type="system",
                title=f"Mise à jour — {referral.partner.name}",
                message=msg,
                data={
                    "partner_id": str(referral.partner.pk),
                    "referral_id": str(referral.pk),
                },
            )
    except Exception as e:
        logger.error("Erreur notification utilisateur referral : %s", e)
