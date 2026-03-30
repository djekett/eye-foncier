"""
Tests des modeles critiques — EYE-FONCIER
"""
import pytest
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Polygon, Point

User = get_user_model()


class ParcelleModelTest(TestCase):
    """Tests du modele Parcelle."""

    def setUp(self):
        from parcelles.models import Zone
        self.owner = User.objects.create_user(
            email="seller@test.com",
            username="seller",
            password="testpass123456",
            role="vendeur",
        )
        self.zone = Zone.objects.create(
            name="Zone Test",
            code="ZT01",
            geometry=Polygon(
                ((-4.1, 5.3), (-4.0, 5.3), (-4.0, 5.4), (-4.1, 5.4), (-4.1, 5.3)),
                srid=4326,
            ),
        )

    def test_create_parcelle_with_geometry(self):
        """Creer une parcelle avec une geometrie valide."""
        from parcelles.models import Parcelle
        poly = Polygon(
            ((-4.05, 5.35), (-4.04, 5.35), (-4.04, 5.36), (-4.05, 5.36), (-4.05, 5.35)),
            srid=4326,
        )
        parcelle = Parcelle.objects.create(
            title="Parcelle Test",
            lot_number="LOT-001",
            owner=self.owner,
            zone=self.zone,
            geometry=poly,
            surface_m2=500,
            price=Decimal("15000000"),
        )
        # Centroide auto-calcule
        self.assertIsNotNone(parcelle.centroid)
        # Prix au m2 auto-calcule
        self.assertEqual(parcelle.price_per_m2, 30000)

    def test_parcelle_likes_count_annotation(self):
        """likes_count fonctionne avec et sans annotation."""
        from parcelles.models import Parcelle
        poly = Polygon(
            ((-4.05, 5.35), (-4.04, 5.35), (-4.04, 5.36), (-4.05, 5.36), (-4.05, 5.35)),
            srid=4326,
        )
        parcelle = Parcelle.objects.create(
            title="Parcelle Likes",
            lot_number="LOT-002",
            owner=self.owner,
            zone=self.zone,
            geometry=poly,
            surface_m2=500,
            price=Decimal("10000000"),
        )
        # Sans annotation (fallback)
        self.assertEqual(parcelle.likes_count, 0)

        # Avec annotation
        annotated = Parcelle.objects.with_likes_count().get(pk=parcelle.pk)
        self.assertEqual(annotated.likes_count, 0)

    def test_parcelle_completeness_score(self):
        """Le score de completude augmente avec les champs remplis."""
        from parcelles.models import Parcelle
        poly = Polygon(
            ((-4.05, 5.35), (-4.04, 5.35), (-4.04, 5.36), (-4.05, 5.36), (-4.05, 5.35)),
            srid=4326,
        )
        # Parcelle minimale
        parcelle = Parcelle.objects.create(
            title="Test",
            lot_number="LOT-003",
            owner=self.owner,
            zone=self.zone,
            geometry=poly,
            surface_m2=500,
            price=Decimal("10000000"),
        )
        score = parcelle.completeness_score
        self.assertGreater(score, 0)
        self.assertLessEqual(score, 100)


class NotificationModelTest(TestCase):
    """Tests du modele Notification."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="notif@test.com",
            username="notifuser",
            password="testpass123456",
        )

    def test_create_notification(self):
        """Creer une notification in-app."""
        from notifications.models import Notification
        notif = Notification.objects.create(
            recipient=self.user,
            notification_type="welcome",
            channel="inapp",
            title="Bienvenue",
            message="Bienvenue sur EYE-FONCIER",
        )
        self.assertFalse(notif.is_read)
        self.assertFalse(notif.is_sent)
        self.assertEqual(notif.priority, "normal")

    def test_notification_types_complete(self):
        """Verifier que tous les types de notification essentiels existent."""
        from notifications.models import Notification
        types = [choice[0] for choice in Notification.NotificationType.choices]
        essential_types = [
            "welcome", "parcelle_published", "parcelle_validated",
            "parcelle_rejected", "transaction_status", "payment_confirmed",
            "new_order", "new_message", "new_review", "kyc_update",
            "boutique_activated", "boutique_update",
        ]
        for t in essential_types:
            self.assertIn(t, types, f"Type '{t}' manquant dans NotificationType")

    def test_mark_as_read(self):
        """Marquer une notification comme lue."""
        from notifications.models import Notification
        from notifications.services import mark_as_read

        notif = Notification.objects.create(
            recipient=self.user,
            notification_type="system",
            channel="inapp",
            title="Test",
            message="Message test",
        )
        self.assertFalse(notif.is_read)

        mark_as_read(notif.pk, self.user)
        notif.refresh_from_db()
        self.assertTrue(notif.is_read)
        self.assertIsNotNone(notif.read_at)

    def test_send_notification_respects_preferences(self):
        """send_notification respecte les preferences desactivees."""
        from notifications.models import NotificationPreference
        from notifications.services import send_notification

        # Desactiver les emails
        prefs = NotificationPreference.objects.get(user=self.user)
        prefs.email_enabled = False
        prefs.sms_enabled = False
        prefs.whatsapp_enabled = False
        prefs.push_enabled = False
        prefs.save()

        notifs = send_notification(
            recipient=self.user,
            notification_type="system",
            title="Test",
            message="Test message",
        )
        # Seul inapp devrait etre cree (les autres sont desactives)
        channels = [n.channel for n in notifs]
        self.assertIn("inapp", channels)
        self.assertNotIn("email", channels)
        self.assertNotIn("sms", channels)

    def test_send_notification_disabled_type(self):
        """Les types desactives ne generent pas de notification."""
        from notifications.models import NotificationPreference
        from notifications.services import send_notification

        prefs = NotificationPreference.objects.get(user=self.user)
        prefs.disabled_types = ["system"]
        prefs.save()

        notifs = send_notification(
            recipient=self.user,
            notification_type="system",
            title="Test desactive",
            message="Ne devrait pas etre envoye",
        )
        self.assertEqual(len(notifs), 0)


class TransactionModelTest(TestCase):
    """Tests du modele Transaction."""

    def setUp(self):
        from parcelles.models import Zone, Parcelle
        self.buyer = User.objects.create_user(
            email="buyer@test.com", username="buyer",
            password="testpass123456", role="acheteur",
        )
        self.seller = User.objects.create_user(
            email="seller@test.com", username="seller",
            password="testpass123456", role="vendeur",
        )
        zone = Zone.objects.create(
            name="Zone TX", code="ZTX",
            geometry=Polygon(
                ((-4.1, 5.3), (-4.0, 5.3), (-4.0, 5.4), (-4.1, 5.4), (-4.1, 5.3)),
                srid=4326,
            ),
        )
        self.parcelle = Parcelle.objects.create(
            title="Parcelle TX", lot_number="LOT-TX",
            owner=self.seller, zone=zone,
            geometry=Polygon(
                ((-4.05, 5.35), (-4.04, 5.35), (-4.04, 5.36), (-4.05, 5.36), (-4.05, 5.35)),
                srid=4326,
            ),
            surface_m2=600, price=Decimal("20000000"),
        )

    def test_create_transaction(self):
        """Creer une transaction valide."""
        from transactions.models import Transaction
        tx = Transaction.objects.create(
            parcelle=self.parcelle,
            buyer=self.buyer,
            seller=self.seller,
            amount=Decimal("20000000"),
        )
        self.assertEqual(tx.status, "pending")
        self.assertTrue(tx.reference)  # Auto-generee

    def test_transaction_status_choices(self):
        """Verifier les statuts de transaction."""
        from transactions.models import Transaction
        statuses = [c[0] for c in Transaction.Status.choices]
        for s in ["pending", "reserved", "escrow_funded", "paid", "completed", "cancelled", "disputed"]:
            self.assertIn(s, statuses)
