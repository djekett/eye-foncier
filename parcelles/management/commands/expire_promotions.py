"""
Commande de gestion : expire les promotions arrivées à échéance.

Usage : python manage.py expire_promotions
Cron  : 0 1 * * * cd /app && python manage.py expire_promotions
"""
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone

from parcelles.models import PromotionCampaign

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Expire les campagnes de promotion dont la date de fin est dépassée."

    def handle(self, *args, **options):
        now = timezone.now()
        expired = PromotionCampaign.objects.filter(
            status="active",
            end_date__lt=now,
        )
        count = expired.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS("Aucune promotion à expirer."))
            return

        for campaign in expired:
            campaign.status = "completed"
            campaign.save(update_fields=["status"])

            # Notifier le vendeur
            try:
                from notifications.services import send_notification
                send_notification(
                    recipient=campaign.parcelle.owner,
                    notification_type="transaction_status",
                    title="Promotion terminée",
                    message=(
                        f"La promotion pour votre parcelle Lot {campaign.parcelle.lot_number} "
                        f"({campaign.get_campaign_type_display()}) est terminée. "
                        f"Impressions : {campaign.impressions}, Clics : {campaign.clicks}."
                    ),
                    data={
                        "parcelle_id": str(campaign.parcelle.pk),
                        "parcelle_lot": campaign.parcelle.lot_number,
                        "campaign_type": campaign.campaign_type,
                        "impressions": campaign.impressions,
                        "clicks": campaign.clicks,
                    },
                )
            except Exception as e:
                logger.warning("Notification expiration promo échouée : %s", e)

            logger.info(
                "Promotion expirée : %s (parcelle %s)",
                campaign.pk, campaign.parcelle.lot_number,
            )

        self.stdout.write(self.style.SUCCESS(
            f"{count} promotion(s) expirée(s) avec succès."
        ))
