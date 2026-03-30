"""
Modèles Notifications — EYE-FONCIER
Système de notifications multicanal (in-app, email, SMS, WhatsApp, push).
"""
import uuid
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Notification(models.Model):
    """Notification envoyée à un utilisateur via un canal donné."""

    class NotificationType(models.TextChoices):
        # Transactions
        TRANSACTION_STATUS = "transaction_status", _("Statut transaction")
        PAYMENT_CONFIRMED = "payment_confirmed", _("Paiement confirmé")
        PAYMENT_REMINDER = "payment_reminder", _("Rappel de paiement")
        ESCROW_UPDATE = "escrow_update", _("Mise à jour séquestre")
        SCORING_UPDATE = "scoring_update", _("Mise à jour scoring")
        # Parcelles
        PARCELLE_PUBLISHED = "parcelle_published", _("Parcelle publiée")
        PARCELLE_VALIDATED = "parcelle_validated", _("Parcelle validée")
        PARCELLE_REJECTED = "parcelle_rejected", _("Parcelle rejetée")
        PARCELLE_INTEREST = "parcelle_interest", _("Intérêt pour une parcelle")
        # Matching & Visites
        MATCH_FOUND = "match_found", _("Correspondance trouvée")
        VISIT_REQUEST = "visit_request", _("Demande de visite")
        VISIT_CONFIRMED = "visit_confirmed", _("Visite confirmée")
        # Communication
        NEW_MESSAGE = "new_message", _("Nouveau message")
        NEW_REVIEW = "new_review", _("Nouvel avis")
        CLIENT_REQUEST = "client_request", _("Demande client")
        # Compte
        KYC_UPDATE = "kyc_update", _("Mise à jour KYC")
        DOCUMENT_READY = "document_ready", _("Document disponible")
        ACCOUNT_UPDATE = "account_update", _("Mise à jour compte")
        WELCOME = "welcome", _("Bienvenue")
        # Système
        SYSTEM = "system", _("Système")

    class Channel(models.TextChoices):
        INAPP = "inapp", _("In-App")
        EMAIL = "email", _("Email")
        SMS = "sms", _("SMS")
        WHATSAPP = "whatsapp", _("WhatsApp")
        PUSH = "push", _("Push")

    class Priority(models.TextChoices):
        LOW = "low", _("Basse")
        NORMAL = "normal", _("Normale")
        HIGH = "high", _("Haute")
        URGENT = "urgent", _("Urgente")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name=_("destinataire"),
    )
    notification_type = models.CharField(
        _("type"), max_length=30, choices=NotificationType.choices
    )
    channel = models.CharField(
        _("canal"), max_length=10, choices=Channel.choices, default=Channel.INAPP
    )
    priority = models.CharField(
        _("priorité"), max_length=10,
        choices=Priority.choices, default=Priority.NORMAL,
    )
    title = models.CharField(_("titre"), max_length=300)
    message = models.TextField(_("message"))
    data = models.JSONField(_("données"), default=dict, blank=True)

    is_read = models.BooleanField(_("lu"), default=False)
    read_at = models.DateTimeField(_("lu le"), null=True, blank=True)
    is_sent = models.BooleanField(_("envoyé"), default=False)
    sent_at = models.DateTimeField(_("envoyé le"), null=True, blank=True)
    error_message = models.TextField(_("erreur d'envoi"), blank=True)
    retry_count = models.PositiveSmallIntegerField(_("tentatives"), default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Notification")
        verbose_name_plural = _("Notifications")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "-created_at"]),
            models.Index(fields=["is_read", "recipient"]),
            models.Index(fields=["notification_type", "-created_at"]),
            models.Index(fields=["channel", "is_sent"]),
        ]

    def __str__(self):
        return f"[{self.get_channel_display()}] {self.title} → {self.recipient}"


class NotificationPreference(models.Model):
    """Préférences de notification par utilisateur."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
        verbose_name=_("utilisateur"),
    )
    email_enabled = models.BooleanField(_("notifications email"), default=True)
    sms_enabled = models.BooleanField(_("notifications SMS"), default=False)
    whatsapp_enabled = models.BooleanField(_("notifications WhatsApp"), default=False)
    push_enabled = models.BooleanField(_("notifications push"), default=True)
    inapp_enabled = models.BooleanField(_("notifications in-app"), default=True)

    # WhatsApp
    whatsapp_number = models.CharField(
        _("numéro WhatsApp"), max_length=20, blank=True, default="",
        help_text=_("Numéro au format international (ex: +225XXXXXXXXXX)"),
    )
    whatsapp_consent = models.BooleanField(
        _("consentement WhatsApp"), default=False,
        help_text=_("L'utilisateur a donné son consentement pour recevoir des messages WhatsApp"),
    )
    whatsapp_verified = models.BooleanField(
        _("WhatsApp vérifié"), default=False,
        help_text=_("Le numéro WhatsApp a été vérifié"),
    )

    quiet_hours_start = models.TimeField(
        _("début heures calmes"), null=True, blank=True,
        help_text=_("Ex: 22:00 — pas de SMS/push/WhatsApp pendant cette période"),
    )
    quiet_hours_end = models.TimeField(
        _("fin heures calmes"), null=True, blank=True,
        help_text=_("Ex: 07:00"),
    )
    disabled_types = models.JSONField(
        _("types désactivés"), default=list, blank=True,
        help_text=_("Liste des types de notification à ignorer"),
    )

    # Token Firebase Cloud Messaging pour les notifications push
    fcm_token = models.CharField(
        _("token FCM"), max_length=500, blank=True, default="",
        help_text=_("Token Firebase Cloud Messaging du device"),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Préférence de notification")
        verbose_name_plural = _("Préférences de notification")

    def __str__(self):
        return f"Préférences de {self.user}"


class NotificationLog(models.Model):
    """Journal d'envoi des notifications pour traçabilité et débogage."""

    class Status(models.TextChoices):
        QUEUED = "queued", _("En file d'attente")
        SENDING = "sending", _("En cours d'envoi")
        SENT = "sent", _("Envoyé")
        DELIVERED = "delivered", _("Délivré")
        FAILED = "failed", _("Échoué")
        RETRYING = "retrying", _("Nouvelle tentative")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    notification = models.ForeignKey(
        Notification, on_delete=models.CASCADE,
        related_name="logs", verbose_name=_("notification"),
    )
    status = models.CharField(
        _("statut"), max_length=10, choices=Status.choices,
    )
    channel = models.CharField(
        _("canal"), max_length=10, choices=Notification.Channel.choices,
    )
    provider = models.CharField(
        _("fournisseur"), max_length=50, blank=True,
        help_text=_("Ex: twilio, infobip, fcm, smtp"),
    )
    provider_message_id = models.CharField(
        _("ID message fournisseur"), max_length=200, blank=True,
    )
    error_detail = models.TextField(_("détail erreur"), blank=True)
    response_data = models.JSONField(
        _("réponse fournisseur"), default=dict, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Log de notification")
        verbose_name_plural = _("Logs de notification")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["notification", "-created_at"]),
            models.Index(fields=["status", "channel"]),
        ]

    def __str__(self):
        return f"[{self.get_status_display()}] {self.channel} — {self.notification_id}"
