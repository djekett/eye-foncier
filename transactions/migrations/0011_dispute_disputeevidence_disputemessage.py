"""
Migration : Modeles Litiges (Dispute, DisputeEvidence, DisputeMessage)
"""
import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("transactions", "0010_boutique_commune_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="Dispute",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("reference", models.CharField(editable=False, max_length=30, unique=True, verbose_name="reference")),
                ("category", models.CharField(
                    choices=[
                        ("fraud", "Fraude suspectee"),
                        ("non_conformity", "Non-conformite du terrain"),
                        ("payment", "Probleme de paiement"),
                        ("docs_missing", "Documents manquants ou falsifies"),
                        ("boundary", "Litige de bornage"),
                        ("title_issue", "Probleme de titre foncier"),
                        ("seller_no_response", "Vendeur injoignable"),
                        ("buyer_withdrawal", "Retractation de l'acheteur"),
                        ("other", "Autre"),
                    ],
                    max_length=30, verbose_name="categorie",
                )),
                ("priority", models.CharField(
                    choices=[("low", "Basse"), ("normal", "Normale"), ("high", "Haute"), ("urgent", "Urgente")],
                    default="normal", max_length=10, verbose_name="priorite",
                )),
                ("status", models.CharField(
                    choices=[
                        ("opened", "Ouvert"), ("under_review", "En cours d'examen"),
                        ("mediation", "Mediation en cours"), ("escalated", "Escalade (juridique)"),
                        ("resolved", "Resolu"), ("closed", "Clos"),
                    ],
                    default="opened", max_length=20, verbose_name="statut",
                )),
                ("subject", models.CharField(max_length=200, verbose_name="sujet")),
                ("description", models.TextField(verbose_name="description detaillee")),
                ("resolution_type", models.CharField(
                    blank=True,
                    choices=[
                        ("full_refund", "Remboursement integral"),
                        ("partial_refund", "Remboursement partiel"),
                        ("no_refund", "Pas de remboursement"),
                        ("transaction_resumed", "Transaction reprise"),
                        ("mutual_agreement", "Accord a l'amiable"),
                        ("external_arbitration", "Arbitrage externe"),
                    ],
                    max_length=30, verbose_name="type de resolution",
                )),
                ("resolution_notes", models.TextField(blank=True, verbose_name="notes de resolution")),
                ("refund_amount", models.DecimalField(
                    blank=True, decimal_places=0, max_digits=15, null=True,
                    verbose_name="montant rembourse (FCFA)",
                )),
                ("refund_processed", models.BooleanField(default=False, verbose_name="remboursement effectue")),
                ("refund_processed_at", models.DateTimeField(blank=True, null=True)),
                ("deadline", models.DateTimeField(blank=True, null=True, verbose_name="date limite de resolution")),
                ("escalated_at", models.DateTimeField(blank=True, null=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict, verbose_name="metadonnees")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("transaction", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="disputes",
                    to="transactions.transaction",
                    verbose_name="transaction",
                )),
                ("opened_by", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="disputes_opened",
                    to=settings.AUTH_USER_MODEL,
                    verbose_name="ouvert par",
                )),
                ("assigned_to", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="disputes_assigned",
                    to=settings.AUTH_USER_MODEL,
                    verbose_name="assigne a",
                )),
            ],
            options={
                "verbose_name": "Litige",
                "verbose_name_plural": "Litiges",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="dispute",
            index=models.Index(fields=["status"], name="tx_dispute_status_idx"),
        ),
        migrations.AddIndex(
            model_name="dispute",
            index=models.Index(fields=["priority", "-created_at"], name="tx_dispute_priority_idx"),
        ),
        migrations.AddIndex(
            model_name="dispute",
            index=models.Index(fields=["transaction"], name="tx_dispute_transaction_idx"),
        ),
        migrations.AddIndex(
            model_name="dispute",
            index=models.Index(fields=["assigned_to", "status"], name="tx_dispute_assigned_idx"),
        ),
        migrations.AddIndex(
            model_name="dispute",
            index=models.Index(fields=["opened_by"], name="tx_dispute_opened_by_idx"),
        ),
        migrations.CreateModel(
            name="DisputeEvidence",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("evidence_type", models.CharField(
                    choices=[
                        ("document", "Document"), ("photo", "Photo"),
                        ("screenshot", "Capture d'ecran"), ("message", "Conversation / Message"),
                        ("contract", "Contrat / Compromis"), ("payment_proof", "Preuve de paiement"),
                        ("survey", "Plan de bornage"), ("other", "Autre"),
                    ],
                    max_length=20, verbose_name="type",
                )),
                ("title", models.CharField(max_length=200, verbose_name="titre")),
                ("description", models.TextField(blank=True, verbose_name="description")),
                ("file", models.FileField(upload_to="disputes/evidences/%Y/%m/", verbose_name="fichier")),
                ("file_size", models.PositiveIntegerField(default=0, verbose_name="taille (octets)")),
                ("verified", models.BooleanField(default=False, verbose_name="verifie par admin")),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("dispute", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="evidences",
                    to="transactions.dispute",
                    verbose_name="litige",
                )),
                ("uploaded_by", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="dispute_evidences",
                    to=settings.AUTH_USER_MODEL,
                    verbose_name="soumis par",
                )),
                ("verified_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="verified_evidences",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "verbose_name": "Piece a conviction",
                "verbose_name_plural": "Pieces a conviction",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="DisputeMessage",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("sender_role", models.CharField(
                    choices=[
                        ("buyer", "Acheteur"), ("seller", "Vendeur"),
                        ("mediator", "Mediateur"), ("system", "Systeme"),
                    ],
                    max_length=10, verbose_name="role",
                )),
                ("content", models.TextField(verbose_name="message")),
                ("attachment", models.FileField(
                    blank=True, upload_to="disputes/messages/%Y/%m/",
                    verbose_name="piece jointe",
                )),
                ("read_by_buyer", models.BooleanField(default=False)),
                ("read_by_seller", models.BooleanField(default=False)),
                ("read_by_mediator", models.BooleanField(default=False)),
                ("is_internal", models.BooleanField(default=False, verbose_name="note interne")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("dispute", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="messages",
                    to="transactions.dispute",
                    verbose_name="litige",
                )),
                ("sender", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="dispute_messages",
                    to=settings.AUTH_USER_MODEL,
                    verbose_name="expediteur",
                )),
            ],
            options={
                "verbose_name": "Message litige",
                "verbose_name_plural": "Messages litige",
                "ordering": ["created_at"],
            },
        ),
    ]
