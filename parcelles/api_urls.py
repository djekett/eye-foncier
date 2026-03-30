from django.urls import path
from . import api_views

urlpatterns = [
    # Endpoint optimisé (sérialisation manuelle, cache, simplification géométrique)
    path("geojson/", api_views.parcelle_geojson_list, name="api_parcelles_geojson"),
    # Fallback DRF (pour les clients tiers / Browsable API)
    path("geojson/drf/", api_views.ParcelleGeoListView.as_view(), name="api_parcelles_geojson_drf"),
    path("geojson/<uuid:pk>/", api_views.ParcelleGeoDetailView.as_view(), name="api_parcelle_detail"),
    path("nearby/", api_views.nearby_parcelles, name="api_nearby"),
    path("zones/", api_views.ZoneListView.as_view(), name="api_zones"),
    path("ilots/", api_views.IlotListView.as_view(), name="api_ilots"),
    path("shapefile-preview/", api_views.shapefile_preview, name="api_shapefile_preview"),
]
