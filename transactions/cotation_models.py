"""
Modèles Cotation & Boutique — EYE-FONCIER
============================================
COTATION : Paiement de 10 % de la valeur du bien avant toute réservation.
  → Débloque : visite de la parcelle + accès aux documents filigranés.
  → Principe : « Ne réserve pas une parcelle qui veut, mais qui peut. »

BOUTIQUE : Espace vendeur / promoteur créé après paiement d'une cotation boutique.
  → Les vendeurs et promoteurs paient une cotation pour publier leurs parcelles.

VERIFICATION : Workflow du responsable Eye-Foncier qui :
  1. Contacte le vendeur pour récupérer la documentation physique.
  2. Vérifie et analyse les documents dans les locaux Eye-Foncier.
  3. Contacte le client pour le rendez-vous d'achat définitif.
"""
import uuid
import time
from decimal import Decimal

from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _


# ═══════════════════════════════════════════════════════════
# COTATION — « Ne réserve pas qui veut, mais qui peut »
# ═══════════════════════════════════════════════════════════

class Cotation(models.Model):
    """Cotation = 10 % du prix du bien, payée AVANT toute réservation.

    Droits conférés par une cotation VALIDÉE :
      ✓ Visite physique de la parcelle (BonDeVisite)
      ✓ Accès aux documents scannés et filigranés
      ✓ Déclenchement du processus de vérification Eye-Foncier
      ✓ Possibilité de réservation définitive

    La cotation est déduite du prix total lors de l'achat définitif.
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("En attente de paiement")
        PAID = "paid", _("Payée — En attente de validation")
        VALIDATED = "validated", _("Validée — Droits actifs")
        EXPIRED = "expired", _("Expirée")
        REFUNDED = "refunded", _("Remboursée")
        CANCELLED = "cancelled", _("Annulée")

    class CotationType(models.TextChoices):
        ACHAT = "achat", _("Cotation d'achat — 10 % du bien")
        BOUTIQUE = "boutique", _("Cotation boutique — Vendeur / Promoteur")

    # Tarif fixe pour la cotation boutique (en FCFA)
    BOUTIQUE_COTATION_PRICE = 50_000

    # Pourcentage de cotation d'achat
    ACHAT_COTATION_RATE = Decimal("0.10")  # 10 %

    # Durée de validité d'une cotation (en jours)
    VALIDITY_DAYS = 30

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(
        _("référence"), max_length=30, unique=True, editable=False,
    )

    # Qui paie
    payer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cotations",
        verbose_name=_("payeur"),
    )

    # Type de cotation
    cotation_type = models.CharField(
        _("type de cotation"), max_length=20,
        choices=CotationType.choices, default=CotationType.ACHAT,
    )

    # Parcelle concernée (NULL pour cotation boutique)
    parcelle = models.ForeignKey(
        "parcelles.Parcelle",
        on_delete=models.PROTECT,
        related_name="cotations",
        verbose_name=_("parcelle"),
        null=True, blank=True,
        help_text=_("Parcelle concernée (uniquement pour cotation d'achat)."),
    )

    # Montants
    amount = models.DecimalField(
        _("montant cotation (FCFA)"), max_digits=15, decimal_places=0,
    )
    property_price = models.DecimalField(
        _("prix du bien (FCFA)"), max_digits=15, decimal_places=0,
        null=True, blank=True,
        help_text=_("Prix du bien au moment de la cotation (pour traçabilité)."),
    )

    # Statut
    status = models.CharField(
        _("statut"), max_length=20,
        choices=Status.choices, default=Status.PENDING,
    )

    # Paiement (CinetPay)
    payment_reference = models.CharField(
        _("référence paiement CinetPay"), max_length=100, blank=True,
    )
    payment_method = models.CharField(
        _("mode de paiement"), max_length=30, blank=True,
        choices=[
            ("mobile_money", _("Mobile Money")),
            ("wave", _("Wave")),
            ("carte", _("Carte bancaire")),
            ("virement", _("Virement bancaire")),
        ],
    )
    paid_at = models.DateTimeField(_("date de paiement"), null=True, blank=True)
    validated_at = models.DateTimeField(_("date de validation"), null=True, blank=True)
    expires_at = models.DateTimeField(_("date d'expiration"), null=True, blank=True)

    # Lien vers la transaction finale (cotation déduite)
    transaction = models.OneToOneField(
        "transactions.Transaction",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="cotation",
        verbose_name=_("transaction liée"),
        help_text=_("Transaction d'achat définitif où la cotation est déduite."),
    )

    # Audit
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="validated_cotations",
        verbose_name=_("validé par"),
    )
    notes = models.TextField(_("notes"), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Cotation")
        verbose_name_plural = _("Cotations")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["payer", "-created_at"]),
            models.Index(fields=["parcelle", "status"]),
            models.Index(fields=["status"]),
        ]
        constraints = [
            # Un seul achat de cotation VALIDATED/PAID par parcelle par acheteur
            models.UniqueConstraint(
                fields=["payer", "parcelle"],
                condition=models.Q(status__in=["paid", "validated"]),
                name="unique_active_cotation_per_buyer_parcelle",
            ),
        ]

    def __str__(self):
        target = self.parcelle.lot_number if self.parcelle else "Boutique"
        return f"COT-{self.reference} | {target} | {self.get_status_display()}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"COT-{int(time.time())}"
        super().save(*args, **kwargs)

    @classmethod
    def compute_cotation_amount(cls, parcelle_price):
        """Calcule le montant de la cotation d'achat (10 % du prix)."""
        return int(Decimal(str(parcelle_price)) * cls.ACHAT_COTATION_RATE)

    @property
    def is_valid(self):
        """Vérifie si la cotation est active et non expirée."""
        if self.status != self.Status.VALIDATED:
            return False
        if self.expires_at:
            from django.utils import timezone
            return timezone.now() < self.expires_at
        return True

    @property
    def remaining_balance(self):
        """Montant restant à payer pour l'achat définitif."""
        if self.property_price and self.amount:
            return self.property_price - self.amount
        return None


# ═══════════════════════════════════════════════════════════
# BOUTIQUE — Espace vendeur / promoteur
# ═══════════════════════════════════════════════════════════

class Boutique(models.Model):
    """Boutique = espace de publication d'un vendeur ou promoteur.

    Créée après paiement de la cotation boutique.
    Le vendeur/promoteur peut ensuite publier ses parcelles.
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("En attente de cotation")
        ACTIVE = "active", _("Active")
        SUSPENDED = "suspended", _("Suspendue")
        CLOSED = "closed", _("Fermée")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="boutique",
        verbose_name=_("propriétaire"),
    )

    # Identité de la boutique
    name = models.CharField(_("nom de la boutique"), max_length=200)
    slug = models.SlugField(_("slug"), max_length=200, unique=True)
    description = models.TextField(_("description"), blank=True)
    logo = models.ImageField(
        _("logo"), upload_to="boutiques/logos/%Y/%m/", blank=True,
    )
    banner = models.ImageField(
        _("bannière"), upload_to="boutiques/banners/%Y/%m/", blank=True,
    )

    # Contact
    phone = models.CharField(_("téléphone"), max_length=20, blank=True)
    whatsapp = models.CharField(
        _("numéro WhatsApp"), max_length=20, blank=True,
        help_text=_("Numéro WhatsApp pour le bouton de contact (ex: 2250709000000)"),
    )
    email = models.EmailField(_("email de contact"), blank=True)
    address = models.CharField(_("adresse"), max_length=300, blank=True)
    city = models.CharField(_("ville"), max_length=100, blank=True)
    commune = models.CharField(_("commune"), max_length=100, blank=True)

    # Personnalisation & Branding
    whatsapp_message = models.CharField(
        _("message WhatsApp pré-rempli"), max_length=300, blank=True,
        default="Bonjour, je suis interesse par vos parcelles sur Eye-Foncier.",
    )
    website = models.URLField(_("site web"), blank=True)
    facebook = models.URLField(_("page Facebook"), blank=True)
    instagram = models.CharField(_("Instagram"), max_length=100, blank=True)
    theme_color = models.CharField(
        _("couleur du thème"), max_length=7, blank=True, default="#0B3D2E",
        help_text=_("Couleur hexadécimale pour personnaliser votre boutique (ex: #0B3D2E)"),
    )
    specialty = models.CharField(
        _("spécialité"), max_length=200, blank=True,
        help_text=_("Ex: Terrains résidentiels à Cocody, Lotissements à Yamoussoukro"),
    )

    # Statut
    status = models.CharField(
        _("statut"), max_length=20,
        choices=Status.choices, default=Status.PENDING,
    )

    # Cotation de création
    cotation = models.OneToOneField(
        Cotation,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="boutique",
        verbose_name=_("cotation de création"),
    )

    # Statistiques
    total_parcelles = models.PositiveIntegerField(_("parcelles publiées"), default=0)
    total_ventes = models.PositiveIntegerField(_("ventes réalisées"), default=0)
    rating = models.DecimalField(
        _("note moyenne"), max_digits=3, decimal_places=1, default=0.0,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Boutique")
        verbose_name_plural = _("Boutiques")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE

    @property
    def whatsapp_link(self):
        """Retourne le lien WhatsApp avec message pré-rempli."""
        number = self.whatsapp or self.phone
        if not number:
            return ""
        # Nettoyer le numéro
        clean = number.replace(" ", "").replace("-", "").replace("+", "")
        msg = self.whatsapp_message or "Bonjour, je suis interesse par vos parcelles."
        from urllib.parse import quote
        return f"https://wa.me/{clean}?text={quote(msg)}"

    @property
    def location_display(self):
        """Retourne la localisation formatée."""
        parts = [p for p in [self.commune, self.city, self.address] if p]
        return ", ".join(parts) if parts else ""

    def update_rating(self):
        """Recalcule la note moyenne depuis les avis."""
        from django.db.models import Avg
        avg = self.reviews.aggregate(avg=Avg("score"))["avg"]
        self.rating = round(avg, 1) if avg else 0
        self.save(update_fields=["rating", "updated_at"])


# ═══════════════════════════════════════════════════════════
# AVIS & NOTATIONS — Systeme d'etoiles
# ═══════════════════════════════════════════════════════════

class Review(models.Model):
    """Avis avec notation etoiles (1-5) sur une boutique, un vendeur ou une prestation."""

    class TargetType(models.TextChoices):
        BOUTIQUE = "boutique", _("Boutique")
        VENDEUR = "vendeur", _("Vendeur")
        PRESTATION = "prestation", _("Prestation / Transaction")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="reviews_given", verbose_name=_("auteur"),
    )

    # Cible polymorphe
    target_type = models.CharField(
        _("type de cible"), max_length=20, choices=TargetType.choices,
    )
    boutique = models.ForeignKey(
        Boutique, on_delete=models.CASCADE, null=True, blank=True,
        related_name="reviews", verbose_name=_("boutique"),
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True,
        related_name="reviews_received", verbose_name=_("utilisateur cible"),
    )
    transaction = models.ForeignKey(
        "transactions.Transaction", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviews", verbose_name=_("transaction liee"),
    )

    # Notation
    score = models.PositiveSmallIntegerField(
        _("note (1-5)"),
        help_text=_("1 = Tres mauvais, 5 = Excellent"),
    )
    comment = models.TextField(_("commentaire"), max_length=1000, blank=True)

    # Anti-spam
    is_verified = models.BooleanField(
        _("avis verifie"), default=False,
        help_text=_("L'auteur a effectivement realise une transaction."),
    )
    is_visible = models.BooleanField(_("visible publiquement"), default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Avis")
        verbose_name_plural = _("Avis")
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(check=models.Q(score__gte=1, score__lte=5), name="review_score_1_to_5"),
            # Un utilisateur ne peut donner qu'un avis par boutique
            models.UniqueConstraint(
                fields=["author", "boutique"],
                condition=models.Q(boutique__isnull=False),
                name="unique_review_per_boutique",
            ),
            # Un utilisateur ne peut donner qu'un avis par vendeur
            models.UniqueConstraint(
                fields=["author", "target_user"],
                condition=models.Q(target_user__isnull=False),
                name="unique_review_per_vendeur",
            ),
        ]

    def __str__(self):
        return f"Avis {self.score}/5 par {self.author} — {self.get_target_type_display()}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Mettre a jour la note moyenne de la boutique
        if self.boutique:
            self.boutique.update_rating()


# ═══════════════════════════════════════════════════════════
# VERIFICATION EYE-FONCIER — Workflow du responsable
# ═══════════════════════════════════════════════════════════

class VerificationRequest(models.Model):
    """Demande de vérification déclenchée après validation de la cotation.

    Workflow :
      1. COTATION validée → VerificationRequest créée automatiquement.
      2. Le responsable Eye-Foncier contacte le vendeur.
      3. Le vendeur dépose les documents physiques dans les locaux.
      4. Le responsable vérifie, analyse, filigrade les documents.
      5. Le responsable contacte le client pour le rendez-vous.
      6. Le client se rend dans les locaux pour l'achat définitif.
    """

    class Status(models.TextChoices):
        CREATED = "created", _("Créée — En attente d'assignation")
        ASSIGNED = "assigned", _("Assignée à un vérificateur")
        SELLER_CONTACTED = "seller_contacted", _("Vendeur contacté")
        DOCS_RECEIVED = "docs_received", _("Documents reçus aux locaux")
        DOCS_VERIFIED = "docs_verified", _("Documents vérifiés et analysés")
        DOCS_WATERMARKED = "docs_watermarked", _("Documents filigranés et publiés")
        CLIENT_CONTACTED = "client_contacted", _("Client contacté pour RDV")
        RDV_SCHEDULED = "rdv_scheduled", _("RDV programmé aux locaux")
        COMPLETED = "completed", _("Finalisée — Achat en cours")
        CANCELLED = "cancelled", _("Annulée")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(
        _("référence"), max_length=30, unique=True, editable=False,
    )

    # Cotation source
    cotation = models.OneToOneField(
        Cotation,
        on_delete=models.CASCADE,
        related_name="verification",
        verbose_name=_("cotation source"),
    )

    # Acteurs
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="verification_requests_as_buyer",
        verbose_name=_("acheteur"),
    )
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="verification_requests_as_seller",
        verbose_name=_("vendeur"),
    )
    verifier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="verification_assignments",
        verbose_name=_("vérificateur assigné"),
    )

    # Parcelle
    parcelle = models.ForeignKey(
        "parcelles.Parcelle",
        on_delete=models.PROTECT,
        related_name="verification_requests",
        verbose_name=_("parcelle"),
    )

    # Statut
    status = models.CharField(
        _("statut"), max_length=25,
        choices=Status.choices, default=Status.CREATED,
    )

    # Dates du workflow
    seller_contacted_at = models.DateTimeField(
        _("date contact vendeur"), null=True, blank=True,
    )
    docs_received_at = models.DateTimeField(
        _("date réception documents"), null=True, blank=True,
    )
    docs_verified_at = models.DateTimeField(
        _("date vérification documents"), null=True, blank=True,
    )
    client_contacted_at = models.DateTimeField(
        _("date contact client"), null=True, blank=True,
    )
    rdv_date = models.DateTimeField(
        _("date du RDV aux locaux"), null=True, blank=True,
    )
    completed_at = models.DateTimeField(
        _("date de finalisation"), null=True, blank=True,
    )

    # Notes du vérificateur
    verification_notes = models.TextField(
        _("notes de vérification"), blank=True,
    )
    seller_contact_notes = models.TextField(
        _("notes contact vendeur"), blank=True,
    )
    client_contact_notes = models.TextField(
        _("notes contact client"), blank=True,
    )

    # Résultat de l'analyse
    docs_are_authentic = models.BooleanField(
        _("documents authentiques"), null=True,
        help_text=_("Résultat de la vérification d'authenticité."),
    )
    analysis_report = models.TextField(
        _("rapport d'analyse"), blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Demande de vérification")
        verbose_name_plural = _("Demandes de vérification")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["verifier", "status"]),
        ]

    def __str__(self):
        return f"VER-{self.reference} | {self.parcelle.lot_number} | {self.get_status_display()}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"VER-{int(time.time())}"
        super().save(*args, **kwargs)

    @property
    def progress_percent(self):
        """Pourcentage de progression du workflow."""
        steps = [
            self.status != self.Status.CREATED,
            self.status not in [self.Status.CREATED, self.Status.ASSIGNED],
            self.docs_received_at is not None,
            self.docs_verified_at is not None,
            self.client_contacted_at is not None,
            self.rdv_date is not None,
            self.status == self.Status.COMPLETED,
        ]
        return int(sum(steps) / len(steps) * 100)
