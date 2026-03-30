"""
Modèles — Module Analyse SIG, Smart Matching & Rapport
EYE-FONCIER : Système d'Aide à la Décision (SAD)

MODULE 2 : Analyse Topographique & Spatiale
MODULE 1 : Smart Matching Engine
MODULE 3 : Rapport "État des Lieux"
"""
import uuid
from django.contrib.gis.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator


# ═══════════════════════════════════════════════════════════
# MODULE 2 — ANALYSE TOPOGRAPHIQUE & SPATIALE
# ═══════════════════════════════════════════════════════════

class TerrainAnalysis(models.Model):
    """Résultats de l'analyse topographique d'une parcelle (MNT/DEM).
    Calculé à partir de fichiers GeoTIFF (SRTM ou Lidar).
    """

    class SlopeCategory(models.TextChoices):
        FLAT = "flat", _("Plat (< 5%)")
        GENTLE = "gentle", _("Légère pente (5–10%)")
        MODERATE = "moderate", _("Pente modérée (10–15%)")
        STEEP = "steep", _("Forte pente (15–25%)")
        VERY_STEEP = "very_steep", _("Très forte pente (> 25%)")

    class Aspect(models.TextChoices):
        NORTH = "N", _("Nord")
        NORTHEAST = "NE", _("Nord-Est")
        EAST = "E", _("Est")
        SOUTHEAST = "SE", _("Sud-Est")
        SOUTH = "S", _("Sud")
        SOUTHWEST = "SW", _("Sud-Ouest")
        WEST = "W", _("Ouest")
        NORTHWEST = "NW", _("Nord-Ouest")
        FLAT = "FLAT", _("Plat")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parcelle = models.OneToOneField(
        "parcelles.Parcelle", on_delete=models.CASCADE,
        related_name="terrain_analysis",
    )

    # Élévation
    elevation_min = models.FloatField(_("altitude min (m)"), null=True, blank=True)
    elevation_max = models.FloatField(_("altitude max (m)"), null=True, blank=True)
    elevation_mean = models.FloatField(_("altitude moyenne (m)"), null=True, blank=True)
    elevation_range = models.FloatField(_("dénivelé (m)"), null=True, blank=True)

    # Pente
    slope_mean = models.FloatField(
        _("pente moyenne (%)"), null=True, blank=True,
        help_text=_("Inclinaison moyenne du terrain en pourcentage."),
    )
    slope_max = models.FloatField(_("pente max (%)"), null=True, blank=True)
    slope_category = models.CharField(
        _("catégorie de pente"), max_length=20,
        choices=SlopeCategory.choices, blank=True,
    )
    slope_is_constructible = models.BooleanField(
        _("constructible (pente)"), default=True,
        help_text=_("Faux si pente > 15% — coûts de construction élevés."),
    )

    # Exposition (Aspect)
    aspect_dominant = models.CharField(
        _("exposition dominante"), max_length=5,
        choices=Aspect.choices, blank=True,
    )
    solar_potential = models.FloatField(
        _("potentiel solaire (0-100)"), null=True, blank=True,
        help_text=_("Score basé sur l'exposition Sud = meilleur."),
    )

    # Hydrologie
    water_accumulation_risk = models.FloatField(
        _("risque accumulation eau (0-100)"), null=True, blank=True,
        help_text=_("Score de probabilité de stagnation d'eau en cas de pluie."),
    )
    drainage_quality = models.CharField(
        _("qualité du drainage"), max_length=20, blank=True,
        choices=[
            ("excellent", _("Excellent")),
            ("bon", _("Bon")),
            ("moyen", _("Moyen")),
            ("mauvais", _("Mauvais")),
        ],
    )

    # Score technique global
    technical_score = models.FloatField(
        _("score technique (0-100)"), null=True, blank=True,
        help_text=_("Score composite : pente + exposition + drainage + constructibilité."),
    )

    # Métadonnées
    dem_source = models.CharField(
        _("source MNT"), max_length=100, blank=True,
        help_text=_("Ex: SRTM 30m, Lidar IGN, etc."),
    )
    analyzed_at = models.DateTimeField(_("date d'analyse"), auto_now=True)
    raw_data = models.JSONField(
        _("données brutes"), default=dict, blank=True,
        help_text=_("Histogramme des pentes, stats détaillées, etc."),
    )

    class Meta:
        verbose_name = _("Analyse de terrain")
        verbose_name_plural = _("Analyses de terrain")

    def __str__(self):
        return "Terrain {} — Score {}/100".format(
            self.parcelle.lot_number,
            int(self.technical_score) if self.technical_score else "N/A",
        )


class SpatialConstraint(models.Model):
    """Contraintes spatiales détectées sur une parcelle.
    Résultat du croisement géométrique avec les couches SIG nationales.
    """

    class ConstraintType(models.TextChoices):
        FLOOD_ZONE = "flood_zone", _("Zone inondable")
        EROSION = "erosion", _("Zone d'érosion")
        POWER_LINE = "power_line", _("Servitude — Ligne haute tension")
        PIPELINE = "pipeline", _("Servitude — Pipeline/Conduite")
        GREEN_ZONE = "green_zone", _("Zone verte / non constructible")
        HERITAGE = "heritage", _("Zone patrimoine protégé")
        ROAD_SETBACK = "road_setback", _("Recul routier")
        CUSTOM = "custom", _("Autre contrainte")

    class Severity(models.TextChoices):
        INFO = "info", _("Information")
        WARNING = "warning", _("Attention")
        CRITICAL = "critical", _("Critique — Bloquant")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parcelle = models.ForeignKey(
        "parcelles.Parcelle", on_delete=models.CASCADE,
        related_name="spatial_constraints",
    )
    constraint_type = models.CharField(
        _("type de contrainte"), max_length=30,
        choices=ConstraintType.choices,
    )
    severity = models.CharField(
        _("gravité"), max_length=15, choices=Severity.choices,
    )
    description = models.TextField(_("description"), blank=True)
    affected_area_pct = models.FloatField(
        _("% surface affectée"), null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    source_layer = models.CharField(
        _("couche source"), max_length=200, blank=True,
        help_text=_("Nom du fichier ou couche SIG utilisée."),
    )
    intersection_geometry = models.GeometryField(
        _("géométrie intersection"), srid=4326, null=True, blank=True,
    )
    detected_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Contrainte spatiale")
        verbose_name_plural = _("Contraintes spatiales")
        ordering = ["-severity", "constraint_type"]

    def __str__(self):
        return "{} — {} ({})".format(
            self.parcelle.lot_number,
            self.get_constraint_type_display(),
            self.get_severity_display(),
        )


class ProximityAnalysis(models.Model):
    """Analyse de voisinage — distances aux infrastructures clés."""

    class POIType(models.TextChoices):
        ROAD = "road", _("Route bitumée")
        ELECTRICITY = "electricity", _("Réseau électrique")
        WATER = "water", _("Réseau d'eau")
        SCHOOL = "school", _("École")
        HOSPITAL = "hospital", _("Hôpital / Centre de santé")
        MARKET = "market", _("Marché")
        TRANSPORT = "transport", _("Transport public")
        POLICE = "police", _("Commissariat / Gendarmerie")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parcelle = models.ForeignKey(
        "parcelles.Parcelle", on_delete=models.CASCADE,
        related_name="proximity_analyses",
    )
    poi_type = models.CharField(
        _("type d'infrastructure"), max_length=20,
        choices=POIType.choices,
    )
    distance_m = models.FloatField(
        _("distance (mètres)"), null=True, blank=True,
        help_text=_("Distance à vol d'oiseau vers l'infrastructure la plus proche."),
    )
    poi_name = models.CharField(
        _("nom du point"), max_length=300, blank=True,
    )
    poi_location = models.PointField(
        _("localisation POI"), srid=4326, null=True, blank=True,
    )
    score = models.FloatField(
        _("score accessibilité (0-100)"), null=True, blank=True,
        help_text=_("100 = très proche, 0 = très éloigné."),
    )
    analyzed_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Analyse de proximité")
        verbose_name_plural = _("Analyses de proximité")
        unique_together = [("parcelle", "poi_type")]
        ordering = ["poi_type"]

    def __str__(self):
        dist_str = "{:,.0f}m".format(self.distance_m) if self.distance_m else "N/A"
        return "{} — {} → {}".format(
            self.parcelle.lot_number,
            self.get_poi_type_display(),
            dist_str,
        )


class RiskAssessment(models.Model):
    """Évaluation globale des risques d'une parcelle.
    Synthèse automatique de TerrainAnalysis + SpatialConstraints + Proximity.
    """

    class RiskLevel(models.TextChoices):
        LOW = "low", _("Faible")
        MEDIUM = "medium", _("Moyen")
        HIGH = "high", _("Élevé")
        CRITICAL = "critical", _("Critique")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parcelle = models.OneToOneField(
        "parcelles.Parcelle", on_delete=models.CASCADE,
        related_name="risk_assessment",
    )

    # Risques individuels
    flood_risk = models.CharField(
        _("risque inondation"), max_length=15,
        choices=RiskLevel.choices, default=RiskLevel.LOW,
    )
    erosion_risk = models.CharField(
        _("risque érosion"), max_length=15,
        choices=RiskLevel.choices, default=RiskLevel.LOW,
    )
    slope_risk = models.CharField(
        _("risque pente"), max_length=15,
        choices=RiskLevel.choices, default=RiskLevel.LOW,
    )
    legal_risk = models.CharField(
        _("risque juridique / servitudes"), max_length=15,
        choices=RiskLevel.choices, default=RiskLevel.LOW,
    )

    # Scores axes (Radar Chart)
    score_accessibility = models.FloatField(
        _("accessibilité (0-5)"), default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
    )
    score_topography = models.FloatField(
        _("topographie (0-5)"), default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
    )
    score_legal = models.FloatField(
        _("juridique (0-5)"), default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
    )
    score_environment = models.FloatField(
        _("environnement (0-5)"), default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
    )
    score_price = models.FloatField(
        _("prix (0-5)"), default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
    )

    # Score global
    overall_score = models.FloatField(
        _("score global (0-100)"), null=True, blank=True,
    )
    overall_risk = models.CharField(
        _("niveau de risque global"), max_length=15,
        choices=RiskLevel.choices, default=RiskLevel.LOW,
    )

    # Conclusion IA
    ai_conclusion = models.TextField(
        _("conclusion IA"), blank=True,
        help_text=_("Diagnostic automatique. Ex: 'Terrain idéal pour construction résidentielle'."),
    )
    recommendation = models.CharField(
        _("recommandation"), max_length=50, blank=True,
        choices=[
            ("ideal", _("Idéal — Construction immédiate")),
            ("good", _("Bon — Travaux mineurs")),
            ("caution", _("Prudence — Études complémentaires")),
            ("risky", _("Risqué — Terrassement important")),
            ("no_go", _("Déconseillé")),
        ],
    )

    assessed_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Évaluation des risques")
        verbose_name_plural = _("Évaluations des risques")

    def __str__(self):
        return "Risque {} — {} — Score {}/100".format(
            self.parcelle.lot_number,
            self.get_overall_risk_display(),
            int(self.overall_score) if self.overall_score else "N/A",
        )

    @property
    def radar_data(self):
        """Données pour le radar chart (5 axes)."""
        return {
            "Accessibilité": self.score_accessibility,
            "Topographie": self.score_topography,
            "Juridique": self.score_legal,
            "Environnement": self.score_environment,
            "Prix": self.score_price,
        }


# ═══════════════════════════════════════════════════════════
# MODULE 1 — SMART MATCHING ENGINE
# ═══════════════════════════════════════════════════════════

class BuyerProfile(models.Model):
    """Profil acheteur avancé pour le Smart Matching.
    Collecte besoins explicites et implicites.
    """

    class Lifestyle(models.TextChoices):
        URBAN = "urban", _("Urbain — Centre-ville")
        SUBURBAN = "suburban", _("Péri-urbain — Banlieue")
        RURAL = "rural", _("Rural — Campagne")
        MIXED = "mixed", _("Sans préférence")

    class RiskTolerance(models.TextChoices):
        CONSERVATIVE = "conservative", _("Conservateur — Sécurité maximale")
        MODERATE = "moderate", _("Modéré — Rapport qualité/prix")
        ADVENTUROUS = "adventurous", _("Aventurier — Opportunités")

    class ProjectType(models.TextChoices):
        RESIDENCE = "residence", _("Résidence principale")
        INVESTMENT = "investment", _("Investissement locatif")
        COMMERCIAL = "commercial", _("Projet commercial")
        AGRICULTURAL = "agricultural", _("Projet agricole")
        SPECULATIVE = "speculative", _("Achat spéculatif (revente)")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="buyer_profile",
    )

    # Budget
    budget_min = models.DecimalField(
        _("budget minimum (FCFA)"), max_digits=15, decimal_places=0,
        null=True, blank=True,
    )
    budget_max = models.DecimalField(
        _("budget maximum (FCFA)"), max_digits=15, decimal_places=0,
        null=True, blank=True,
    )

    # Surface souhaitée
    surface_min = models.DecimalField(
        _("surface min (m²)"), max_digits=12, decimal_places=2,
        null=True, blank=True,
    )
    surface_max = models.DecimalField(
        _("surface max (m²)"), max_digits=12, decimal_places=2,
        null=True, blank=True,
    )

    # Type de terrain préféré
    preferred_land_types = models.JSONField(
        _("types de terrain préférés"), default=list, blank=True,
        help_text=_('Ex: ["residentiel", "mixte"]'),
    )

    # Zones préférées
    preferred_zones = models.ManyToManyField(
        "parcelles.Zone", blank=True,
        related_name="interested_buyers",
        verbose_name=_("zones préférées"),
    )

    # Zone de recherche géographique (polygone dessiné par l'acheteur)
    search_area = models.PolygonField(
        _("zone de recherche"), srid=4326, null=True, blank=True,
        help_text=_("Polygone de la zone de recherche dessinée sur la carte."),
    )

    # Point de référence (travail, domicile actuel)
    reference_point = models.PointField(
        _("point de référence (travail/domicile)"), srid=4326,
        null=True, blank=True,
    )
    max_travel_minutes = models.PositiveIntegerField(
        _("temps de trajet max (min)"), null=True, blank=True,
        help_text=_("Temps max accepté entre le terrain et le point de référence."),
    )

    # Préférences implicites
    lifestyle = models.CharField(
        _("style de vie"), max_length=20,
        choices=Lifestyle.choices, default=Lifestyle.MIXED,
    )
    risk_tolerance = models.CharField(
        _("tolérance au risque"), max_length=20,
        choices=RiskTolerance.choices, default=RiskTolerance.MODERATE,
    )
    project_type = models.CharField(
        _("type de projet"), max_length=20,
        choices=ProjectType.choices, default=ProjectType.RESIDENCE,
    )

    # Importance des critères (pondération W)
    weight_price = models.FloatField(
        _("poids prix (Wp)"), default=0.30,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    weight_location = models.FloatField(
        _("poids localisation (Wl)"), default=0.25,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    weight_technical = models.FloatField(
        _("poids technique (Wt)"), default=0.25,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    weight_seller = models.FloatField(
        _("poids fiabilité vendeur (Wv)"), default=0.20,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )

    # Notifications
    notify_on_match = models.BooleanField(
        _("alertes opportunités"), default=True,
        help_text=_("Recevoir une alerte si un terrain > 85% de compatibilité."),
    )
    match_threshold = models.PositiveIntegerField(
        _("seuil d'alerte (%)"), default=85,
        validators=[MinValueValidator(50), MaxValueValidator(100)],
    )

    is_active = models.BooleanField(_("profil actif"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Profil acheteur")
        verbose_name_plural = _("Profils acheteurs")

    def __str__(self):
        budget_str = ""
        if self.budget_max:
            budget_str = " — Budget {:,.0f} FCFA".format(float(self.budget_max))
        return "Profil {}{}".format(self.user.get_full_name(), budget_str)


class MatchScore(models.Model):
    """Score de compatibilité entre un acheteur et une parcelle.
    S = (Wp × Sprix) + (Wl × Sloc) + (Wt × Stech) + (Wv × Svendeur)
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    buyer_profile = models.ForeignKey(
        BuyerProfile, on_delete=models.CASCADE,
        related_name="match_scores",
    )
    parcelle = models.ForeignKey(
        "parcelles.Parcelle", on_delete=models.CASCADE,
        related_name="match_scores",
    )

    # Scores composants
    score_price = models.FloatField(_("score prix (0-100)"), default=0)
    score_location = models.FloatField(_("score localisation (0-100)"), default=0)
    score_technical = models.FloatField(_("score technique (0-100)"), default=0)
    score_seller = models.FloatField(_("score vendeur (0-100)"), default=0)

    # Score final pondéré
    final_score = models.FloatField(
        _("score final (0-100)"), default=0,
        help_text=_("Score pondéré : S = Wp·Sp + Wl·Sl + Wt·St + Wv·Sv"),
    )

    # Détail du calcul
    breakdown = models.JSONField(
        _("détail du calcul"), default=dict, blank=True,
    )

    is_notified = models.BooleanField(
        _("notification envoyée"), default=False,
    )
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Score de compatibilité")
        verbose_name_plural = _("Scores de compatibilité")
        unique_together = [("buyer_profile", "parcelle")]
        ordering = ["-final_score"]
        indexes = [
            models.Index(fields=["-final_score"]),
            models.Index(fields=["buyer_profile", "-final_score"]),
        ]

    def __str__(self):
        return "{} ↔ {} : {:.0f}%".format(
            self.buyer_profile.user.get_full_name(),
            self.parcelle.lot_number,
            self.final_score,
        )

    @property
    def is_golden_opportunity(self):
        """Vrai si le score dépasse le seuil d'alerte."""
        return self.final_score >= self.buyer_profile.match_threshold


class MatchNotification(models.Model):
    """Notification « Opportunité en Or » envoyée à un acheteur."""

    class Channel(models.TextChoices):
        EMAIL = "email", _("Email")
        PUSH = "push", _("Notification Push")
        SMS = "sms", _("SMS")
        INAPP = "inapp", _("In-App")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    match_score = models.ForeignKey(
        MatchScore, on_delete=models.CASCADE,
        related_name="notifications",
    )
    channel = models.CharField(
        _("canal"), max_length=10, choices=Channel.choices, default=Channel.INAPP,
    )
    title = models.CharField(_("titre"), max_length=300)
    message = models.TextField(_("message"))
    is_read = models.BooleanField(_("lu"), default=False)
    read_at = models.DateTimeField(_("lu à"), null=True, blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Notification matching")
        verbose_name_plural = _("Notifications matching")
        ordering = ["-sent_at"]

    def __str__(self):
        return "{} → {} ({:.0f}%)".format(
            self.match_score.parcelle.lot_number,
            self.match_score.buyer_profile.user.get_full_name(),
            self.match_score.final_score,
        )


# ═══════════════════════════════════════════════════════════
# MODULE 3 — RAPPORT "ÉTAT DES LIEUX"
# ═══════════════════════════════════════════════════════════

class AnalysisReport(models.Model):
    """Certificat d'Analyse Eye-Foncier — Rapport PDF automatisé."""

    class ReportStatus(models.TextChoices):
        PENDING = "pending", _("En cours de génération")
        READY = "ready", _("Prêt")
        ERROR = "error", _("Erreur")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parcelle = models.ForeignKey(
        "parcelles.Parcelle", on_delete=models.CASCADE,
        related_name="analysis_reports",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="requested_reports",
    )

    status = models.CharField(
        _("statut"), max_length=15,
        choices=ReportStatus.choices, default=ReportStatus.PENDING,
    )

    # Fichier PDF
    pdf_file = models.FileField(
        _("rapport PDF"), upload_to="reports/analysis/%Y/%m/",
        blank=True,
    )

    # QR Code de vérification
    qr_verification_code = models.CharField(
        _("code QR vérification"), max_length=64, blank=True,
    )

    # Snapshot des données au moment du rapport
    snapshot_data = models.JSONField(
        _("données du rapport"), default=dict, blank=True,
        help_text=_("Copie des scores/risques au moment de la génération."),
    )

    generated_at = models.DateTimeField(_("date de génération"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Rapport d'analyse")
        verbose_name_plural = _("Rapports d'analyse")
        ordering = ["-created_at"]

    def __str__(self):
        return "Rapport {} — {}".format(
            self.parcelle.lot_number,
            self.get_status_display(),
        )


# ═══════════════════════════════════════════════════════════
# COUCHES SIG DE RÉFÉRENCE (données nationales)
# ═══════════════════════════════════════════════════════════

class GISReferenceLayer(models.Model):
    """Couches SIG de référence (zones inondables, servitudes, urbanisme).
    Uploadées par l'admin pour les croisements spatiaux.
    """

    class LayerType(models.TextChoices):
        FLOOD_ZONE = "flood_zone", _("Zones inondables")
        EROSION_ZONE = "erosion_zone", _("Zones d'érosion")
        POWER_LINE = "power_line", _("Lignes haute tension")
        PIPELINE = "pipeline", _("Pipelines / Conduites")
        URBAN_ZONE = "urban_zone", _("Zonage urbanisme")
        GREEN_ZONE = "green_zone", _("Zones vertes protégées")
        ROAD_NETWORK = "road_network", _("Réseau routier")
        WATER_NETWORK = "water_network", _("Réseau hydrique")
        POI = "poi", _("Points d'intérêt (écoles, hôpitaux)")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("nom de la couche"), max_length=200)
    layer_type = models.CharField(
        _("type"), max_length=30, choices=LayerType.choices,
    )
    description = models.TextField(_("description"), blank=True)
    geometry = models.GeometryCollectionField(
        _("géométries"), srid=4326, null=True, blank=True,
    )
    source_file = models.FileField(
        _("fichier source"), upload_to="gis_layers/%Y/%m/", blank=True,
    )
    buffer_distance_m = models.FloatField(
        _("distance buffer (m)"), null=True, blank=True,
        help_text=_("Zone tampon à appliquer autour de la géométrie."),
    )
    is_active = models.BooleanField(_("active"), default=True)
    metadata = models.JSONField(_("métadonnées"), default=dict, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Couche SIG de référence")
        verbose_name_plural = _("Couches SIG de référence")
        ordering = ["layer_type", "name"]

    def __str__(self):
        return "{} — {}".format(self.name, self.get_layer_type_display())
