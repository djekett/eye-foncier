from django.urls import path
from . import api_views
from . import cotation_api_views

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
]
