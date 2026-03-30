"""
Modeles de Litiges — EYE-FONCIER
Workflow complet de resolution : ouverture, preuves, mediation, decision, remboursement.
"""
import uuid
import time

from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from .models import Transaction


class Dispute(models.Model):
    """Litige sur une transaction fonciere.

    Cycle de vie :
    opened → under_review → mediation → resolved / escalated → closed
    """

    class Status(models.TextChoices):
        OPENED = "opened", _("Ouvert")
        UNDER_REVIEW = "under_review", _("En cours d'examen")
        MEDIATION = "mediation", _("Mediation en cours")
        ESCALATED = "escalated", _("Escalade (juridique)")
        RESOLVED = "resolved", _("Resolu")
        CLOSED = "closed", _("Clos")

    class Category(models.TextChoices):
        FRAUD = "fraud", _("Fraude suspectee")
        NON_CONFORMITY = "non_conformity", _("Non-conformite du terrain")
        PAYMENT = "payment", _("Probleme de paiement")
        DOCS_MISSING = "docs_missing", _("Documents manquants ou falsifies")
        BOUNDARY = "boundary", _("Litige de bornage")
        TITLE_ISSUE = "title_issue", _("Probleme de titre foncier")
        SELLER_NO_RESPONSE = "seller_no_response", _("Vendeur injoignable")
        BUYER_WITHDRAWAL = "buyer_withdrawal", _("Retractation de l'acheteur")
        OTHER = "other", _("Autre")

    class Priority(models.TextChoices):
        LOW = "low", _("Basse")
        NORMAL = "normal", _("Normale")
        HIGH = "high", _("Haute")
        URGENT = "urgent", _("Urgente")

    class Resolution(models.TextChoices):
        FULL_REFUND = "full_refund", _("Remboursement integral")
        PARTIAL_REFUND = "partial_refund", _("Remboursement partiel")
        NO_REFUND = "no_refund", _("Pas de remboursement")
        TRANSACTION_RESUMED = "transaction_resumed", _("Transaction reprise")
        MUTUAL_AGREEMENT = "mutual_agreement", _("Accord a l'amiable")
        EXTERNAL_ARBITRATION = "external_arbitration", _("Arbitrage externe")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(
        _("reference"), max_length=30, unique=True, editable=False,
    )
    transaction = models.ForeignKey(
        Transaction, on_delete=models.PROTECT, related_name="disputes",
        verbose_name=_("transaction"),
    )

    # Parties
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="disputes_opened", verbose_name=_("ouvert par"),
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="disputes_assigned",
        verbose_name=_("assigne a"),
        help_text=_("Mediateur ou administrateur en charge"),
    )

    # Classification
    category = models.CharField(
        _("categorie"), max_length=30, choices=Category.choices,
    )
    priority = models.CharField(
        _("priorite"), max_length=10, choices=Priority.choices, default=Priority.NORMAL,
    )
    status = models.CharField(
        _("statut"), max_length=20, choices=Status.choices, default=Status.OPENED,
    )

    # Description
    subject = models.CharField(_("sujet"), max_length=200)
    description = models.TextField(
        _("description detaillee"),
        help_text=_("Decrivez le probleme en detail."),
    )

    # Resolution
    resolution_type = models.CharField(
        _("type de resolution"), max_length=30,
        choices=Resolution.choices, blank=True,
    )
    resolution_notes = models.TextField(_("notes de resolution"), blank=True)
    refund_amount = models.DecimalField(
        _("montant rembourse (FCFA)"), max_digits=15, decimal_places=0,
        null=True, blank=True,
    )
    refund_processed = models.BooleanField(_("remboursement effectue"), default=False)
    refund_processed_at = models.DateTimeField(null=True, blank=True)

    # Delais
    deadline = models.DateTimeField(
        _("date limite de resolution"), null=True, blank=True,
        help_text=_("Delai reglementaire pour resoudre le litige."),
    )
    escalated_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    # Metadata
    metadata = models.JSONField(_("metadonnees"), default=dict, blank=True)

    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Litige")
        verbose_name_plural = _("Litiges")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["priority", "-created_at"]),
            models.Index(fields=["transaction"]),
            models.Index(fields=["assigned_to", "status"]),
            models.Index(fields=["opened_by"]),
        ]

    def __str__(self):
        return f"LIT-{self.reference} | {self.subject[:50]} | {self.get_status_display()}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"LIT-{int(time.time())}"
        super().save(*args, **kwargs)

    @property
    def is_open(self):
        return self.status not in (self.Status.RESOLVED, self.Status.CLOSED)

    @property
    def days_since_opened(self):
        from django.utils import timezone
        return (timezone.now() - self.created_at).days

    @property
    def is_overdue(self):
        if not self.deadline:
            return False
        from django.utils import timezone
        return timezone.now() > self.deadline and self.is_open


class DisputeEvidence(models.Model):
    """Piece a conviction / preuve attachee a un litige."""

    class EvidenceType(models.TextChoices):
        DOCUMENT = "document", _("Document")
        PHOTO = "photo", _("Photo")
        SCREENSHOT = "screenshot", _("Capture d'ecran")
        MESSAGE = "message", _("Conversation / Message")
        CONTRACT = "contract", _("Contrat / Compromis")
        PAYMENT_PROOF = "payment_proof", _("Preuve de paiement")
        SURVEY = "survey", _("Plan de bornage")
        OTHER = "other", _("Autre")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dispute = models.ForeignKey(
        Dispute, on_delete=models.CASCADE, related_name="evidences",
        verbose_name=_("litige"),
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="dispute_evidences", verbose_name=_("soumis par"),
    )

    evidence_type = models.CharField(
        _("type"), max_length=20, choices=EvidenceType.choices,
    )
    title = models.CharField(_("titre"), max_length=200)
    description = models.TextField(_("description"), blank=True)
    file = models.FileField(
        _("fichier"), upload_to="disputes/evidences/%Y/%m/",
    )
    file_size = models.PositiveIntegerField(_("taille (octets)"), default=0)

    # Verification admin
    verified = models.BooleanField(_("verifie par admin"), default=False)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="verified_evidences",
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Piece a conviction")
        verbose_name_plural = _("Pieces a conviction")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.get_evidence_type_display()})"

    def save(self, *args, **kwargs):
        if self.file and not self.file_size:
            try:
                self.file_size = self.file.size
            except Exception:
                pass
        super().save(*args, **kwargs)


class DisputeMessage(models.Model):
    """Message dans le fil de discussion d'un litige (mediation)."""

    class SenderRole(models.TextChoices):
        BUYER = "buyer", _("Acheteur")
        SELLER = "seller", _("Vendeur")
        MEDIATOR = "mediator", _("Mediateur")
        SYSTEM = "system", _("Systeme")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dispute = models.ForeignKey(
        Dispute, on_delete=models.CASCADE, related_name="messages",
        verbose_name=_("litige"),
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="dispute_messages", verbose_name=_("expediteur"),
    )
    sender_role = models.CharField(
        _("role"), max_length=10, choices=SenderRole.choices,
    )
    content = models.TextField(_("message"))
    attachment = models.FileField(
        _("piece jointe"), upload_to="disputes/messages/%Y/%m/",
        blank=True,
    )

    # Lecture
    read_by_buyer = models.BooleanField(default=False)
    read_by_seller = models.BooleanField(default=False)
    read_by_mediator = models.BooleanField(default=False)

    is_internal = models.BooleanField(
        _("note interne"), default=False,
        help_text=_("Visible uniquement par les mediateurs et admins."),
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Message litige")
        verbose_name_plural = _("Messages litige")
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.sender} ({self.get_sender_role_display()}) — {self.content[:50]}"
