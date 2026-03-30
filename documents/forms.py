import os

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import ParcelleDocument

# Extensions et MIME types autorises pour les documents
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
}
MAX_FILE_SIZE_MB = 10  # Taille max en Mo


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

    def clean_file(self):
        """Validation serveur : extension, MIME type et taille du fichier."""
        uploaded = self.cleaned_data.get("file")
        if not uploaded:
            return uploaded

        # 1. Verifier l'extension
        ext = os.path.splitext(uploaded.name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValidationError(
                _("Type de fichier non autorise (%(ext)s). "
                  "Formats acceptes : PDF, JPG, JPEG, PNG."),
                params={"ext": ext},
            )

        # 2. Verifier le MIME type (content_type envoye par le navigateur)
        content_type = getattr(uploaded, "content_type", "")
        if content_type and content_type not in ALLOWED_MIME_TYPES:
            raise ValidationError(
                _("Type MIME non autorise (%(mime)s). "
                  "Formats acceptes : PDF, JPG, PNG."),
                params={"mime": content_type},
            )

        # 3. Verifier la taille
        max_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
        if uploaded.size > max_bytes:
            raise ValidationError(
                _("Le fichier est trop volumineux (%(size).1f Mo). "
                  "Taille maximale : %(max)d Mo."),
                params={
                    "size": uploaded.size / (1024 * 1024),
                    "max": MAX_FILE_SIZE_MB,
                },
            )

        # 4. Verifier les magic bytes (signature du fichier)
        header = uploaded.read(8)
        uploaded.seek(0)  # Remettre le curseur au debut

        is_valid_header = False
        if header[:4] == b"%PDF":
            is_valid_header = True
        elif header[:3] == b"\xff\xd8\xff":  # JPEG
            is_valid_header = True
        elif header[:8] == b"\x89PNG\r\n\x1a\n":  # PNG
            is_valid_header = True

        if not is_valid_header:
            raise ValidationError(
                _("Le contenu du fichier ne correspond pas a son extension. "
                  "Le fichier pourrait etre corrompu ou non valide.")
            )

        return uploaded
