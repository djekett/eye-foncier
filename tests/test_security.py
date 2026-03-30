"""
Tests de securite — EYE-FONCIER
Verifie les protections critiques de la plateforme.
"""
import os
import pytest
from django.test import TestCase, RequestFactory, override_settings
from django.contrib.auth import get_user_model

User = get_user_model()


class SettingsSecurityTest(TestCase):
    """Verifie que les settings de securite sont correctement configurees."""

    def test_secret_key_not_default_insecure(self):
        """SECRET_KEY ne doit pas etre la valeur insecure par defaut en production."""
        from django.conf import settings
        if not settings.DEBUG:
            self.assertNotIn("insecure", settings.SECRET_KEY.lower())

    def test_database_password_not_hardcoded(self):
        """Le mot de passe DB ne doit plus etre en dur dans settings.py."""
        settings_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "eyefoncier", "settings.py"
        )
        with open(settings_path, "r") as f:
            content = f.read()
        # Verifier qu'aucun mot de passe n'est en dur
        self.assertNotIn('"PASSWORD": "Lynkwb123."', content)
        self.assertIn('os.environ.get("DATABASE_PASSWORD"', content)

    def test_allowed_hosts_no_wildcard(self):
        """ALLOWED_HOSTS ne doit pas contenir de wildcard en production."""
        from django.conf import settings
        if not settings.DEBUG:
            self.assertNotIn("*", settings.ALLOWED_HOSTS)

    def test_debug_defaults_to_false(self):
        """Verifier que DEBUG est False par defaut (sans variable d'environnement)."""
        settings_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "eyefoncier", "settings.py"
        )
        with open(settings_path, "r") as f:
            content = f.read()
        # Le default doit etre "False" pas "True"
        self.assertIn('get("DJANGO_DEBUG", "False")', content)


class AuthorizationTest(TestCase):
    """Verifie les controles d'acces critiques."""

    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@test.com",
            username="owner",
            password="testpass123456",
            role="vendeur",
        )
        self.other_user = User.objects.create_user(
            email="other@test.com",
            username="other",
            password="testpass123456",
            role="acheteur",
        )

    def test_unauthenticated_cannot_access_notifications_api(self):
        """Les notifications API necessitent une authentification."""
        response = self.client.get("/api/v1/notifications/")
        self.assertIn(response.status_code, [401, 403])

    def test_unauthenticated_cannot_access_preferences(self):
        """La page preferences necessite une authentification."""
        response = self.client.get("/notifications/preferences/")
        self.assertIn(response.status_code, [302, 401, 403])


class FileUploadValidationTest(TestCase):
    """Verifie la validation des uploads de fichiers."""

    def test_document_form_rejects_exe_extension(self):
        """Le formulaire doit rejeter les fichiers .exe."""
        from documents.forms import DocumentUploadForm
        from django.core.files.uploadedfile import SimpleUploadedFile

        exe_file = SimpleUploadedFile(
            "malware.exe",
            b"MZ\x90\x00\x03\x00\x00\x00",
            content_type="application/x-msdownload",
        )
        form = DocumentUploadForm(
            data={
                "doc_type": "titre_foncier",
                "title": "Test",
                "description": "Test",
                "confidentiality": "public",
            },
            files={"file": exe_file},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("file", form.errors)

    def test_document_form_rejects_oversized_file(self):
        """Le formulaire doit rejeter les fichiers trop volumineux."""
        from documents.forms import DocumentUploadForm, MAX_FILE_SIZE_MB
        from django.core.files.uploadedfile import SimpleUploadedFile

        # Creer un faux fichier PDF de 11 Mo
        size = (MAX_FILE_SIZE_MB + 1) * 1024 * 1024
        big_file = SimpleUploadedFile(
            "huge.pdf",
            b"%PDF" + b"\x00" * (size - 4),
            content_type="application/pdf",
        )
        form = DocumentUploadForm(
            data={
                "doc_type": "titre_foncier",
                "title": "Test",
                "description": "Test",
                "confidentiality": "public",
            },
            files={"file": big_file},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("file", form.errors)

    def test_document_form_accepts_valid_pdf(self):
        """Le formulaire doit accepter un PDF valide de taille raisonnable."""
        from documents.forms import DocumentUploadForm
        from django.core.files.uploadedfile import SimpleUploadedFile

        valid_pdf = SimpleUploadedFile(
            "document.pdf",
            b"%PDF-1.4 test content here",
            content_type="application/pdf",
        )
        form = DocumentUploadForm(
            data={
                "doc_type": "titre_foncier",
                "title": "Titre foncier test",
                "description": "Description test",
                "confidentiality": "public",
            },
            files={"file": valid_pdf},
        )
        # Le formulaire peut avoir d'autres erreurs liees a ForeignKey
        # mais le champ file doit etre valide
        if not form.is_valid():
            self.assertNotIn("file", form.errors)


class NotificationPreferenceTest(TestCase):
    """Verifie le systeme de preferences de notification."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="notif@test.com",
            username="notifuser",
            password="testpass123456",
        )

    def test_preferences_auto_created_on_user_creation(self):
        """Les preferences de notification doivent etre creees automatiquement."""
        from notifications.models import NotificationPreference
        prefs = NotificationPreference.objects.filter(user=self.user)
        self.assertTrue(prefs.exists())

    def test_preferences_default_values(self):
        """Verifier les valeurs par defaut des preferences."""
        from notifications.models import NotificationPreference
        prefs = NotificationPreference.objects.get(user=self.user)
        self.assertTrue(prefs.email_enabled)
        self.assertTrue(prefs.inapp_enabled)
        self.assertFalse(prefs.whatsapp_enabled)  # Desactive par defaut
        self.assertFalse(prefs.sms_enabled)  # Desactive par defaut

    def test_whatsapp_requires_consent_and_number(self):
        """WhatsApp necessite un numero et un consentement."""
        from notifications.forms import NotificationPreferenceForm
        from notifications.models import NotificationPreference

        prefs = NotificationPreference.objects.get(user=self.user)
        form = NotificationPreferenceForm(
            data={
                "email_enabled": True,
                "sms_enabled": False,
                "whatsapp_enabled": True,  # Activer sans numero
                "push_enabled": True,
                "inapp_enabled": True,
                "whatsapp_number": "",  # Pas de numero
                "whatsapp_consent": False,  # Pas de consentement
            },
            instance=prefs,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("whatsapp_number", form.errors)
        self.assertIn("whatsapp_consent", form.errors)
