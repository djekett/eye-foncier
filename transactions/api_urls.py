from django.urls import path
from . import api_views
from . import cotation_api_views
from . import dispute_api_views

urlpatterns = [
    path("", api_views.TransactionListAPIView.as_view(), name="api_transactions"),
    path("<uuid:pk>/", api_views.TransactionDetailAPIView.as_view(), name="api_transaction_detail"),
    # Scoring & Simulateur
    path("scoring/", api_views.FinancialScoreAPIView.as_view(), name="api_financial_score"),
    path("simulateur/", api_views.SimulatorAPIView.as_view(), name="api_simulator"),
    path("eligibilite/<uuid:parcelle_pk>/", api_views.EligibilityCheckAPIView.as_view(), name="api_eligibility"),

    # ── Cotation API ──
    path("cotation/", cotation_api_views.api_cotation_create, name="api_cotation_create"),
    path("cotation/mes/", cotation_api_views.api_my_cotations, name="api_my_cotations"),
    path("cotation/<uuid:pk>/", cotation_api_views.api_cotation_detail, name="api_cotation_detail"),
    path("cotation/check/<uuid:parcelle_pk>/", cotation_api_views.api_cotation_check, name="api_cotation_check"),

    # ── Boutique API ──
    path("boutique/cotation/", cotation_api_views.api_boutique_cotation_create, name="api_boutique_cotation"),
    path("boutique/", cotation_api_views.api_my_boutique, name="api_my_boutique"),

    # ── Vérification API ──
    path("verifications/", cotation_api_views.api_verification_list, name="api_verification_list"),
    path("verifications/<uuid:pk>/", cotation_api_views.api_verification_detail, name="api_verification_detail"),
    path("verifications/<uuid:pk>/avancer/", cotation_api_views.api_verification_advance, name="api_verification_advance"),

    # ── Litiges API ──
    path("litiges/", dispute_api_views.DisputeListAPIView.as_view(), name="api_disputes"),
    path("litiges/stats/", dispute_api_views.api_dispute_stats, name="api_dispute_stats"),
    path("litiges/ouvrir/", dispute_api_views.api_open_dispute, name="api_open_dispute"),
    path("litiges/<uuid:pk>/", dispute_api_views.DisputeDetailAPIView.as_view(), name="api_dispute_detail"),
    path("litiges/<uuid:pk>/resoudre/", dispute_api_views.api_resolve_dispute, name="api_resolve_dispute"),
    path("litiges/<uuid:pk>/messages/", dispute_api_views.api_add_dispute_message, name="api_dispute_message"),
    path("litiges/<uuid:pk>/preuves/", dispute_api_views.api_add_dispute_evidence, name="api_dispute_evidence"),
]
