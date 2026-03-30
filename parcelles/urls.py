from django.urls import path
from . import views

app_name = "parcelles"

urlpatterns = [
    # Parcelles CRUD
    path("", views.ParcelleListView.as_view(), name="list"),
    path("deposer/", views.parcelle_create_view, name="create"),
    path("<uuid:pk>/", views.ParcelleDetailView.as_view(), name="detail"),
    path("<uuid:pk>/modifier/", views.parcelle_edit_view, name="edit"),
    path("<uuid:pk>/supprimer/", views.ParcelleDeleteView.as_view(), name="delete"),
    path("<uuid:pk>/medias/", views.media_upload_view, name="media_upload"),
    path("<uuid:pk>/medias/<uuid:media_pk>/supprimer/", views.media_delete_view, name="media_delete"),
    path("<uuid:pk>/valider/", views.validate_parcelle_view, name="validate"),

    # Réactions
    path("<uuid:pk>/reaction/", views.toggle_reaction_view, name="toggle_reaction"),
    path("api/<uuid:pk>/reactions/", views.parcelle_reactions_api, name="reactions_api"),

    # Parcelles à proximité
    path("api/nearby/", views.nearby_parcelles_api, name="nearby_api"),

    # Promotions
    path("<uuid:pk>/promouvoir/", views.promotion_create_view, name="promote"),
    path("<uuid:pk>/promotion/<uuid:promo_pk>/", views.promotion_detail_view, name="promotion_detail"),
    path("mes-promotions/", views.my_promotions_view, name="my_promotions"),
    path("api/promoted/", views.promoted_parcelles_api, name="promoted_api"),
    path("api/recommendations/", views.recommended_parcelles_api, name="recommendations_api"),

    # Mode Pro promoteur
    path("import-lot/", views.bulk_parcelle_upload_view, name="bulk_upload"),
    path("dashboard-pro/", views.seller_dashboard_pro_view, name="seller_dashboard_pro"),

    # Analyse foncière
    path("<uuid:pk>/analyse/", views.parcelle_analysis_view, name="analysis"),
    path("<uuid:pk>/analyse/lancer/", views.run_analysis_view, name="run_analysis"),
    path("<uuid:pk>/analyse/terrain/", views.terrain_inspection_view, name="terrain_inspection"),
    path("<uuid:pk>/soumettre-validation/", views.submit_for_validation_view, name="submit_validation"),

    # Géomètre
    path("geometre/dashboard/", views.geometre_dashboard_view, name="geometre_dashboard"),

    # Lotissements (promoteurs)
    path("lotissements/", views.lotissement_list_view, name="lotissement_list"),
    path("lotissements/creer/", views.lotissement_create_view, name="lotissement_create"),
    path("lotissements/<uuid:pk>/", views.lotissement_detail_view, name="lotissement_detail"),
    path("lotissements/<uuid:pk>/ajouter-parcelle/", views.lotissement_add_parcelle_view, name="lotissement_add_parcelle"),
]
