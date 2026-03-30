"""Formulaires du module Analyse — EYE-FONCIER."""
from django import forms
from django.contrib.gis.geos import Point

from .models import BuyerProfile, GISReferenceLayer
from parcelles.models import Zone


class BuyerProfileForm(forms.ModelForm):
    """Formulaire de profil acheteur pour le Smart Matching."""

    # Point de référence simplifié (lat/lng)
    ref_latitude = forms.FloatField(
        required=False,
        widget=forms.NumberInput(attrs={
            "class": "form-control", "placeholder": "Latitude (ex: 5.3600)",
            "step": "0.0001",
        }),
        label="Latitude (point de référence)",
    )
    ref_longitude = forms.FloatField(
        required=False,
        widget=forms.NumberInput(attrs={
            "class": "form-control", "placeholder": "Longitude (ex: -4.0083)",
            "step": "0.0001",
        }),
        label="Longitude (point de référence)",
    )

    class Meta:
        model = BuyerProfile
        fields = [
            "budget_min", "budget_max",
            "surface_min", "surface_max",
            "preferred_land_types", "preferred_zones",
            "lifestyle", "risk_tolerance", "project_type",
            "max_travel_minutes",
            "weight_price", "weight_location", "weight_technical", "weight_seller",
            "notify_on_match", "match_threshold",
        ]
        widgets = {
            "budget_min": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Ex: 5 000 000"}),
            "budget_max": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Ex: 25 000 000"}),
            "surface_min": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Ex: 300", "step": "1"}),
            "surface_max": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Ex: 1000", "step": "1"}),
            "preferred_zones": forms.CheckboxSelectMultiple(),
            "lifestyle": forms.Select(attrs={"class": "form-select"}),
            "risk_tolerance": forms.Select(attrs={"class": "form-select"}),
            "project_type": forms.Select(attrs={"class": "form-select"}),
            "max_travel_minutes": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Ex: 30"}),
            "weight_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.05", "min": "0", "max": "1"}),
            "weight_location": forms.NumberInput(attrs={"class": "form-control", "step": "0.05", "min": "0", "max": "1"}),
            "weight_technical": forms.NumberInput(attrs={"class": "form-control", "step": "0.05", "min": "0", "max": "1"}),
            "weight_seller": forms.NumberInput(attrs={"class": "form-control", "step": "0.05", "min": "0", "max": "1"}),
            "match_threshold": forms.NumberInput(attrs={"class": "form-control", "min": "50", "max": "100"}),
            "notify_on_match": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pré-remplir lat/lng depuis le point existant
        if self.instance and self.instance.pk and self.instance.reference_point:
            self.fields["ref_latitude"].initial = self.instance.reference_point.y
            self.fields["ref_longitude"].initial = self.instance.reference_point.x

        # Types de terrain comme checkboxes
        from parcelles.models import Parcelle
        self.fields["preferred_land_types"].widget = forms.CheckboxSelectMultiple(
            choices=Parcelle.LandType.choices,
        )

    def clean(self):
        cleaned = super().clean()

        # Valider la somme des poids ≈ 1.0
        weights = [
            cleaned.get("weight_price", 0) or 0,
            cleaned.get("weight_location", 0) or 0,
            cleaned.get("weight_technical", 0) or 0,
            cleaned.get("weight_seller", 0) or 0,
        ]
        total = sum(weights)
        if total > 0 and abs(total - 1.0) > 0.05:
            self.add_error(None, "La somme des poids doit être égale à 1.0 (actuellement : {:.2f})".format(total))

        # Budget cohérent
        bmin = cleaned.get("budget_min")
        bmax = cleaned.get("budget_max")
        if bmin and bmax and bmin > bmax:
            self.add_error("budget_max", "Le budget max doit être supérieur au budget min.")

        # Surface cohérente
        smin = cleaned.get("surface_min")
        smax = cleaned.get("surface_max")
        if smin and smax and smin > smax:
            self.add_error("surface_max", "La surface max doit être supérieure à la surface min.")

        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)

        # Construire le point de référence
        lat = self.cleaned_data.get("ref_latitude")
        lng = self.cleaned_data.get("ref_longitude")
        if lat and lng:
            instance.reference_point = Point(lng, lat, srid=4326)
        elif not lat and not lng:
            instance.reference_point = None

        if commit:
            instance.save()
            self.save_m2m()
        return instance


class GISLayerUploadForm(forms.Form):
    """Upload d'une couche SIG (Shapefile ZIP ou GeoJSON)."""
    name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Nom de la couche"}),
    )
    layer_type = forms.ChoiceField(
        choices=GISReferenceLayer.LayerType.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )
    file = forms.FileField(
        widget=forms.ClearableFileInput(attrs={
            "class": "form-control", "accept": ".zip,.geojson,.json,.shp",
        }),
        help_text="Shapefile (.zip) ou GeoJSON (.geojson)",
    )
    buffer_distance_m = forms.FloatField(
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "Distance buffer en mètres"}),
        help_text="Zone tampon autour des géométries (optionnel).",
    )
