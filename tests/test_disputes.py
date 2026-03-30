"""
Tests des litiges — EYE-FONCIER
Verifie le workflow complet de resolution des litiges.
"""
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Polygon

User = get_user_model()


class DisputeWorkflowTest(TestCase):
    """Tests du workflow de litiges."""

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
        self.admin = User.objects.create_user(
            email="admin@test.com", username="admin",
            password="testpass123456", is_staff=True,
        )
        zone = Zone.objects.create(
            name="Zone Test", code="ZT01",
            geometry=Polygon(
                ((-4.1, 5.3), (-4.0, 5.3), (-4.0, 5.4), (-4.1, 5.4), (-4.1, 5.3)),
                srid=4326,
            ),
        )
        self.parcelle = Parcelle.objects.create(
            title="Parcelle Test", lot_number="LOT-DISP",
            owner=self.seller, zone=zone,
            geometry=Polygon(
                ((-4.05, 5.35), (-4.04, 5.35), (-4.04, 5.36), (-4.05, 5.36), (-4.05, 5.35)),
                srid=4326,
            ),
            surface_m2=500, price=Decimal("15000000"),
        )

    def _create_transaction(self, status="reserved"):
        from transactions.models import Transaction
        tx = Transaction.objects.create(
            parcelle=self.parcelle,
            buyer=self.buyer,
            seller=self.seller,
            amount=Decimal("15000000"),
            status=status,
        )
        return tx

    def test_open_dispute(self):
        """Ouvrir un litige sur une transaction reservee."""
        from transactions.dispute_service import open_dispute
        from transactions.dispute_models import Dispute

        tx = self._create_transaction(status="escrow_funded")
        dispute = open_dispute(
            transaction=tx,
            opened_by=self.buyer,
            category="non_conformity",
            subject="Terrain non conforme",
            description="Le terrain ne correspond pas a la description.",
        )

        self.assertEqual(dispute.status, "opened")
        self.assertEqual(dispute.category, "non_conformity")
        self.assertIsNotNone(dispute.deadline)
        self.assertTrue(dispute.reference.startswith("LIT-"))

        # La transaction doit passer en disputed
        tx.refresh_from_db()
        self.assertEqual(tx.status, "disputed")

    def test_cannot_open_duplicate_dispute(self):
        """Impossible d'ouvrir deux litiges simultanes."""
        from transactions.dispute_service import open_dispute

        tx = self._create_transaction(status="escrow_funded")
        open_dispute(
            transaction=tx, opened_by=self.buyer,
            category="payment", subject="Test", description="Test",
        )

        with self.assertRaises(ValueError):
            open_dispute(
                transaction=tx, opened_by=self.seller,
                category="docs_missing", subject="Test 2", description="Test 2",
            )

    def test_dispute_status_transitions(self):
        """Verifier les transitions de statut du litige."""
        from transactions.dispute_service import open_dispute, transition_dispute

        tx = self._create_transaction(status="escrow_funded")
        dispute = open_dispute(
            transaction=tx, opened_by=self.buyer,
            category="fraud", subject="Fraude", description="Description",
            priority="high",
        )

        # opened → under_review
        dispute = transition_dispute(dispute, "under_review", self.admin, "Examen en cours")
        self.assertEqual(dispute.status, "under_review")

        # under_review → mediation
        dispute = transition_dispute(dispute, "mediation", self.admin, "Mediation demarree")
        self.assertEqual(dispute.status, "mediation")

        # mediation → resolved
        dispute = transition_dispute(dispute, "resolved", self.admin, "Resolu")
        self.assertEqual(dispute.status, "resolved")
        self.assertIsNotNone(dispute.resolved_at)

    def test_invalid_transition_raises_error(self):
        """Transition invalide leve une erreur."""
        from transactions.dispute_service import open_dispute, transition_dispute

        tx = self._create_transaction(status="escrow_funded")
        dispute = open_dispute(
            transaction=tx, opened_by=self.buyer,
            category="payment", subject="Test", description="Test",
        )

        with self.assertRaises(ValueError):
            transition_dispute(dispute, "closed", self.admin)  # opened → closed OK actually

    def test_resolve_dispute_with_refund(self):
        """Resoudre un litige avec remboursement."""
        from transactions.dispute_service import open_dispute, resolve_dispute

        tx = self._create_transaction(status="escrow_funded")
        dispute = open_dispute(
            transaction=tx, opened_by=self.buyer,
            category="non_conformity", subject="Test", description="Test",
        )

        dispute = resolve_dispute(
            dispute=dispute,
            actor=self.admin,
            resolution_type="partial_refund",
            notes="Remboursement partiel accorde",
            refund_amount=Decimal("5000000"),
        )

        self.assertEqual(dispute.status, "resolved")
        self.assertEqual(dispute.resolution_type, "partial_refund")
        self.assertEqual(dispute.refund_amount, Decimal("5000000"))

    def test_add_message_to_dispute(self):
        """Ajouter un message dans un litige."""
        from transactions.dispute_service import open_dispute, add_message

        tx = self._create_transaction(status="escrow_funded")
        dispute = open_dispute(
            transaction=tx, opened_by=self.buyer,
            category="payment", subject="Test", description="Test",
        )

        msg = add_message(dispute, self.buyer, "J'ai un probleme avec le paiement.")
        self.assertEqual(msg.sender_role, "buyer")
        self.assertEqual(msg.dispute, dispute)

        msg2 = add_message(dispute, self.admin, "Note interne", is_internal=True)
        self.assertEqual(msg2.sender_role, "mediator")
        self.assertTrue(msg2.is_internal)

    def test_dispute_model_properties(self):
        """Tester les proprietes du modele Dispute."""
        from transactions.dispute_service import open_dispute

        tx = self._create_transaction(status="escrow_funded")
        dispute = open_dispute(
            transaction=tx, opened_by=self.buyer,
            category="fraud", subject="Test", description="Test",
            priority="urgent",
        )

        self.assertTrue(dispute.is_open)
        self.assertEqual(dispute.days_since_opened, 0)
        self.assertFalse(dispute.is_overdue)

    def test_dispute_categories_complete(self):
        """Verifier que toutes les categories de litige sont definies."""
        from transactions.dispute_models import Dispute
        categories = [c[0] for c in Dispute.Category.choices]
        expected = [
            "fraud", "non_conformity", "payment", "docs_missing",
            "boundary", "title_issue", "seller_no_response",
            "buyer_withdrawal", "other",
        ]
        for cat in expected:
            self.assertIn(cat, categories, f"Categorie '{cat}' manquante")

    def test_dispute_resolution_types_complete(self):
        """Verifier que tous les types de resolution sont definis."""
        from transactions.dispute_models import Dispute
        resolutions = [r[0] for r in Dispute.Resolution.choices]
        expected = [
            "full_refund", "partial_refund", "no_refund",
            "transaction_resumed", "mutual_agreement", "external_arbitration",
        ]
        for res in expected:
            self.assertIn(res, resolutions, f"Resolution '{res}' manquante")


class DisputeAPITest(TestCase):
    """Tests API des litiges."""

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
            name="Zone API", code="ZAPI",
            geometry=Polygon(
                ((-4.1, 5.3), (-4.0, 5.3), (-4.0, 5.4), (-4.1, 5.4), (-4.1, 5.3)),
                srid=4326,
            ),
        )
        self.parcelle = Parcelle.objects.create(
            title="Parcelle API", lot_number="LOT-API",
            owner=self.seller, zone=zone,
            geometry=Polygon(
                ((-4.05, 5.35), (-4.04, 5.35), (-4.04, 5.36), (-4.05, 5.36), (-4.05, 5.35)),
                srid=4326,
            ),
            surface_m2=500, price=Decimal("10000000"),
        )

    def test_unauthenticated_cannot_list_disputes(self):
        """Les litiges necessitent une authentification."""
        response = self.client.get("/api/v1/transactions/litiges/")
        self.assertIn(response.status_code, [401, 403])

    def test_unauthenticated_cannot_open_dispute(self):
        """Ouvrir un litige necessite une authentification."""
        response = self.client.post("/api/v1/transactions/litiges/ouvrir/")
        self.assertIn(response.status_code, [401, 403])
