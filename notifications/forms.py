"""Formulaires Notifications — EYE-FONCIER."""
import re

from django import forms
from django.core.exceptions import ValidationError

from .models import Notification, NotificationPreference


class NotificationPreferenceForm(forms.ModelForm):
    class Meta:
        model = NotificationPreference
        fields = [
            "email_enabled",
            "sms_enabled",
            "whatsapp_enabled",
            "push_enabled",
            "inapp_enabled",
            "whatsapp_number",
            "whatsapp_consent",
            "quiet_hours_start",
            "quiet_hours_end",
            "disabled_types",
        ]
        widgets = {
            "quiet_hours_start": forms.TimeInput(
                attrs={"type": "time", "class": "form-control"}
            ),
            "quiet_hours_end": forms.TimeInput(
                attrs={"type": "time", "class": "form-control"}
            ),
            "whatsapp_number": forms.TextInput(
                attrs={
                    "type": "tel",
                    "class": "form-control",
                    "placeholder": "+225XXXXXXXXXX",
                }
            ),
            "disabled_types": forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Construire les choix pour disabled_types
        self.notification_type_choices = Notification.NotificationType.choices

    def clean_whatsapp_number(self):
        number = self.cleaned_data.get("whatsapp_number", "").strip()
        if not number:
            return ""
        # Format international : +XXX...
        if not re.match(r"^\+\d{10,15}$", number):
            raise ValidationError(
                "Le numéro WhatsApp doit être au format international "
                "(ex: +225XXXXXXXXXX)."
            )
        return number

    def clean(self):
        cleaned = super().clean()
        whatsapp_enabled = cleaned.get("whatsapp_enabled")
        whatsapp_number = cleaned.get("whatsapp_number")
        whatsapp_consent = cleaned.get("whatsapp_consent")

        if whatsapp_enabled:
            if not whatsapp_number:
                self.add_error(
                    "whatsapp_number",
                    "Un numéro WhatsApp est requis pour activer les notifications.",
                )
            if not whatsapp_consent:
                self.add_error(
                    "whatsapp_consent",
                    "Vous devez donner votre consentement pour recevoir des messages WhatsApp.",
                )

        return cleaned
