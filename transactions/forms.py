from django import forms
from .models import FinancialScore, Transaction


class ReservationForm(forms.Form):
    """Formulaire de réservation d'une parcelle."""
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "Message au vendeur (optionnel)...",
        }),
        label="Notes",
    )
    use_escrow = forms.BooleanField(
        required=False,
        label="Utiliser le séquestre EYE-Foncier (paiement sécurisé)",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text="Les fonds sont bloqués jusqu'à réception des documents légaux.",
    )
    confirm = forms.BooleanField(
        required=True,
        label="Je confirme vouloir réserver cette parcelle",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )


class TransactionUpdateForm(forms.ModelForm):
    """Mise à jour du statut de transaction (admin/vendeur)."""
    class Meta:
        model = Transaction
        fields = ["status", "payment_method", "notes"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-select"}),
            "payment_method": forms.Select(attrs={"class": "form-select"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


class FinancialProfileForm(forms.ModelForm):
    """Formulaire de profil financier pour le scoring."""

    class Meta:
        model = FinancialScore
        fields = [
            "revenue_declared",
            "revenue_proof",
            "employer_name",
            "employment_type",
            "mobile_money_verified",
        ]
        widgets = {
            "revenue_declared": forms.NumberInput(attrs={
                "class": "form-control",
                "placeholder": "Ex: 350 000",
                "min": "0",
            }),
            "revenue_proof": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "employer_name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Nom de l'employeur ou activité...",
            }),
            "employment_type": forms.Select(attrs={"class": "form-select"}),
            "mobile_money_verified": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "revenue_declared": "Revenus mensuels (FCFA)",
            "revenue_proof": "Justificatif (fiche de paie, relevé Mobile Money...)",
            "employer_name": "Employeur / Activité",
            "employment_type": "Situation professionnelle",
            "mobile_money_verified": "J'ai un compte Mobile Money vérifié",
        }


class SimulatorForm(forms.Form):
    """Formulaire du simulateur d'achat-vente."""

    property_price = forms.DecimalField(
        label="Prix du bien (FCFA)",
        max_digits=15,
        decimal_places=0,
        min_value=100_000,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "Ex: 15 000 000",
        }),
    )
    down_payment = forms.DecimalField(
        label="Apport initial (FCFA)",
        max_digits=15,
        decimal_places=0,
        min_value=0,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "Ex: 3 000 000",
        }),
    )
    duration_months = forms.ChoiceField(
        label="Durée de remboursement",
        choices=[
            (12, "12 mois (1 an)"),
            (24, "24 mois (2 ans)"),
            (36, "36 mois (3 ans)"),
            (48, "48 mois (4 ans)"),
            (60, "60 mois (5 ans)"),
            (84, "84 mois (7 ans)"),
            (120, "120 mois (10 ans)"),
        ],
        initial=36,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    interest_rate = forms.DecimalField(
        label="Taux d'intérêt annuel (%)",
        max_digits=5,
        decimal_places=2,
        initial=8.50,
        min_value=0,
        max_value=30,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "step": "0.5",
        }),
    )

    def clean(self):
        cleaned = super().clean()
        price = cleaned.get("property_price")
        down = cleaned.get("down_payment")
        if price and down and down >= price:
            raise forms.ValidationError(
                "L'apport initial doit être inférieur au prix du bien."
            )
        return cleaned
