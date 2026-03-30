from django.urls import path
from . import views

app_name = "documents"

urlpatterns = [
    path("parcelle/<uuid:parcelle_pk>/", views.document_list_view, name="list"),
    path("parcelle/<uuid:parcelle_pk>/upload/", views.document_upload_view, name="upload"),
    path("parcelle/<uuid:parcelle_pk>/fiche-pdf/", views.parcelle_fiche_pdf, name="fiche_pdf"),
    path("<uuid:pk>/consulter/", views.document_view_watermarked, name="view_watermarked"),
    path("coffre-fort/", views.digital_vault_view, name="digital_vault"),
]
