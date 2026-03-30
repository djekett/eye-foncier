"""
Modèles du coffre-fort documentaire — EYE-FONCIER
Stockage sécurisé avec traçabilité.
"""
import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from parcelles.models import Parcelle


class ParcelleDocument(models.Model):
    """Document administratif sécurisé lié à une parcelle."""

    class DocType(models.TextChoices):
        TITRE_FONCIER = "titre_foncier", _("Titre Foncier")
        ACD = "acd", _("Arrêté de Concession Définitive (ACD)")
        CERTIFICAT = "certificat", _("Certificat de propriété")
        PLAN = "plan", _("Plan cadastral")
        PERMIS = "permis", _("Permis de construire")
        ATTESTATION = "attestation", _("Attestation villageoise")
        AUTRE = "autre", _("Autre document")

    class Confidentiality(models.TextChoices):
        PUBLIC = "public", _("Public — Visible par tous")
        BUYER_ONLY = "buyer_only", _("Acheteurs vérifiés uniquement")
        PRIVATE = "private", _("Privé — Admin seulement")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parcelle = models.ForeignKey(
        Parcelle, on_delete=models.CASCADE, related_name="documents",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="uploaded_documents",
    )

    doc_type = models.CharField(
        _("type de document"), max_length=30, choices=DocType.choices,
    )
    title = models.CharField(_("titre du document"), max_length=300)
    description = models.TextField(_("description"), blank=True)
    file = models.FileField(_("fichier"), upload_to="documents/secure/%Y/%m/")
    file_hash = models.CharField(
        _("hash SHA-256"), max_length=64, blank=True,
        help_text=_("Empreinte du fichier pour vérification d'intégrité."),
    )
    confidentiality = models.CharField(
        _("niveau de confidentialité"), max_length=20,
        choices=Confidentiality.choices, default=Confidentiality.BUYER_ONLY,
    )
    is_verified = models.BooleanField(
        _("vérifié"), default=False,
        help_text=_("Le document a été vérifié par un administrateur."),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Document de parcelle")
        verbose_name_plural = _("Documents de parcelles")
        ordering = ["doc_type", "-created_at"]

    def __str__(self):
        return f"{self.get_doc_type_display()} — {self.parcelle.lot_number}"


class DocumentAccessLog(models.Model):
    """Trace chaque consultation de document."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        ParcelleDocument, on_delete=models.CASCADE, related_name="access_logs",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    action = models.CharField(max_length=50, default="view")
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Log consultation document")
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["document", "-timestamp"]),
        ]

    def __str__(self):
        return f"{self.user} → {self.document} @ {self.timestamp:%Y-%m-%d %H:%M}"
