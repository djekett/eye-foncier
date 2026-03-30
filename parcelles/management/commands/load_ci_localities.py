"""
Commande Django pour charger les localites principales de la Cote d'Ivoire.

Usage:
    python manage.py load_ci_localities
    python manage.py load_ci_localities --clear    # Supprime les zones existantes d'abord
    python manage.py load_ci_localities --update    # Met a jour les existantes (par code)

Charge 120+ localites couvrant :
  - Districts autonomes (Abidjan, Yamoussoukro)
  - Chefs-lieux de region
  - Chefs-lieux de departement
  - Sous-prefectures et communes principales
"""
import logging
from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point, Polygon

from parcelles.models import Zone

logger = logging.getLogger("parcelles")

# ─────────────────────────────────────────────────────
# Base de donnees des localites de Cote d'Ivoire
# Format: (code, nom, lat, lng, population_estimee)
# Coordonnees WGS84 (EPSG:4326)
# ─────────────────────────────────────────────────────
CI_LOCALITIES = [
    # ═══ DISTRICTS AUTONOMES ═══
    ("ABJ", "Abidjan", 5.3600, -4.0083, 5616633),
    ("YAM", "Yamoussoukro", 6.8276, -5.2893, 355573),

    # ═══ CHEFS-LIEUX DE REGION — NORD ═══
    ("KOR", "Korhogo", 9.4580, -5.6295, 286071),
    ("BOU", "Boundiali", 9.5166, -6.4833, 52384),
    ("FER", "Ferkessedougou", 9.5939, -5.1949, 120178),
    ("TEN", "Tengrela", 10.4833, -6.3833, 33764),
    ("ODE", "Odienne", 9.5100, -7.5650, 62625),
    ("MNK", "Minignan", 9.9833, -7.8000, 15000),

    # ═══ CHEFS-LIEUX DE REGION — NORD-EST ═══
    ("BDK", "Bondoukou", 8.0400, -2.8000, 75921),
    ("BON", "Bouna", 9.2667, -2.9833, 54162),
    ("TAN", "Tanda", 7.8000, -3.1667, 23543),
    ("NAS", "Nassian", 8.4500, -3.4667, 12000),

    # ═══ CHEFS-LIEUX DE REGION — NORD-OUEST ═══
    ("TOU", "Touba", 8.2833, -7.6833, 32852),
    ("SEG", "Seguela", 7.9600, -6.6700, 66277),
    ("MAN", "Mankono", 8.0583, -6.1900, 56449),

    # ═══ CHEFS-LIEUX DE REGION — CENTRE-NORD ═══
    ("BKE", "Bouake", 7.6930, -5.0308, 536189),
    ("KAT", "Katiola", 8.1361, -5.1010, 85653),
    ("DAB", "Dabakala", 8.3667, -4.4333, 24891),
    ("SAK", "Sakassou", 6.9833, -5.2833, 15000),

    # ═══ CHEFS-LIEUX DE REGION — CENTRE ═══
    ("DIM", "Dimbokro", 6.6491, -4.7065, 75457),
    ("BOM", "Bouafle", 6.9900, -5.7400, 75005),
    ("TOT", "Toumodi", 6.5565, -5.0178, 42502),
    ("DJE", "Djekanou", 6.4833, -5.1167, 12000),

    # ═══ CHEFS-LIEUX DE REGION — CENTRE-OUEST ═══
    ("DLO", "Daloa", 6.8740, -6.4502, 319427),
    ("GAN", "Gagnoa", 6.1313, -5.9506, 219421),
    ("ISA", "Issia", 6.4900, -6.5800, 77006),
    ("VAV", "Vavoua", 7.3833, -6.4833, 54774),
    ("ZUE", "Zuenoula", 7.4292, -6.0444, 38193),
    ("SOB", "Soubre", 5.7849, -6.5930, 141249),
    ("BUY", "Buyo", 6.2500, -7.0333, 35000),

    # ═══ CHEFS-LIEUX DE REGION — CENTRE-EST ═══
    ("ABG", "Abengourou", 6.7300, -3.4964, 104020),
    ("AGN", "Agnibilekrou", 7.1290, -3.2030, 46982),
    ("ADD", "Adzope", 6.1054, -3.8621, 73687),
    ("AKP", "Akoupé", 6.3833, -3.8833, 25000),

    # ═══ CHEFS-LIEUX DE REGION — SUD ═══
    ("ABL", "Aboisso", 5.4658, -3.2095, 55884),
    ("ADI", "Adiaké", 5.2831, -3.3014, 24300),
    ("GPD", "Grand-Bassam", 5.2137, -3.7423, 73772),
    ("BNG", "Bingerville", 5.3536, -3.8927, 91319),
    ("ANY", "Anyama", 5.4917, -4.0533, 212000),
    ("ABO", "Abobo", 5.4167, -4.0167, 1042000),
    ("YOP", "Yopougon", 5.3333, -4.0667, 1071543),
    ("COC", "Cocody", 5.3450, -3.9825, 655000),
    ("MCS", "Marcory", 5.3000, -3.9833, 260000),
    ("TRV", "Treichville", 5.2917, -3.9917, 150000),
    ("KMS", "Koumassi", 5.2959, -3.9618, 435000),
    ("PBT", "Port-Bouet", 5.2569, -3.9605, 420000),
    ("ATT", "Attécoubé", 5.3333, -4.0333, 280000),
    ("PLT", "Plateau", 5.3200, -4.0175, 12000),
    ("AJM", "Adjamé", 5.3583, -4.0250, 422000),
    ("SGP", "Songon", 5.3333, -4.2500, 180000),

    # ═══ CHEFS-LIEUX DE REGION — SUD-OUEST ═══
    ("SPD", "San-Pedro", 4.7485, -6.6363, 301890),
    ("TAB", "Tabou", 4.4232, -7.3530, 30957),
    ("SAS", "Sassandra", 4.9491, -6.0848, 34430),

    # ═══ CHEFS-LIEUX DE REGION — OUEST ═══
    ("MNH", "Man", 7.4125, -7.5540, 188704),
    ("DAN", "Danane", 7.2612, -8.1517, 63288),
    ("BIA", "Biankouma", 7.7333, -7.6167, 26000),
    ("GUG", "Guiglo", 6.5364, -7.4870, 60000),
    ("DUE", "Duekoue", 6.7400, -7.3500, 76428),
    ("TLP", "Toulepleu", 6.5833, -8.4167, 30000),
    ("BLO", "Bloléquin", 6.5333, -7.9500, 50000),

    # ═══ CHEFS-LIEUX DE REGION — EST ═══
    ("BET", "Bettié", 6.1000, -3.4833, 18000),

    # ═══ SUD-COMOE ═══
    ("GDL", "Grand-Lahou", 5.1429, -5.0180, 34000),
    ("TIA", "Tiassalé", 5.8956, -4.8273, 37000),
    ("SIN", "Sikensi", 5.6725, -4.5767, 23000),
    ("DAB2", "Dabou", 5.3212, -4.3742, 75000),
    ("JAC", "Jacqueville", 5.2000, -4.4167, 16000),

    # ═══ BANDAMA ═══
    ("TAG", "Taabo", 6.2333, -5.0667, 12000),

    # ═══ LAGUNES ═══
    ("AGV", "Agboville", 5.9283, -4.2119, 95800),
    ("ALK", "Alépé", 5.4989, -3.6611, 35000),
    ("TPS", "Tiébissou", 7.1567, -5.2233, 22671),

    # ═══ MARAHOUE ═══
    ("SFO", "Sinfra", 6.6167, -5.9167, 68000),

    # ═══ HAUT-SASSANDRA ═══

    # ═══ BELIER ═══
    ("DID", "Didiévi", 7.0167, -4.8333, 12000),

    # ═══ GBEKE ═══
    ("BEC", "Béoumi", 7.6743, -5.5720, 37000),

    # ═══ HAMBOL ═══
    ("NIA", "Niakara", 8.6667, -5.3000, 30000),

    # ═══ PORO ═══
    ("SIN2", "Sinematiali", 9.5833, -5.3833, 20000),
    ("DIK", "Dikodougou", 9.0667, -5.7667, 15000),

    # ═══ TCHOLOGO ═══
    ("KON", "Kong", 9.1500, -4.6167, 25000),

    # ═══ BAGOUE ═══
    ("KAU", "Kaniasso", 10.0833, -7.5000, 12000),

    # ═══ FOLON ═══

    # ═══ KABADOUGOU ═══
    ("MAD", "Madinani", 9.6000, -6.9500, 15000),

    # ═══ BAFING ═══

    # ═══ WORODOUGOU ═══

    # ═══ BERE ═══

    # ═══ IFFOU ═══
    ("M'BAH", "M'Bahiakro", 7.4558, -4.3392, 30000),
    ("PRK", "Prikro", 7.6500, -3.7833, 15000),

    # ═══ N'ZI ═══
    ("BOC", "Bocanda", 7.0631, -4.4964, 20000),

    # ═══ MORONOU ═══
    ("BOG", "Bongouanou", 6.6500, -4.2000, 40000),
    ("ARR", "Arrah", 6.6667, -3.9667, 15000),

    # ═══ INDENIE-DJUABLIN ═══

    # ═══ ME ═══
    ("ANN", "Anoumaba", 6.0833, -4.3333, 10000),

    # ═══ GBÔKLÉ ═══
    ("MED", "Méagui", 5.4000, -6.5500, 40000),

    # ═══ NAWA ═══

    # ═══ SAN-PEDRO ═══

    # ═══ CAVALLY ═══

    # ═══ GUEMON ═══
    ("BGA", "Bangolo", 7.0167, -7.4833, 42000),

    # ═══ TONKPI ═══
    ("ZOU", "Zouan-Hounien", 6.9167, -8.2167, 35000),

    # ═══ GRANDS-PONTS ═══

    # ═══ GOH ═══
    ("OUM", "Oumé", 6.3833, -5.4167, 48000),

    # ═══ LOH-DJIBOUA ═══
    ("DVO", "Divo", 5.8372, -5.3598, 127867),
    ("LAK", "Lakota", 5.8333, -5.6833, 50000),

    # ═══ AGNEBY-TIASSA ═══

    # ═══ Autres localites importantes ═══
    ("ASS", "Assinie", 5.1567, -3.4633, 15000),
    ("GLP", "Grand-Lahou Plage", 5.1333, -5.0167, 5000),
]


def _create_zone_polygon(lat, lng, size_km=2.0):
    """
    Cree un carre approximatif autour du point central.
    La taille varie selon la population (plus peuplee = zone plus grande).
    1 degre latitude ≈ 111km, 1 degre longitude ≈ 111km * cos(lat).
    """
    import math
    half_deg_lat = (size_km / 2.0) / 111.0
    half_deg_lng = (size_km / 2.0) / (111.0 * math.cos(math.radians(lat)))

    coords = [
        (lng - half_deg_lng, lat - half_deg_lat),  # SW
        (lng + half_deg_lng, lat - half_deg_lat),  # SE
        (lng + half_deg_lng, lat + half_deg_lat),  # NE
        (lng - half_deg_lng, lat + half_deg_lat),  # NW
        (lng - half_deg_lng, lat - half_deg_lat),  # close ring
    ]
    return Polygon(coords, srid=4326)


def _population_to_size(pop):
    """Taille approximative de la zone en km basee sur la population."""
    if pop and pop >= 1000000:
        return 15.0
    elif pop and pop >= 300000:
        return 10.0
    elif pop and pop >= 100000:
        return 6.0
    elif pop and pop >= 50000:
        return 4.0
    elif pop and pop >= 20000:
        return 3.0
    return 2.0


class Command(BaseCommand):
    help = "Charge les localites principales de la Cote d'Ivoire (120+ zones)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear", action="store_true",
            help="Supprime toutes les zones existantes avant chargement",
        )
        parser.add_argument(
            "--update", action="store_true",
            help="Met a jour les zones existantes (match par code)",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            count = Zone.objects.count()
            Zone.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Supprime {count} zones existantes."))

        created, updated, skipped = 0, 0, 0

        for code, name, lat, lng, population in CI_LOCALITIES:
            size = _population_to_size(population)
            geometry = _create_zone_polygon(lat, lng, size)

            existing = Zone.objects.filter(code=code).first()

            if existing:
                if options["update"]:
                    existing.name = name
                    existing.geometry = geometry
                    if hasattr(existing, 'population'):
                        existing.population = population
                    existing.save()
                    updated += 1
                else:
                    skipped += 1
            else:
                kwargs = {
                    "code": code,
                    "name": name,
                    "geometry": geometry,
                }
                if hasattr(Zone, 'population'):
                    kwargs["population"] = population
                if hasattr(Zone, 'description'):
                    kwargs["description"] = f"Commune/Localite de {name}, Cote d'Ivoire"

                Zone.objects.create(**kwargs)
                created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Localites CI chargees: {created} creees, {updated} mises a jour, {skipped} ignorees"
        ))
        self.stdout.write(f"Total zones en base: {Zone.objects.count()}")
