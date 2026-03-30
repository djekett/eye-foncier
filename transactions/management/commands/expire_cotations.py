"""
Commande Django — Expiration des cotations.
Usage :
    python manage.py expire_cotations
    # En cron (tous les jours à minuit) :
    0 0 * * * cd /path/to/project && python manage.py expire_cotations
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from transactions.cotation_models import Cotation


class Command(BaseCommand):
    help = "Expire les cotations validées dont la date d'expiration est dépassée."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Afficher les cotations à expirer sans les modifier.",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        dry_run = options["dry_run"]

        expired_qs = Cotation.objects.filter(
            status=Cotation.Status.VALIDATED,
            expires_at__lt=now,
        )

        count = expired_qs.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS("Aucune cotation à expirer."))
            return

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"{count} cotation(s) à expirer (dry-run) :")
            )
            for c in expired_qs[:20]:
                self.stdout.write(
                    f"  - {c.reference} | {c.payer} | "
                    f"Expire: {c.expires_at:%d/%m/%Y} | "
                    f"Parcelle: {c.parcelle.lot_number if c.parcelle else 'Boutique'}"
                )
            return

        updated = expired_qs.update(status=Cotation.Status.EXPIRED)

        self.stdout.write(
            self.style.SUCCESS(f"{updated} cotation(s) expirée(s) avec succès.")
        )

        # Notifier les utilisateurs concernés
        for cotation in Cotation.objects.filter(
            status=Cotation.Status.EXPIRED,
            expires_at__gte=now - timezone.timedelta(days=1),
        ):
            try:
                from notifications.services import send_notification

                send_notification(
                    recipient=cotation.payer,
                    notification_type="cotation_expired",
                    title="Cotation expirée",
                    message=(
                        f"Votre cotation {cotation.reference} a expiré. "
                        f"Vous pouvez en créer une nouvelle pour continuer."
                    ),
                    data={
                        "cotation_id": str(cotation.pk),
                        "reference": cotation.reference,
                    },
                )
            except Exception:
                pass
