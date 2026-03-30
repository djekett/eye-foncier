"""
Modèles Comptes & Profils — EYE-FONCIER
"""
import uuid
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.gis.db import models
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    """Utilisateur personnalisé avec rôle intégré."""

    class Role(models.TextChoices):
        VISITEUR = "visiteur", _("Visiteur")
        ACHETEUR = "acheteur", _("Acheteur")
        VENDEUR = "vendeur", _("Vendeur")
        PROMOTEUR = "promoteur", _("Promoteur immobilier")
        GEOMETRE = "geometre", _("Géomètre / Validateur")
        ADMIN = "admin", _("Administrateur")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(_("adresse email"), unique=True)
    role = models.CharField(
        _("rôle"), max_length=20, choices=Role.choices, default=Role.VISITEUR
    )
    phone = models.CharField(_("téléphone"), max_length=20, blank=True)
    is_verified = models.BooleanField(_("compte vérifié"), default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username", "first_name", "last_name"]

    class Meta:
        verbose_name = _("Utilisateur")
        verbose_name_plural = _("Utilisateurs")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_full_name()} ({self.role})"

    @property
    def is_acheteur(self):
        return self.role == self.Role.ACHETEUR

    @property
    def is_vendeur(self):
        return self.role in (self.Role.VENDEUR, self.Role.PROMOTEUR)

    @property
    def is_promoteur(self):
        return self.role == self.Role.PROMOTEUR

    @property
    def is_geometre(self):
        return self.role == self.Role.GEOMETRE

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN or self.is_staff or self.is_superuser


class Profile(models.Model):
    """Extension du profil utilisateur."""

    class KYCStatus(models.TextChoices):
        PENDING = "pending", _("En attente")
        SUBMITTED = "submitted", _("Soumis")
        VERIFIED = "verified", _("Vérifié")
        REJECTED = "rejected", _("Rejeté")

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    avatar = models.ImageField(
        _("photo de profil"), upload_to="avatars/%Y/%m/", blank=True
    )
    bio = models.TextField(_("biographie"), blank=True, max_length=500)
    address = models.CharField(_("adresse"), max_length=255, blank=True)
    city = models.CharField(_("ville"), max_length=100, blank=True)
    country = models.CharField(_("pays"), max_length=100, default="Côte d'Ivoire")

    # KYC (Know Your Customer)
    id_document = models.FileField(
        _("pièce d'identité"), upload_to="documents/kyc/%Y/%m/", blank=True
    )
    kyc_status = models.CharField(
        _("statut KYC"), max_length=20, choices=KYCStatus.choices, default=KYCStatus.PENDING
    )

    # Stats vendeur
    trust_score = models.DecimalField(
        _("score de confiance"), max_digits=3, decimal_places=1, default=0.0
    )
    total_sales = models.PositiveIntegerField(_("ventes totales"), default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Profil")
        verbose_name_plural = _("Profils")

    def __str__(self):
        return f"Profil de {self.user.get_full_name()}"

    @property
    def is_kyc_verified(self):
        return self.kyc_status == self.KYCStatus.VERIFIED


class AccessLog(models.Model):
    """Journal d'audit : qui a fait quoi et quand."""

    class ActionType(models.TextChoices):
        LOGIN = "login", _("Connexion")
        LOGOUT = "logout", _("Déconnexion")
        VIEW_DOC = "view_doc", _("Consultation document")
        VIEW_PARCELLE = "view_parcelle", _("Consultation parcelle")
        DOWNLOAD = "download", _("Téléchargement")
        RESERVATION = "reservation", _("Réservation")
        UPLOAD = "upload", _("Upload")
        UPDATE = "update", _("Modification")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="access_logs"
    )
    action = models.CharField(_("action"), max_length=30, choices=ActionType.choices)
    resource_type = models.CharField(_("type ressource"), max_length=100, blank=True)
    resource_id = models.CharField(_("ID ressource"), max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(_("adresse IP"), null=True, blank=True)
    user_agent = models.TextField(_("user agent"), blank=True)
    details = models.JSONField(_("détails"), default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("Log d'accès")
        verbose_name_plural = _("Logs d'accès")
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["user", "-timestamp"]),
            models.Index(fields=["action", "-timestamp"]),
        ]

    def __str__(self):
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {self.user} — {self.action}"


class CertificationRequest(models.Model):
    """Demande de certification / Badge de Confiance.

    Workflow : pending → scheduled → approved / rejected
    Types :
      • standard    — Upload pièces (gratuit)
      • visio       — Visio-vérification 15min (5 000 FCFA)
      • premium     — Visite terrain par géomètre (25 000 FCFA)
    """

    class CertType(models.TextChoices):
        STANDARD = "standard", _("Standard — Upload de pièces")
        VISIO = "visio", _("Visio-Vérification (15min)")
        PREMIUM = "premium", _("Premium — Visite terrain")

    class Status(models.TextChoices):
        PENDING = "pending", _("En attente")
        SCHEDULED = "scheduled", _("RDV programmé")
        IN_REVIEW = "in_review", _("En cours d'examen")
        APPROVED = "approved", _("Approuvé")
        REJECTED = "rejected", _("Rejeté")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="certification_requests",
    )
    cert_type = models.CharField(
        _("type de certification"), max_length=20,
        choices=CertType.choices, default=CertType.STANDARD,
    )
    status = models.CharField(
        _("statut"), max_length=20,
        choices=Status.choices, default=Status.PENDING,
    )
    message = models.TextField(_("message du demandeur"), blank=True)
    preferred_date = models.CharField(
        _("date souhaitée"), max_length=100, blank=True,
        help_text=_("Date/créneau préféré pour la visio ou visite."),
    )
    admin_notes = models.TextField(_("notes admin"), blank=True)
    scheduled_at = models.DateTimeField(_("RDV programmé"), null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_certifications",
    )

    # Caution vendeur premium
    caution_amount = models.DecimalField(
        _("caution déposée (FCFA)"), max_digits=10, decimal_places=0,
        null=True, blank=True,
    )
    caution_paid = models.BooleanField(_("caution payée"), default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Demande de certification")
        verbose_name_plural = _("Demandes de certification")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Cert-{self.user.username} ({self.cert_type}) — {self.status}"


# ─── Espace Partenaires ──────────────────────────────────
class Partner(models.Model):
    """Partenaires institutionnels (banques, assurances, notaires)."""

    class PartnerType(models.TextChoices):
        BANK = "bank", _("Banque")
        INSURANCE = "insurance", _("Assurance")
        NOTARY = "notary", _("Notaire")
        AGENCY = "agency", _("Agence immobiliere")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, verbose_name=_("Nom"))
    partner_type = models.CharField(max_length=20, choices=PartnerType.choices, verbose_name=_("Type"))
    logo = models.ImageField(upload_to="partners/logos/", blank=True, null=True)
    description = models.TextField(blank=True, default="")
    contact_email = models.EmailField(blank=True, default="")
    contact_phone = models.CharField(max_length=30, blank=True, default="")
    website = models.URLField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text=_("% commission"))
    services = models.JSONField(default=list, blank=True, help_text=_("Liste des services proposes"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Partenaire")
        verbose_name_plural = _("Partenaires")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_partner_type_display()})"


class PartnerReferral(models.Model):
    """Demandes de mise en relation avec un partenaire."""

    class Status(models.TextChoices):
        PENDING = "pending", _("En attente")
        CONTACTED = "contacted", _("Contacte")
        CONVERTED = "converted", _("Converti")
        REJECTED = "rejected", _("Rejete")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    partner = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name="referrals")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="partner_referrals")
    transaction = models.ForeignKey(
        "transactions.Transaction", on_delete=models.SET_NULL, null=True, blank=True, related_name="partner_referrals"
    )
    referral_type = models.CharField(max_length=50, blank=True, default="", help_text=_("credit_request, insurance_quote, etc."))
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Demande partenaire")
        verbose_name_plural = _("Demandes partenaires")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} → {self.partner.name} ({self.status})"


# ─── Parrainage & Affiliation ────────────────────────────
class ReferralProgram(models.Model):
    """Programme de parrainage entre utilisateurs."""

    class Status(models.TextChoices):
        PENDING = "pending", _("En attente")
        REGISTERED = "registered", _("Inscrit")
        CONVERTED = "converted", _("Converti")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    referrer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referrals_sent")
    referred = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referral_received")
    referral_code = models.CharField(max_length=20, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reward_type = models.CharField(max_length=30, blank=True, default="bonus")
    reward_amount = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    reward_claimed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Parrainage")
        verbose_name_plural = _("Parrainages")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.referrer.email} → {self.referred.email} ({self.status})"


class AmbassadorProfile(models.Model):
    """Profil ambassadeur pour le programme d'affiliation."""

    class Tier(models.TextChoices):
        BRONZE = "bronze", _("Bronze")
        SILVER = "silver", _("Argent")
        GOLD = "gold", _("Or")
        PLATINUM = "platinum", _("Platine")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ambassador_profile")
    ambassador_code = models.CharField(max_length=20, unique=True)
    tier = models.CharField(max_length=20, choices=Tier.choices, default=Tier.BRONZE)
    total_referrals = models.IntegerField(default=0)
    total_conversions = models.IntegerField(default=0)
    total_earnings = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=2.0, help_text=_("% par transaction"))
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Ambassadeur")
        verbose_name_plural = _("Ambassadeurs")

    def __str__(self):
        return f"Ambassadeur {self.user.email} ({self.get_tier_display()})"

    @property
    def conversion_rate(self):
        if self.total_referrals == 0:
            return 0
        return round((self.total_conversions / self.total_referrals) * 100, 1)
