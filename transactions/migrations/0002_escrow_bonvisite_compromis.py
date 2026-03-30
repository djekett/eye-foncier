"""Add escrow/compromis fields to Transaction + BonDeVisite model."""
import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── Escrow fields on Transaction ──
        migrations.AddField(
            model_name="transaction",
            name="escrow_funded",
            field=models.BooleanField(default=False, verbose_name="séquestre alimenté"),
        ),
        migrations.AddField(
            model_name="transaction",
            name="escrow_amount",
            field=models.DecimalField(blank=True, decimal_places=0, max_digits=15, null=True, verbose_name="montant séquestre (FCFA)"),
        ),
        migrations.AddField(
            model_name="transaction",
            name="escrow_funded_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="date alimentation séquestre"),
        ),
        migrations.AddField(
            model_name="transaction",
            name="escrow_released",
            field=models.BooleanField(default=False, verbose_name="séquestre libéré"),
        ),
        migrations.AddField(
            model_name="transaction",
            name="escrow_released_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="date libération séquestre"),
        ),
        migrations.AddField(
            model_name="transaction",
            name="buyer_docs_confirmed",
            field=models.BooleanField(default=False, verbose_name="acheteur a confirmé réception docs"),
        ),
        migrations.AddField(
            model_name="transaction",
            name="buyer_docs_confirmed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        # ── Compromis fields on Transaction ──
        migrations.AddField(
            model_name="transaction",
            name="compromis_generated",
            field=models.BooleanField(default=False, verbose_name="compromis généré"),
        ),
        migrations.AddField(
            model_name="transaction",
            name="compromis_generated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="transaction",
            name="compromis_signed_buyer",
            field=models.BooleanField(default=False, verbose_name="signé par l'acheteur"),
        ),
        migrations.AddField(
            model_name="transaction",
            name="compromis_signed_seller",
            field=models.BooleanField(default=False, verbose_name="signé par le vendeur"),
        ),
        # ── New Transaction statuses ──
        migrations.AlterField(
            model_name="transaction",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "En attente"), ("reserved", "Réservé"),
                    ("escrow_funded", "Séquestre alimenté"), ("docs_validated", "Documents validés"),
                    ("paid", "Payé"), ("completed", "Finalisé"),
                    ("cancelled", "Annulé"), ("disputed", "Litige"),
                ],
                default="pending", max_length=20, verbose_name="statut",
            ),
        ),
        migrations.AlterField(
            model_name="transaction",
            name="payment_method",
            field=models.CharField(
                blank=True,
                choices=[
                    ("virement", "Virement bancaire"), ("mobile_money", "Mobile Money"),
                    ("especes", "Espèces"), ("cheque", "Chèque"),
                    ("escrow", "Séquestre EYE-Foncier"), ("autre", "Autre"),
                ],
                max_length=20, verbose_name="mode de paiement",
            ),
        ),
        # ── BonDeVisite model ──
        migrations.CreateModel(
            name="BonDeVisite",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("reference", models.CharField(max_length=30, unique=True, verbose_name="référence")),
                ("status", models.CharField(
                    choices=[("pending", "En attente de validation"), ("approved", "Approuvé"), ("used", "Utilisé — Visite effectuée"), ("expired", "Expiré"), ("cancelled", "Annulé")],
                    default="pending", max_length=20, verbose_name="statut",
                )),
                ("visit_date", models.DateTimeField(verbose_name="date de visite prévue")),
                ("visit_notes", models.TextField(blank=True, verbose_name="notes / commentaires")),
                ("feedback", models.TextField(blank=True, verbose_name="retour après visite")),
                ("feedback_rating", models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="note (1-5)")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("parcelle", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bons_visite", to="parcelles.parcelle")),
                ("visitor", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bons_visite", to=settings.AUTH_USER_MODEL, verbose_name="visiteur")),
            ],
            options={
                "verbose_name": "Bon de visite",
                "verbose_name_plural": "Bons de visite",
                "ordering": ["-created_at"],
            },
        ),
    ]
