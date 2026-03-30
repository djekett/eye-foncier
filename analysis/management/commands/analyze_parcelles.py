"""
Commande de gestion : analyser toutes les parcelles.
Usage: python manage.py analyze_parcelles [--lot LOT_NUMBER]
"""
from django.core.management.base import BaseCommand
from parcelles.models import Parcelle


class Command(BaseCommand):
    help = "Lance l'analyse complète (terrain + contraintes + proximité + risques) pour les parcelles."
    
    def add_arguments(self, parser):
        parser.add_argument(
            "--lot", type=str, default=None,
            help="Numéro de lot spécifique à analyser.",
        )
        parser.add_argument(
            "--all", action="store_true",
            help="Analyser toutes les parcelles (même déjà analysées).",
        )

    def handle(self, *args, **options):
        from analysis.services.terrain_analyzer import analyze_parcelle_complete

        if options["lot"]:
            parcelles = Parcelle.objects.filter(lot_number=options["lot"])
        elif options["all"]:
            parcelles = Parcelle.objects.all()
        else:
            # Seulement les non-analysées
            parcelles = Parcelle.objects.exclude(
                terrain_analysis__isnull=False,
            )

        total = parcelles.count()
        self.stdout.write("Analyse de {} parcelle(s)...".format(total))

        success = 0
        errors = 0
        for i, parcelle in enumerate(parcelles, 1):
            try:
                result = analyze_parcelle_complete(parcelle)
                score = result["risk_assessment"].overall_score or 0
                self.stdout.write(
                    "  [{}/{}] {} — Score: {:.0f}/100".format(i, total, parcelle.lot_number, score)
                )
                success += 1
            except Exception as e:
                self.stderr.write("  [{}/{}] {} — ERREUR: {}".format(i, total, parcelle.lot_number, e))
                errors += 1

        self.stdout.write(self.style.SUCCESS(
            "Terminé : {} succès, {} erreur(s).".format(success, errors)
        ))
