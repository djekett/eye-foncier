"""API URL patterns Analysis — EYE-FONCIER (Smart Matching)."""
from django.urls import path
from . import api_views

app_name = "analysis_api"

urlpatterns = [
    path("matching/", api_views.MatchingResultsAPIView.as_view(), name="matching"),
    path("matching/trigger/", api_views.TriggerMatchingAPIView.as_view(), name="matching_trigger"),
    path("buyer-profile/", api_views.BuyerProfileAPIView.as_view(), name="buyer_profile"),
    path("parcelle/<uuid:pk>/matches/", api_views.ParcelleMatchesAPIView.as_view(), name="parcelle_matches"),
    # Heatmap & Scores (fusion analysis ↔ parcelles)
    path("heatmap/", api_views.HeatmapDataAPIView.as_view(), name="heatmap"),
    path("parcelle/<uuid:pk>/scores/", api_views.ParcelleScoresAPIView.as_view(), name="parcelle_scores"),
]
