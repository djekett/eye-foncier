"""
Commande de gestion : applique le filigrane EYE-FONCIER aux images existantes.

Usage :
    python manage.py watermark_existing              # Appliquer a toutes les images
    python manage.py watermark_existing --dry-run    # Lister sans modifier
"""
import os

from django.core.management.base import BaseCommand

from parcelles.models import ParcelleMedia
from parcelles.watermark_service import apply_watermark, is_image_file


class Command(BaseCommand):
    help = "Applique le filigrane EYE-FONCIER a toutes les images existantes des parcelles."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Lister les images sans appliquer le filigrane.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        medias = ParcelleMedia.objects.filter(
            media_type__in=["image", "plan"]
        ).select_related("parcelle")

        total = medias.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS("Aucune image trouvee."))
            return

        self.stdout.write(
            f"{'[DRY RUN] ' if dry_run else ''}"
            f"{total} image(s) a traiter..."
        )

        success = 0
        skipped = 0
        errors = 0

        for i, media in enumerate(medias.iterator(), 1):
            file_path = media.file.path if media.file else None

            if not file_path or not os.path.isfile(file_path):
                skipped += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"  [{i}/{total}] IGNORE — fichier introuvable : "
                        f"{media.title or media.pk}"
                    )
                )
                continue

            if not is_image_file(file_path):
                skipped += 1
                continue

            lot = media.parcelle.lot_number if media.parcelle else "?"

            if dry_run:
                self.stdout.write(
                    f"  [{i}/{total}] Lot {lot} — {os.path.basename(file_path)}"
                )
                success += 1
                continue

            result = apply_watermark(file_path)
            if result:
                success += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  [{i}/{total}] OK — Lot {lot} — "
                        f"{os.path.basename(file_path)}"
                    )
                )
            else:
                errors += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"  [{i}/{total}] ERREUR — Lot {lot} — "
                        f"{os.path.basename(file_path)}"
                    )
                )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"{'[DRY RUN] ' if dry_run else ''}"
                f"Termine : {success} traitee(s), "
                f"{skipped} ignoree(s), {errors} erreur(s)."
            )
        )
