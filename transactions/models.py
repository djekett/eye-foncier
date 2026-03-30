"""
Modèles Transactions — EYE-FONCIER
Réservation, Séquestre, Bon de Visite, Compromis de Vente.
"""
import uuid
import time
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from parcelles.models import Parcelle


class Transaction(models.Model):
    """Transaction foncière (réservation → séquestre → finalisation)."""

    class Status(models.TextChoices):
        PENDING = "pending", _("En attente")
        RESERVED = "reserved", _("Réservé")
        ESCROW_FUNDED = "escrow_funded", _("Séquestre alimenté")
        DOCS_VALIDATED = "docs_validated", _("Documents validés")
        PAID = "paid", _("Payé")
        COMPLETED = "completed", _("Finalisé")
        CANCELLED = "cancelled", _("Annulé")
        DISPUTED = "disputed", _("Litige")

    class PaymentMethod(models.TextChoices):
        VIREMENT = "virement", _("Virement bancaire")
        MOBILE_MONEY = "mobile_money", _("Mobile Money")
        ESPECES = "especes", _("Espèces")
        CHEQUE = "cheque", _("Chèque")
        ESCROW = "escrow", _("Séquestre EYE-Foncier")
        AUTRE = "autre", _("Autre")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(
        _("référence"), max_length=30, unique=True, editable=False,
    )
    parcelle = models.ForeignKey(
        Parcelle, on_delete=models.PROTECT, related_name="transactions",
    )
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="purchases", verbose_name=_("acheteur"),
    )
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="sales", verbose_name=_("vendeur"),
    )

    amount = models.DecimalField(_("montant (FCFA)"), max_digits=15, decimal_places=0)
    status = models.CharField(
        _("statut"), max_length=20, choices=Status.choices, default=Status.PENDING,
    )
    payment_method = models.CharField(
        _("mode de paiement"), max_length=20,
        choices=PaymentMethod.choices, blank=True,
    )

    notes = models.TextField(_("notes"), blank=True)
    reserved_at = models.DateTimeField(_("date de réservation"), null=True, blank=True)
    completed_at = models.DateTimeField(_("date de finalisation"), null=True, blank=True)
    cancelled_at = models.DateTimeField(_("date d'annulation"), null=True, blank=True)

    # ── Séquestre (Escrow) ──
    escrow_funded = models.BooleanField(_("séquestre alimenté"), default=False)
    escrow_amount = models.DecimalField(
        _("montant séquestre (FCFA)"), max_digits=15, decimal_places=0,
        null=True, blank=True,
    )
    escrow_funded_at = models.DateTimeField(
        _("date alimentation séquestre"), null=True, blank=True,
    )
    escrow_released = models.BooleanField(_("séquestre libéré"), default=False)
    escrow_released_at = models.DateTimeField(
        _("date libération séquestre"), null=True, blank=True,
    )
    buyer_docs_confirmed = models.BooleanField(
        _("acheteur a confirmé réception docs"), default=False,
    )
    buyer_docs_confirmed_at = models.DateTimeField(null=True, blank=True)

    # ── Compromis de vente ──
    compromis_generated = models.BooleanField(
        _("compromis généré"), default=False,
    )
    compromis_generated_at = models.DateTimeField(null=True, blank=True)
    compromis_signed_buyer = models.BooleanField(_("signé par l'acheteur"), default=False)
    compromis_signed_seller = models.BooleanField(_("signé par le vendeur"), default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Transaction")
        verbose_name_plural = _("Transactions")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["buyer", "-created_at"]),
            models.Index(fields=["seller", "-created_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"TX-{self.reference} | {self.parcelle.lot_number} | {self.get_status_display()}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"EYF-{int(time.time())}"
        super().save(*args, **kwargs)

    @property
    def escrow_status_label(self):
        if self.escrow_released:
            return "Libéré"
        if self.buyer_docs_confirmed:
            return "Docs confirmés — En attente libération"
        if self.escrow_funded:
            return "Alimenté — En attente confirmation docs"
        return "Non alimenté"

    @property
    def progress_percent(self):
        steps = [
            self.status != self.Status.PENDING,      # Réservé
            self.escrow_funded,                       # Séquestre
            self.buyer_docs_confirmed,                # Docs OK
            self.compromis_generated,                 # Compromis
            self.status == self.Status.COMPLETED,     # Finalisé
        ]
        return int(sum(steps) / len(steps) * 100)


class BonDeVisite(models.Model):
    """Bon de visite numérique — ticket pour visiter physiquement une parcelle.

    Permet à EYE-Foncier de tracer qui visite quoi et d'assurer le suivi.
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("En attente de validation")
        APPROVED = "approved", _("Approuvé")
        USED = "used", _("Utilisé — Visite effectuée")
        EXPIRED = "expired", _("Expiré")
        CANCELLED = "cancelled", _("Annulé")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(_("référence"), max_length=30, unique=True)
    parcelle = models.ForeignKey(
        Parcelle, on_delete=models.CASCADE, related_name="bons_visite",
    )
    visitor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="visitor_bons_visite", verbose_name=_("visiteur"),
    )
    status = models.CharField(
        _("statut"), max_length=20, choices=Status.choices, default=Status.PENDING,
    )
    visit_date = models.DateTimeField(_("date de visite prévue"))
    visit_notes = models.TextField(_("notes / commentaires"), blank=True)
    feedback = models.TextField(_("retour après visite"), blank=True)
    feedback_rating = models.PositiveSmallIntegerField(
        _("note (1-5)"), null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Bon de visite")
        verbose_name_plural = _("Bons de visite")
        ordering = ["-created_at"]

    def __str__(self):
        return f"BV-{self.reference} | {self.parcelle.lot_number} | {self.visitor}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"BV-{int(time.time())}"
        super().save(*args, **kwargs)


class FinancialScore(models.Model):
    """Scoring financier d'un acquéreur — évalue la capacité d'achat."""

    class Grade(models.TextChoices):
        A = "A", _("Excellent (80-100)")
        B = "B", _("Bon (60-79)")
        C = "C", _("Moyen (40-59)")
        D = "D", _("Faible (20-39)")
        E = "E", _("Insuffisant (0-19)")

    class EmploymentType(models.TextChoices):
        SALARIE = "salarie", _("Salarié")
        FONCTIONNAIRE = "fonctionnaire", _("Fonctionnaire")
        INDEPENDANT = "independant", _("Indépendant")
        ENTREPRENEUR = "entrepreneur", _("Entrepreneur")
        INFORMEL = "informel", _("Secteur informel")
        AUTRE = "autre", _("Autre")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="financial_score", verbose_name=_("utilisateur"),
    )

    # Scores par composante (0-100)
    overall_score = models.FloatField(_("score global (0-100)"), null=True, blank=True)
    score_kyc = models.FloatField(_("score KYC"), default=0)
    score_revenue = models.FloatField(_("score revenus"), default=0)
    score_history = models.FloatField(_("score historique"), default=0)
    score_mobile_money = models.FloatField(_("score Mobile Money"), default=0)

    grade = models.CharField(
        _("grade"), max_length=1, choices=Grade.choices, blank=True,
    )

    # Capacité financière
    max_purchase_capacity = models.DecimalField(
        _("capacité max achat (FCFA)"), max_digits=15, decimal_places=0,
        null=True, blank=True,
    )
    monthly_capacity = models.DecimalField(
        _("capacité mensuelle (FCFA)"), max_digits=12, decimal_places=0,
        null=True, blank=True,
    )

    # Informations déclarées
    revenue_declared = models.DecimalField(
        _("revenus déclarés (FCFA/mois)"), max_digits=12, decimal_places=0,
        null=True, blank=True,
    )
    revenue_proof = models.FileField(
        _("justificatif revenus"), upload_to="scoring/revenue/%Y/%m/", blank=True,
    )
    mobile_money_verified = models.BooleanField(
        _("compte Mobile Money vérifié"), default=False,
    )
    employer_name = models.CharField(_("employeur"), max_length=200, blank=True)
    employment_type = models.CharField(
        _("type d'emploi"), max_length=20,
        choices=EmploymentType.choices, blank=True,
    )

    breakdown = models.JSONField(_("détails du calcul"), default=dict, blank=True)
    computed_at = models.DateTimeField(_("dernier calcul"), auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Score financier")
        verbose_name_plural = _("Scores financiers")
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["grade"]),
        ]

    def __str__(self):
        return f"Score {self.user} — {self.grade or '?'} ({self.overall_score or 0:.0f}/100)"


class SimulationResult(models.Model):
    """Résultat d'une simulation d'achat-vente."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="simulations", null=True, blank=True,
        verbose_name=_("utilisateur"),
    )
    parcelle = models.ForeignKey(
        Parcelle, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="simulations",
    )

    property_price = models.DecimalField(
        _("prix du bien (FCFA)"), max_digits=15, decimal_places=0,
    )
    down_payment = models.DecimalField(
        _("apport initial (FCFA)"), max_digits=15, decimal_places=0,
    )
    loan_amount = models.DecimalField(
        _("montant emprunt (FCFA)"), max_digits=15, decimal_places=0,
    )
    duration_months = models.PositiveIntegerField(_("durée (mois)"))
    interest_rate = models.DecimalField(
        _("taux d'intérêt annuel (%)"), max_digits=5, decimal_places=2,
    )
    monthly_payment = models.DecimalField(
        _("mensualité (FCFA)"), max_digits=12, decimal_places=0,
    )
    total_cost = models.DecimalField(
        _("coût total (FCFA)"), max_digits=15, decimal_places=0,
    )
    total_interest = models.DecimalField(
        _("total intérêts (FCFA)"), max_digits=15, decimal_places=0,
    )
    amortization_table = models.JSONField(
        _("tableau d'amortissement"), default=list, blank=True,
    )
    is_feasible = models.BooleanField(_("réalisable"), default=True)
    feasibility_notes = models.TextField(_("notes de faisabilité"), blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Simulation d'achat")
        verbose_name_plural = _("Simulations d'achat")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Simulation {self.user} — {self.property_price:,.0f} FCFA"


class TransactionEvent(models.Model):
    """Événement dans la timeline d'une transaction (audit trail)."""

    class EventType(models.TextChoices):
        CREATED = "created", _("Créée")
        RESERVED = "reserved", _("Réservée")
        ESCROW_FUNDED = "escrow_funded", _("Séquestre alimenté")
        DOCS_VALIDATED = "docs_validated", _("Documents validés")
        COMPROMIS_GENERATED = "compromis_generated", _("Compromis généré")
        COMPROMIS_SIGNED = "compromis_signed", _("Compromis signé")
        PAID = "paid", _("Payée")
        COMPLETED = "completed", _("Finalisée")
        CANCELLED = "cancelled", _("Annulée")
        DISPUTED = "disputed", _("Litige ouvert")
        DISPUTE_RESOLVED = "dispute_resolved", _("Litige résolu")
        REFUND_INITIATED = "refund_initiated", _("Remboursement initié")
        REFUND_COMPLETED = "refund_completed", _("Remboursement effectué")
        NOTE_ADDED = "note_added", _("Note ajoutée")
        APPROVAL_REQUESTED = "approval_requested", _("Approbation demandée")
        APPROVAL_APPROVED = "approval_approved", _("Approbation accordée")
        APPROVAL_REJECTED = "approval_rejected", _("Approbation refusée")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction = models.ForeignKey(
        Transaction, on_delete=models.CASCADE, related_name="events",
        verbose_name=_("transaction"),
    )
    event_type = models.CharField(
        _("type"), max_length=25, choices=EventType.choices,
    )
    old_status = models.CharField(_("ancien statut"), max_length=20, blank=True)
    new_status = models.CharField(_("nouveau statut"), max_length=20, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name=_("acteur"),
    )
    description = models.TextField(_("description"), blank=True)
    metadata = models.JSONField(_("métadonnées"), default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Événement transaction")
        verbose_name_plural = _("Événements transactions")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["transaction", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.transaction.reference} — {self.get_event_type_display()}"


class TransactionApproval(models.Model):
    """Demande d'approbation pour une opération de transaction."""

    class OperationType(models.TextChoices):
        RESERVE = "reserve", _("Réservation")
        ESCROW_FUND = "escrow_fund", _("Alimentation séquestre")
        DOCS_CONFIRM = "docs_confirm", _("Confirmation documents")
        COMPROMIS = "compromis", _("Compromis de vente")

    class Status(models.TextChoices):
        PENDING = "pending", _("En attente")
        APPROVED = "approved", _("Approuvé")
        REJECTED = "rejected", _("Refusé")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction = models.ForeignKey(
        Transaction, on_delete=models.CASCADE, related_name="approvals",
        verbose_name=_("transaction"),
    )
    operation_type = models.CharField(
        _("type d'opération"), max_length=20, choices=OperationType.choices,
    )
    status = models.CharField(
        _("statut"), max_length=20, choices=Status.choices, default=Status.PENDING,
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="approval_requests", verbose_name=_("demandeur"),
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="approval_reviews",
        verbose_name=_("valideur"),
    )
    reason = models.TextField(_("motif du refus"), blank=True)
    metadata = models.JSONField(_("métadonnées"), default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(_("date de validation"), null=True, blank=True)

    class Meta:
        verbose_name = _("Approbation")
        verbose_name_plural = _("Approbations")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["transaction", "operation_type"],
                condition=models.Q(status="pending"),
                name="unique_pending_approval_per_op",
            )
        ]

    def __str__(self):
        return f"{self.transaction.reference} — {self.get_operation_type_display()} ({self.get_status_display()})"


class ContractSignature(models.Model):
    """Signature électronique pour les contrats de transaction."""

    class SignerRole(models.TextChoices):
        BUYER = "buyer", _("Acheteur")
        SELLER = "seller", _("Vendeur")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction = models.ForeignKey(
        Transaction, on_delete=models.CASCADE, related_name="signatures"
    )
    signer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="contract_signatures"
    )
    role = models.CharField(max_length=10, choices=SignerRole.choices)
    signature_data = models.TextField(
        help_text=_("Donnée base64 du canvas de signature")
    )
    signed_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    device_info = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = _("Signature de contrat")
        verbose_name_plural = _("Signatures de contrats")
        constraints = [
            models.UniqueConstraint(
                fields=["transaction", "role"],
                name="unique_signature_per_role",
            )
        ]

    def __str__(self):
        return f"{self.transaction.reference} — {self.get_role_display()} signé"

# ═══════════════════════════════════════════════════════════
# FACTURATION — Factures automatiques
# ═══════════════════════════════════════════════════════════

class Invoice(models.Model):
    """Facture générée automatiquement pour chaque paiement confirmé.

    Types de factures :
    - COTATION : 10% du prix de la parcelle (acheteur)
    - BOUTIQUE : Abonnement vendeur (50 000 FCFA)
    - PROMOTION : Campagne publicitaire
    - CERTIFICATION : Frais de certification
    - VISITE : Bon de visite (5 000 FCFA)
    """

    class InvoiceType(models.TextChoices):
        COTATION = "cotation", _("Cotation achat")
        BOUTIQUE = "boutique", _("Abonnement boutique")
        PROMOTION = "promotion", _("Campagne promotion")
        CERTIFICATION = "certification", _("Certification")
        VISITE = "visite", _("Bon de visite")

    class InvoiceStatus(models.TextChoices):
        DRAFT = "draft", _("Brouillon")
        ISSUED = "issued", _("Émise")
        PAID = "paid", _("Payée")
        OVERDUE = "overdue", _("En retard")
        CANCELLED = "cancelled", _("Annulée")
        REFUNDED = "refunded", _("Remboursée")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice_number = models.CharField(
        _("numéro de facture"), max_length=30, unique=True,
        help_text=_("Format: FAC-YYYYMM-XXXX"),
    )
    reference = models.CharField(
        _("référence interne"), max_length=50, unique=True,
    )

    # ── Client ──
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="invoices", verbose_name=_("client"),
    )
    client_name = models.CharField(_("nom client (snapshot)"), max_length=200)
    client_email = models.EmailField(_("email client (snapshot)"), blank=True)
    client_phone = models.CharField(_("téléphone client"), max_length=20, blank=True)

    # ── Type & Montant ──
    invoice_type = models.CharField(
        _("type"), max_length=20, choices=InvoiceType.choices,
    )
    status = models.CharField(
        _("statut"), max_length=20,
        choices=InvoiceStatus.choices, default=InvoiceStatus.DRAFT,
    )

    # Montants
    subtotal = models.DecimalField(
        _("montant HT (FCFA)"), max_digits=15, decimal_places=0,
    )
    tax_rate = models.DecimalField(
        _("taux TVA (%)"), max_digits=5, decimal_places=2, default=0,
        help_text=_("0 pour exonéré."),
    )
    tax_amount = models.DecimalField(
        _("montant TVA (FCFA)"), max_digits=15, decimal_places=0, default=0,
    )
    total = models.DecimalField(
        _("montant TTC (FCFA)"), max_digits=15, decimal_places=0,
    )
    currency = models.CharField(_("devise"), max_length=3, default="XOF")

    # ── Description ──
    description = models.CharField(_("description"), max_length=500)
    line_items = models.JSONField(
        _("lignes de facture"), default=list,
        help_text=_("Liste [{description, quantity, unit_price, total}]."),
    )

    # ── Lien paiement ──
    payment_reference = models.CharField(
        _("référence paiement"), max_length=100, blank=True,
        help_text=_("ID transaction CinetPay."),
    )
    payment_method = models.CharField(
        _("mode de paiement"), max_length=30, blank=True,
        choices=[
            ("mobile_money", _("Mobile Money")),
            ("wave", _("Wave")),
            ("carte", _("Carte bancaire")),
            ("virement", _("Virement")),
        ],
    )
    paid_at = models.DateTimeField(_("date de paiement"), null=True, blank=True)

    # ── Relations optionnelles ──
    cotation = models.OneToOneField(
        "Cotation", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="invoice",
        verbose_name=_("cotation liée"),
    )
    transaction = models.ForeignKey(
        Transaction, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="invoices",
        verbose_name=_("transaction liée"),
    )
    parcelle = models.ForeignKey(
        Parcelle, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="invoices",
        verbose_name=_("parcelle liée"),
    )

    # ── Fichier PDF ──
    pdf_file = models.FileField(
        _("fichier PDF"), upload_to="invoices/%Y/%m/",
        blank=True,
    )

    # ── Dates ──
    issued_at = models.DateTimeField(_("date d'émission"), null=True, blank=True)
    due_date = models.DateField(_("date d'échéance"), null=True, blank=True)

    # ── Audit ──
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(_("notes internes"), blank=True)

    class Meta:
        verbose_name = _("Facture")
        verbose_name_plural = _("Factures")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["invoice_number"]),
            models.Index(fields=["status"]),
            models.Index(fields=["client"]),
        ]

    def __str__(self):
        return f"{self.invoice_number} — {self.client_name} — {self.total:,.0f} FCFA"

    def save(self, *args, **kwargs):
        # Auto-calculer la TVA et le total
        if self.subtotal:
            self.tax_amount = int(self.subtotal * self.tax_rate / 100)
            self.total = self.subtotal + self.tax_amount
        # Générer le numéro si manquant
        if not self.invoice_number:
            self.invoice_number = self._generate_invoice_number()
        if not self.reference:
            self.reference = f"INV-{int(time.time())}-{str(self.pk)[:8] if self.pk else uuid.uuid4().hex[:8]}"
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_invoice_number():
        """Génère un numéro séquentiel : FAC-YYYYMM-XXXX."""
        from django.utils import timezone
        now = timezone.now()
        prefix = f"FAC-{now.strftime('%Y%m')}"
        last = (
            Invoice.objects
            .filter(invoice_number__startswith=prefix)
            .order_by("-invoice_number")
            .values_list("invoice_number", flat=True)
            .first()
        )
        if last:
            try:
                seq = int(last.split("-")[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = 1
        return f"{prefix}-{seq:04d}"


# ── Import des modèles Cotation / Boutique / Vérification ──
from .cotation_models import Cotation, Boutique, VerificationRequest  # noqa: F401, E402
