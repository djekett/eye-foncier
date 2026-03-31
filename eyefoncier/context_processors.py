"""Global context processors for EYE-FONCIER."""

from django.conf import settings


def site_context(request):
    ctx = {
        "SITE_NAME": "EYE-FONCIER",
        "SITE_TAGLINE": "Plateforme WebSIG de Transaction Foncière Sécurisée",
        "DEBUG": settings.DEBUG,
        "SITE_WHATSAPP_NUMBER": getattr(settings, "SITE_WHATSAPP_NUMBER", ""),
    }

    # Compteur de notifications non lues (navbar badge)
    if hasattr(request, "user") and request.user.is_authenticated:
        from notifications.services import get_unread_count

        ctx["unread_notification_count"] = get_unread_count(request.user)

        user = request.user

        # Compteur cotations actives (acheteur)
        if user.is_acheteur:
            from transactions.cotation_models import Cotation

            ctx["active_cotations_count"] = Cotation.objects.filter(
                payer=user, status=Cotation.Status.VALIDATED,
            ).count()

        # Statut boutique (vendeur / promoteur)
        if user.is_vendeur or getattr(user, "is_promoteur", False):
            boutique = getattr(user, "boutique", None)
            ctx["has_boutique"] = boutique is not None and boutique.is_active
            ctx["user_boutique"] = boutique

        # Vérifications en attente (admin / géomètre)
        if user.is_admin_role or user.is_geometre:
            from transactions.cotation_models import VerificationRequest

            if user.is_admin_role:
                ctx["pending_verifications_count"] = VerificationRequest.objects.exclude(
                    status__in=["completed", "cancelled"],
                ).count()
            else:
                ctx["pending_verifications_count"] = VerificationRequest.objects.filter(
                    verifier=user,
                ).exclude(
                    status__in=["completed", "cancelled"],
                ).count()

    return ctx
