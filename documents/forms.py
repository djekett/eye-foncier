from django import forms
from .models import ParcelleDocument


class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = ParcelleDocument
        fields = ["doc_type", "title", "description", "file", "confidentiality"]
        widgets = {
            "doc_type": forms.Select(attrs={"class": "form-select"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "file": forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".pdf,.jpg,.jpeg,.png"}),
            "confidentiality": forms.Select(attrs={"class": "form-select"}),
        }
