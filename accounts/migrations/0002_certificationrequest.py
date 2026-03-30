"""Add CertificationRequest model for badge de confiance & visio-verification."""
import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CertificationRequest",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("cert_type", models.CharField(
                    choices=[("standard", "Standard — Upload de pièces"), ("visio", "Visio-Vérification (15min)"), ("premium", "Premium — Visite terrain")],
                    default="standard", max_length=20, verbose_name="type de certification",
                )),
                ("status", models.CharField(
                    choices=[("pending", "En attente"), ("scheduled", "RDV programmé"), ("in_review", "En cours d'examen"), ("approved", "Approuvé"), ("rejected", "Rejeté")],
                    default="pending", max_length=20, verbose_name="statut",
                )),
                ("message", models.TextField(blank=True, verbose_name="message du demandeur")),
                ("preferred_date", models.CharField(blank=True, help_text="Date/créneau préféré pour la visio ou visite.", max_length=100, verbose_name="date souhaitée")),
                ("admin_notes", models.TextField(blank=True, verbose_name="notes admin")),
                ("scheduled_at", models.DateTimeField(blank=True, null=True, verbose_name="RDV programmé")),
                ("caution_amount", models.DecimalField(blank=True, decimal_places=0, max_digits=10, null=True, verbose_name="caution déposée (FCFA)")),
                ("caution_paid", models.BooleanField(default=False, verbose_name="caution payée")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="certification_requests", to=settings.AUTH_USER_MODEL)),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_certifications", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Demande de certification",
                "verbose_name_plural": "Demandes de certification",
                "ordering": ["-created_at"],
            },
        ),
    ]
