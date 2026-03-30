"""URLs — Module Analyse SIG, Matching & Rapports."""
from django.urls import path
from . import views

app_name = "analysis"

urlpatterns = [
    # Dashboard
    path("", views.analysis_dashboard, name="dashboard"),

    # Analyse parcelle (Module 2)
    path("parcelle/<uuid:pk>/", views.parcelle_analysis_view, name="parcelle_analysis"),
    path("parcelle/<uuid:pk>/run/", views.run_analysis_view, name="run_analysis"),

    # Profil acheteur & Matching (Module 1)
    path("profil-acheteur/", views.buyer_profile_view, name="buyer_profile"),
    path("matching/", views.matching_results_view, name="matching_results"),
    path("matching/recalculate/", views.recalculate_matching_view, name="recalculate_matching"),

    # Notifications
    path("notifications/", views.notifications_view, name="notifications"),
    path("api/notifications/count/", views.notifications_count_api, name="notifications_count"),

    # Rapports (Module 3)
    path("rapport/generer/<uuid:pk>/", views.generate_report_view, name="generate_report"),
    path("rapport/<uuid:pk>/", views.report_detail_view, name="report_detail"),
    path("rapport/<uuid:pk>/download/", views.report_download_view, name="report_download"),

    # API publiques
    path("api/heatmap/", views.heatmap_data_api, name="heatmap_data"),
    path("api/parcelle/<uuid:pk>/scores/", views.parcelle_scores_api, name="parcelle_scores"),
]
