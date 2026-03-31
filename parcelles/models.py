"""
Modeles GIS — EYE-FONCIER
Zone > Ilot > Parcelle avec geometries PostGIS
"""
import uuid
from django.contrib.gis.db import models
from django.db.models import Count, Q, Subquery, OuterRef
from django.utils.translation import gettext_lazy as _
from django.conf import settings


class ParcelleQuerySet(models.QuerySet):
    """QuerySet optimise pour eviter les N+1 queries."""

    def with_likes_count(self):
        """Annote le nombre de likes (evite N+1 sur likes_count property)."""
        return self.annotate(
            _likes_count=Count(
                "reactions",
                filter=Q(reactions__reaction_type="like"),
            )
        )

    def with_main_image(self):
        """Prefetch la premiere image (evite N+1 sur main_image property)."""
        from django.db.models import Prefetch
        return self.prefetch_related(
            Prefetch(
                "medias",
                queryset=ParcelleMedia.objects.filter(media_type="image").order_by("created_at"),
                to_attr="_prefetched_images",
            )
        )

    def optimized(self):
        """Applique toutes les optimisations standard."""
        return self.with_likes_count().with_main_image().select_related("zone", "owner")


class Zone(models.Model):
    """Zone géographique (Quartier / Ville)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("nom de la zone"), max_length=200)
    code = models.CharField(_("code zone"), max_length=20, unique=True)
    description = models.TextField(_("description"), blank=True)
    geometry = models.PolygonField(_("géométrie"), srid=4326)
    population = models.PositiveIntegerField(_("population estimée"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Zone")
        verbose_name_plural = _("Zones")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class Ilot(models.Model):
    """Îlot — groupement de lots dans une zone."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name="ilots")
    name = models.CharField(_("nom de l'îlot"), max_length=200)
    code = models.CharField(_("code îlot"), max_length=30, unique=True)
    geometry = models.MultiPolygonField(_("géométrie"), srid=4326)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Îlot")
        verbose_name_plural = _("Îlots")
        ordering = ["zone", "name"]

    def __str__(self):
        return f"Îlot {self.code} — {self.zone.name}"

    @property
    def parcelle_count(self):
        """Nombre de parcelles dans l'ilot.

        Utilise l'annotation _parcelle_count si disponible (QuerySet optimise),
        sinon fallback vers une requete COUNT.
        """
        if hasattr(self, "_parcelle_count"):
            return self._parcelle_count
        return self.parcelles.count()


class Parcelle(models.Model):
    """Parcelle — unité foncière de vente."""

    class Status(models.TextChoices):
        DISPONIBLE = "disponible", _("● Disponible")
        RESERVE = "reserve", _("◉ Réservé")
        VENDU = "vendu", _("○ Vendu")

    class LandType(models.TextChoices):
        RESIDENTIAL = "residentiel", _("Résidentiel")
        COMMERCIAL = "commercial", _("Commercial")
        INDUSTRIAL = "industriel", _("Industriel")
        AGRICULTURAL = "agricole", _("Agricole")
        MIXED = "mixte", _("Mixte")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="parcelles",
        verbose_name=_("propriétaire"),
    )
    ilot = models.ForeignKey(
        Ilot, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="parcelles", verbose_name=_("îlot"),
    )
    zone = models.ForeignKey(
        Zone, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="parcelles", verbose_name=_("zone"),
    )

    # Lotissement (optionnel — parcelle issue d'un morcellement)
    lotissement = models.ForeignKey(
        "Lotissement", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="parcelles", verbose_name=_("lotissement"),
    )

    # Identifiants
    lot_number = models.CharField(_("numéro de lot"), max_length=50, unique=True)
    title = models.CharField(_("titre"), max_length=300)
    description = models.TextField(_("description"), blank=True)

    # Caractéristiques
    land_type = models.CharField(
        _("type de terrain"), max_length=20,
        choices=LandType.choices, default=LandType.RESIDENTIAL,
    )
    surface_m2 = models.DecimalField(
        _("surface (m²)"), max_digits=12, decimal_places=2,
    )
    price = models.DecimalField(
        _("prix (FCFA)"), max_digits=15, decimal_places=0,
    )
    price_per_m2 = models.DecimalField(
        _("prix au m² (FCFA)"), max_digits=12, decimal_places=0,
        null=True, blank=True,
    )

    # Statut
    status = models.CharField(
        _("statut"), max_length=20,
        choices=Status.choices, default=Status.DISPONIBLE,
    )
    is_validated = models.BooleanField(_("validé par géomètre"), default=False)
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="validated_parcelles",
    )
    validated_at = models.DateTimeField(null=True, blank=True)

    # Géométrie
    geometry = models.PolygonField(_("géométrie de la parcelle"), srid=4326)
    centroid = models.PointField(_("centroïde"), srid=4326, null=True, blank=True)
    address = models.CharField(_("adresse"), max_length=500, blank=True)

    # Badge de confiance
    title_holder_name = models.CharField(
        _("nom sur le titre foncier"), max_length=200, blank=True,
        help_text=_("Nom exact figurant sur le titre foncier pour vérification."),
    )
    trust_badge = models.BooleanField(
        _("badge de confiance"), default=False,
        help_text=_("Vrai si le nom du titre correspond au nom du compte."),
    )

    # Informations complémentaires (enrichissement)
    ilot_number = models.CharField(
        _("numéro d'îlot"), max_length=50, blank=True,
        help_text=_("Numéro d'îlot tel qu'indiqué sur le plan cadastral."),
    )
    cadastre_ref = models.CharField(
        _("référence cadastrale"), max_length=100, blank=True,
        help_text=_("Référence officielle au cadastre."),
    )
    access_road = models.CharField(
        _("accès routier"), max_length=20, blank=True,
        choices=[
            ("bitume", _("Route bitumée")),
            ("laterite", _("Piste latéritique")),
            ("piste", _("Piste non aménagée")),
            ("aucun", _("Aucun accès direct")),
        ],
    )
    water_access = models.BooleanField(_("accès à l'eau"), null=True, blank=True)
    electricity = models.BooleanField(_("électricité disponible"), null=True, blank=True)
    topography = models.CharField(
        _("topographie"), max_length=20, blank=True,
        choices=[
            ("plat", _("Plat")),
            ("legere_pente", _("Légère pente")),
            ("vallonne", _("Vallonné")),
            ("accidente", _("Accidenté")),
        ],
    )
    soil_type = models.CharField(
        _("type de sol"), max_length=30, blank=True,
        choices=[
            ("argileux", _("Argileux")),
            ("sableux", _("Sableux")),
            ("lateritique", _("Latéritique")),
            ("rocheux", _("Rocheux")),
            ("mixte", _("Mixte")),
        ],
    )

    # Métadonnées
    views_count = models.PositiveIntegerField(_("nombre de vues"), default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Parcelle")
        verbose_name_plural = _("Parcelles")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["lot_number", "ilot"],
                name="unique_lot_per_ilot",
                condition=models.Q(ilot__isnull=False),
            ),
        ]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["zone"]),
            models.Index(fields=["price"]),
            models.Index(fields=["surface_m2"]),
            models.Index(fields=["owner"]),
            models.Index(fields=["owner", "-created_at"]),
        ]

    def __str__(self):
        return f"Lot {self.lot_number} — {self.title}"

    def clean(self):
        """Validation metier avant sauvegarde."""
        from django.core.exceptions import ValidationError

        if self.geometry:
            # Valider que la geometrie est correcte (pas d'auto-intersection)
            if not self.geometry.valid:
                # Tenter de reparer automatiquement
                repaired = self.geometry.buffer(0)
                if repaired.valid:
                    self.geometry = repaired
                else:
                    raise ValidationError({
                        "geometry": "La geometrie est invalide (auto-intersection detectee). "
                                    "Veuillez corriger les contours de la parcelle."
                    })

            # Surface minimum (1 m2)
            if self.geometry.area == 0:
                raise ValidationError({
                    "geometry": "La geometrie a une surface nulle. "
                                "Verifiez les coordonnees."
                })

        if self.price is not None and self.price < 0:
            raise ValidationError({"price": "Le prix ne peut pas etre negatif."})

        if self.surface_m2 is not None and self.surface_m2 <= 0:
            raise ValidationError({"surface_m2": "La surface doit etre superieure a zero."})

    def save(self, *args, **kwargs):
        # Auto-calcul du prix au m2
        if self.price and self.surface_m2 and self.surface_m2 > 0:
            self.price_per_m2 = int(self.price / self.surface_m2)
        # Auto-calcul du centroide
        if self.geometry:
            # Reparer silencieusement les geometries invalides
            if not self.geometry.valid:
                self.geometry = self.geometry.buffer(0)
            self.centroid = self.geometry.centroid
        # Badge de confiance
        if self.title_holder_name and self.owner:
            owner_name = f"{self.owner.first_name} {self.owner.last_name}".strip().lower()
            self.trust_badge = self.title_holder_name.strip().lower() == owner_name
        super().save(*args, **kwargs)

    @property
    def status_color(self):
        colors = {
            self.Status.DISPONIBLE: "#22c55e",
            self.Status.RESERVE: "#f59e0b",
            self.Status.VENDU: "#ef4444",
        }
        return colors.get(self.status, "#6b7280")

    @property
    def completeness_score(self):
        """Score de complétude 0-100 : plus la parcelle est renseignée, plus elle est fiable."""
        checks = [
            (bool(self.title), 5),
            (bool(self.description) and len(self.description) > 20, 5),
            (bool(self.lot_number), 5),
            (bool(self.ilot_number), 5),
            (bool(self.cadastre_ref), 8),
            (bool(self.address) and len(self.address) > 5, 5),
            (bool(self.land_type), 3),
            (self.surface_m2 and self.surface_m2 > 0, 5),
            (self.price and self.price > 0, 5),
            (bool(self.geometry), 10),
            (bool(self.title_holder_name), 8),
            (self.trust_badge, 8),
            (self.is_validated, 10),
            (bool(self.access_road), 3),
            (self.water_access is not None, 3),
            (self.electricity is not None, 3),
            (bool(self.topography), 3),
            (bool(self.soil_type), 3),
            (self.medias.exists() if self.pk else False, 3),
        ]
        return sum(weight for cond, weight in checks if cond)

    @property
    def completeness_label(self):
        s = self.completeness_score
        if s >= 80:
            return "Excellent"
        elif s >= 60:
            return "Bon"
        elif s >= 40:
            return "Moyen"
        elif s >= 20:
            return "Faible"
        return "Incomplet"

    # Manager optimise
    objects = ParcelleQuerySet.as_manager()

    @property
    def likes_count(self):
        """Nombre de likes. Utilise l'annotation _likes_count si disponible."""
        if hasattr(self, "_likes_count"):
            return self._likes_count
        return self.reactions.filter(reaction_type="like").count()

    @property
    def main_image(self):
        """URL de l'image principale. Utilise le prefetch si disponible."""
        if hasattr(self, "_prefetched_images"):
            images = self._prefetched_images
            return images[0].file.url if images else None
        img = self.medias.filter(media_type="image").first()
        return img.file.url if img else None


class ParcelleMedia(models.Model):
    """Médias associés à une parcelle (images, vidéos)."""

    class MediaType(models.TextChoices):
        IMAGE = "image", _("Image")
        VIDEO = "video", _("Vidéo")
        DRONE = "drone", _("Vue drone")
        PLAN = "plan", _("Plan")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parcelle = models.ForeignKey(
        Parcelle, on_delete=models.CASCADE, related_name="medias",
    )
    media_type = models.CharField(
        _("type"), max_length=10, choices=MediaType.choices, default=MediaType.IMAGE,
    )
    title = models.CharField(_("titre"), max_length=200, blank=True)
    file = models.FileField(_("fichier"), upload_to="parcelles/medias/%Y/%m/")
    thumbnail = models.ImageField(
        _("miniature"), upload_to="parcelles/thumbnails/%Y/%m/", blank=True,
    )
    order = models.PositiveSmallIntegerField(_("ordre"), default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Média parcelle")
        verbose_name_plural = _("Médias parcelles")
        ordering = ["order", "-created_at"]

    def __str__(self):
        return f"{self.media_type} — {self.parcelle.lot_number}"


# ═══════════════════════════════════════════════════════════
# RÉACTIONS SUR LES PARCELLES
# ═══════════════════════════════════════════════════════════

class ParcelleReaction(models.Model):
    """Réaction utilisateur sur une publication de parcelle."""

    class ReactionType(models.TextChoices):
        LIKE = "like", _("J'aime")
        FAVORITE = "favorite", _("Favori")
        INTERESTED = "interested", _("Intéressé")
        DISLIKE = "dislike", _("Pas intéressé")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="reactions",
    )
    parcelle = models.ForeignKey(
        Parcelle, on_delete=models.CASCADE, related_name="reactions",
    )
    reaction_type = models.CharField(
        _("type"), max_length=15, choices=ReactionType.choices,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Réaction")
        verbose_name_plural = _("Réactions")
        unique_together = [("user", "parcelle", "reaction_type")]
        ordering = ["-created_at"]

    def __str__(self):
        return "{} {} {}".format(
            self.user.get_full_name(),
            self.get_reaction_type_display(),
            self.parcelle.lot_number,
        )


# ═══════════════════════════════════════════════════════════
# PROMOTION VENDEUR
# ═══════════════════════════════════════════════════════════

class PromotionCampaign(models.Model):
    """Campagne de promotion payante pour une parcelle.
    Affichage personnalisé selon le profil acheteur (Smart Matching).
    """

    class CampaignStatus(models.TextChoices):
        DRAFT = "draft", _("Brouillon")
        PENDING_PAYMENT = "pending_payment", _("En attente de paiement")
        ACTIVE = "active", _("Active")
        PAUSED = "paused", _("En pause")
        COMPLETED = "completed", _("Terminée")
        CANCELLED = "cancelled", _("Annulée")

    class CampaignType(models.TextChoices):
        BASIC = "basic", _("Standard — 5 000 FCFA / semaine")
        PREMIUM = "premium", _("Premium — 15 000 FCFA / semaine")
        BOOST = "boost", _("Boost — 25 000 FCFA / semaine")

    PRICING = {
        "basic": 5000,
        "premium": 15000,
        "boost": 25000,
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parcelle = models.ForeignKey(
        Parcelle, on_delete=models.CASCADE, related_name="promotions",
    )
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="promotion_campaigns",
    )

    campaign_type = models.CharField(
        _("type de campagne"), max_length=15,
        choices=CampaignType.choices, default=CampaignType.BASIC,
    )
    status = models.CharField(
        _("statut"), max_length=20,
        choices=CampaignStatus.choices, default=CampaignStatus.DRAFT,
    )

    # Durée
    start_date = models.DateTimeField(_("date de début"), null=True, blank=True)
    end_date = models.DateTimeField(_("date de fin"), null=True, blank=True)
    duration_weeks = models.PositiveIntegerField(_("durée (semaines)"), default=1)

    # Paiement
    amount_paid = models.DecimalField(
        _("montant payé (FCFA)"), max_digits=12, decimal_places=0,
        null=True, blank=True,
    )
    payment_reference = models.CharField(
        _("référence paiement"), max_length=100, blank=True,
    )
    payment_method = models.CharField(
        _("mode de paiement"), max_length=30, blank=True,
        choices=[
            ("mobile_money", _("Mobile Money")),
            ("virement", _("Virement bancaire")),
            ("carte", _("Carte bancaire")),
        ],
    )

    # Ciblage (Smart Matching)
    target_zones = models.ManyToManyField(
        Zone, blank=True, related_name="targeted_promotions",
        verbose_name=_("zones ciblées"),
        help_text=_("Zones où afficher la promotion. Vide = toutes."),
    )
    target_land_types = models.JSONField(
        _("types de terrain ciblés"), default=list, blank=True,
    )
    target_budget_min = models.DecimalField(
        _("budget min cible"), max_digits=15, decimal_places=0,
        null=True, blank=True,
    )
    target_budget_max = models.DecimalField(
        _("budget max cible"), max_digits=15, decimal_places=0,
        null=True, blank=True,
    )

    # Description promotionnelle
    highlight_text = models.CharField(
        _("accroche"), max_length=200, blank=True,
        help_text=_("Texte mis en avant dans la promotion."),
    )

    # Statistiques
    impressions = models.PositiveIntegerField(_("impressions"), default=0)
    clicks = models.PositiveIntegerField(_("clics"), default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Campagne de promotion")
        verbose_name_plural = _("Campagnes de promotion")
        ordering = ["-created_at"]

    def __str__(self):
        return "Promo {} — {} ({})".format(
            self.parcelle.lot_number,
            self.get_campaign_type_display(),
            self.get_status_display(),
        )

    @property
    def unit_price(self):
        return self.PRICING.get(self.campaign_type, 5000)

    @property
    def total_price(self):
        return self.unit_price * self.duration_weeks

    @property
    def is_active(self):
        if self.status != "active":
            return False
        from django.utils import timezone
        now = timezone.now()
        if self.start_date and now < self.start_date:
            return False
        if self.end_date and now > self.end_date:
            return False
        return True

    @property
    def ctr(self):
        """Click-through rate."""
        if self.impressions == 0:
            return 0
        return round(self.clicks / self.impressions * 100, 1)


# ═══════════════════════════════════════════════════════════
# ANALYSE FONCIÈRE — État des lieux d'une parcelle
# ═══════════════════════════════════════════════════════════

class ParcelleAnalysis(models.Model):
    """Analyse complète de l'état des lieux d'une parcelle.

    Évalue la fiabilité foncière avant validation ou réservation :
    - Cohérence géométrique (surface déclarée vs calculée)
    - Détection de chevauchement avec d'autres parcelles
    - Vérification documentaire (titre foncier, attestation, etc.)
    - Contrôle terrain par un vérificateur
    - Score de fiabilité global (0-100)
    """

    class AnalysisStatus(models.TextChoices):
        PENDING = "pending", _("En attente")
        IN_PROGRESS = "in_progress", _("En cours d'analyse")
        VALIDATED = "validated", _("Validé")
        REJECTED = "rejected", _("Rejeté")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parcelle = models.OneToOneField(
        Parcelle, on_delete=models.CASCADE, related_name="analysis",
        verbose_name=_("parcelle"),
    )

    # ── Statut global ──
    status = models.CharField(
        _("statut"), max_length=20,
        choices=AnalysisStatus.choices, default=AnalysisStatus.PENDING,
    )

    # ── Scores composants (0-100 chacun) ──
    score_geometry = models.PositiveSmallIntegerField(
        _("score géométrie"), default=0,
        help_text=_("Cohérence superficie déclarée vs calculée, qualité du polygone."),
    )
    score_documents = models.PositiveSmallIntegerField(
        _("score documentaire"), default=0,
        help_text=_("Présence et qualité des documents fonciers."),
    )
    score_overlap = models.PositiveSmallIntegerField(
        _("score chevauchement"), default=0,
        help_text=_("100 = aucun chevauchement, 0 = conflit total."),
    )
    score_terrain = models.PositiveSmallIntegerField(
        _("score vérification terrain"), default=0,
        help_text=_("Note du contrôle physique par le vérificateur."),
    )
    score_ownership = models.PositiveSmallIntegerField(
        _("score propriété"), default=0,
        help_text=_("Cohérence propriétaire / historique / titre foncier."),
    )
    overall_score = models.PositiveSmallIntegerField(
        _("score global"), default=0,
        help_text=_("Score pondéré 0-100."),
    )

    # ── Détails analyse géométrique ──
    declared_surface = models.DecimalField(
        _("superficie déclarée (m²)"), max_digits=12, decimal_places=2,
        null=True, blank=True,
    )
    computed_surface = models.DecimalField(
        _("superficie calculée (m²)"), max_digits=12, decimal_places=2,
        null=True, blank=True,
    )
    surface_deviation_pct = models.DecimalField(
        _("écart superficie (%)"), max_digits=10, decimal_places=2,
        null=True, blank=True,
        help_text=_("Écart en % entre superficie déclarée et calculée."),
    )

    # ── Détection chevauchement ──
    has_overlap = models.BooleanField(_("chevauchement détecté"), default=False)
    overlap_parcelles = models.JSONField(
        _("parcelles en chevauchement"), default=list, blank=True,
        help_text=_("IDs des parcelles qui se chevauchent avec celle-ci."),
    )
    overlap_area_m2 = models.DecimalField(
        _("surface chevauchement (m²)"), max_digits=12, decimal_places=2,
        null=True, blank=True,
    )

    # ── Vérification documentaire ──
    has_titre_foncier = models.BooleanField(_("titre foncier fourni"), default=False)
    has_attestation = models.BooleanField(_("attestation fournie"), default=False)
    has_plan_cadastral = models.BooleanField(_("plan cadastral fourni"), default=False)
    has_images_terrain = models.BooleanField(_("photos terrain fournies"), default=False)
    docs_authentic = models.BooleanField(
        _("documents jugés authentiques"), null=True, blank=True,
    )
    docs_notes = models.TextField(_("notes vérification documentaire"), blank=True)

    # ── Historique propriété ──
    ownership_history = models.JSONField(
        _("historique de propriété"), default=list, blank=True,
        help_text=_("Liste [{date, owner, action, reference}]."),
    )
    ownership_verified = models.BooleanField(
        _("historique vérifié"), default=False,
    )

    # ── Contrôle terrain ──
    terrain_inspected = models.BooleanField(_("inspection terrain effectuée"), default=False)
    terrain_inspector = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="terrain_inspections",
        verbose_name=_("inspecteur terrain"),
    )
    terrain_inspection_date = models.DateTimeField(
        _("date inspection"), null=True, blank=True,
    )
    terrain_notes = models.TextField(_("rapport inspection terrain"), blank=True)
    terrain_photos = models.JSONField(
        _("photos inspection"), default=list, blank=True,
        help_text=_("URLs ou chemins des photos terrain."),
    )

    # ── Rapport final ──
    analysis_report = models.TextField(_("rapport d'analyse complet"), blank=True)
    analyzed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="analyses_performed",
        verbose_name=_("analysé par"),
    )
    analyzed_at = models.DateTimeField(_("date analyse"), null=True, blank=True)
    validated_at = models.DateTimeField(_("date validation"), null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Analyse foncière")
        verbose_name_plural = _("Analyses foncières")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Analyse {self.parcelle.lot_number} — {self.get_status_display()} ({self.overall_score}/100)"

    # ── Pondérations ──
    WEIGHTS = {
        "geometry": 0.20,
        "documents": 0.25,
        "overlap": 0.20,
        "terrain": 0.20,
        "ownership": 0.15,
    }

    def compute_overall_score(self):
        """Calcule le score global pondéré."""
        self.overall_score = int(
            self.score_geometry * self.WEIGHTS["geometry"]
            + self.score_documents * self.WEIGHTS["documents"]
            + self.score_overlap * self.WEIGHTS["overlap"]
            + self.score_terrain * self.WEIGHTS["terrain"]
            + self.score_ownership * self.WEIGHTS["ownership"]
        )
        return self.overall_score

    @property
    def reliability_grade(self):
        """Grade lisible : A/B/C/D/E."""
        s = self.overall_score
        if s >= 80:
            return "A"
        elif s >= 60:
            return "B"
        elif s >= 40:
            return "C"
        elif s >= 20:
            return "D"
        return "E"

    @property
    def reliability_label(self):
        labels = {"A": "Excellent", "B": "Bon", "C": "Moyen", "D": "Faible", "E": "Risqué"}
        return labels.get(self.reliability_grade, "Inconnu")


# ═══════════════════════════════════════════════════════════
# LOTISSEMENT — Plans de morcellement pour promoteurs
# ═══════════════════════════════════════════════════════════

class Lotissement(models.Model):
    """Plan de morcellement d'un terrain par un promoteur.

    Contient la géométrie globale et les métadonnées du lotissement.
    Les parcelles individuelles sont liées via le champ ForeignKey sur Parcelle.
    """

    class LotissementStatus(models.TextChoices):
        DRAFT = "draft", _("Brouillon")
        SUBMITTED = "submitted", _("Soumis pour validation")
        APPROVED = "approved", _("Approuvé")
        ACTIVE = "active", _("Actif — en vente")
        COMPLETED = "completed", _("Terminé — tout vendu")
        REJECTED = "rejected", _("Rejeté")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    promoteur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="lotissements", verbose_name=_("promoteur"),
    )
    zone = models.ForeignKey(
        Zone, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="lotissements", verbose_name=_("zone"),
    )

    # Identification
    name = models.CharField(_("nom du lotissement"), max_length=300)
    code = models.CharField(
        _("code lotissement"), max_length=50, unique=True,
        help_text=_("Identifiant unique (ex: LOT-ABJ-001)."),
    )
    description = models.TextField(_("description"), blank=True)

    # Statut
    status = models.CharField(
        _("statut"), max_length=20,
        choices=LotissementStatus.choices, default=LotissementStatus.DRAFT,
    )

    # Géométrie globale
    geometry = models.PolygonField(
        _("périmètre du lotissement"), srid=4326,
        help_text=_("Contour global du terrain à morceler."),
    )
    total_surface_m2 = models.DecimalField(
        _("surface totale (m²)"), max_digits=12, decimal_places=2,
        null=True, blank=True,
    )

    # Plan de morcellement
    plan_image = models.ImageField(
        _("plan de morcellement"), upload_to="lotissements/plans/%Y/%m/",
        blank=True, help_text=_("Image du plan (JPG, PNG)."),
    )
    plan_shapefile = models.FileField(
        _("plan SIG"), upload_to="lotissements/sig/%Y/%m/",
        blank=True, help_text=_("Fichier Shapefile (.zip) ou GeoJSON du morcellement."),
    )

    # Compteurs (dénormalisés pour performance)
    total_ilots = models.PositiveIntegerField(_("nombre d'îlots"), default=0)
    total_lots = models.PositiveIntegerField(_("nombre de lots"), default=0)
    lots_sold = models.PositiveIntegerField(_("lots vendus"), default=0)

    # Prix indicatif
    price_per_m2_min = models.DecimalField(
        _("prix min/m² (FCFA)"), max_digits=12, decimal_places=0,
        null=True, blank=True,
    )
    price_per_m2_max = models.DecimalField(
        _("prix max/m² (FCFA)"), max_digits=12, decimal_places=0,
        null=True, blank=True,
    )

    # Viabilisation
    has_water = models.BooleanField(_("eau potable"), default=False)
    has_electricity = models.BooleanField(_("électricité"), default=False)
    has_road = models.BooleanField(_("voirie bitumée"), default=False)
    has_drainage = models.BooleanField(_("assainissement"), default=False)
    has_public_spaces = models.BooleanField(_("espaces publics"), default=False)

    # ── Documents juridiques ──
    arrete_approbation = models.FileField(
        _("arrêté d'approbation"), upload_to="lotissements/docs/%Y/%m/",
        blank=True, help_text=_("Preuve officielle de la légalité du lotissement (ministère de l'Urbanisme)."),
    )
    attestation_villageoise = models.FileField(
        _("attestation villageoise / lettre d'attribution"),
        upload_to="lotissements/docs/%Y/%m/", blank=True,
        help_text=_("Document administratif de base."),
    )
    dossier_technique = models.FileField(
        _("dossier technique"), upload_to="lotissements/docs/%Y/%m/",
        blank=True, help_text=_("Établi par un géomètre expert."),
    )
    certificat_propriete = models.FileField(
        _("certificat de propriété / état foncier"),
        upload_to="lotissements/docs/%Y/%m/", blank=True,
        help_text=_("Indispensable pour vérifier l'absence d'hypothèques ou de litiges."),
    )

    # ── Approbation ministérielle ──
    is_approved = models.BooleanField(
        _("approuvé par le ministère"), default=False,
        help_text=_("Le lotissement a été approuvé par le ministère de l'Urbanisme."),
    )
    approval_reference = models.CharField(
        _("numéro d'arrêté"), max_length=200, blank=True,
        help_text=_("Référence de l'arrêté d'approbation."),
    )

    # ── Validation géomètre ──
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="validated_lotissements",
        verbose_name=_("validé par (géomètre)"),
    )
    validated_at = models.DateTimeField(_("date de validation"), null=True, blank=True)
    validation_notes = models.TextField(_("notes de validation"), blank=True)

    # Dates
    approval_date = models.DateField(_("date d'approbation"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Lotissement")
        verbose_name_plural = _("Lotissements")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.code}) — {self.get_status_display()}"

    @property
    def progress_pct(self):
        """Pourcentage de lots vendus."""
        if self.total_lots == 0:
            return 0
        return round(self.lots_sold / self.total_lots * 100, 1)

    @property
    def lots_available(self):
        return self.total_lots - self.lots_sold

    def update_counters(self):
        """Met à jour les compteurs depuis les parcelles liées."""
        parcelles = self.parcelles.all()
        self.total_lots = parcelles.count()
        self.lots_sold = parcelles.filter(status="vendu").count()
        self.save(update_fields=["total_lots", "lots_sold", "updated_at"])
