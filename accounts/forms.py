"""Formulaires de gestion des comptes."""
from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import User, Profile


class CustomUserCreationForm(UserCreationForm):
    """Formulaire d'inscription enrichi."""

    role = forms.ChoiceField(
        choices=[
            (User.Role.ACHETEUR, "Acheteur"),
            (User.Role.VENDEUR, "Vendeur / Propriétaire"),
        ],
        label="Je suis",
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = User
        fields = [
            "first_name", "last_name", "email", "username",
            "phone", "role", "password1", "password2",
        ]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Prénom"}),
            "last_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Nom"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "email@exemple.com"}),
            "username": forms.TextInput(attrs={"class": "form-control", "placeholder": "Pseudo"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "+225 XX XX XX XX"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].widget.attrs.update({"class": "form-control"})
        self.fields["password2"].widget.attrs.update({"class": "form-control"})


class CustomLoginForm(AuthenticationForm):
    """Formulaire de connexion stylé."""

    username = forms.EmailField(
        label="Adresse email",
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "email@exemple.com"}),
    )
    password = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Mot de passe"}),
    )


class ProfileUpdateForm(forms.ModelForm):
    """Modification du profil."""

    class Meta:
        model = Profile
        fields = ["avatar", "bio", "address", "city", "country", "id_document"]
        widgets = {
            "avatar": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/*"}),
            "bio": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "address": forms.TextInput(attrs={"class": "form-control"}),
            "city": forms.TextInput(attrs={"class": "form-control"}),
            "country": forms.TextInput(attrs={"class": "form-control"}),
        }


class UserUpdateForm(forms.ModelForm):
    """Modification des infos utilisateur."""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
        }
