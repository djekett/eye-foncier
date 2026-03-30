from django.urls import path
from . import views
from . import cotation_views

app_name = "transactions"

urlpatterns = [
    path("", views.TransactionListView.as_view(), name="list"),
    path("reserver/<uuid:parcelle_pk>/", views.reserve_parcelle_view, name="reserve"),

    # ── Cotation (10 % obligatoire avant réservation) ──
    path("cotation/<uuid:parcelle_pk>/", cotation_views.cotation_create_view, name="cotation_create"),
    path("cotation/detail/<uuid:pk>/", cotation_views.cotation_detail_view, name="cotation_detail"),
    path("cotation/retour/", cotation_views.cotation_callback_view, name="cotation_callback"),
    path("cotation/webhook/", cotation_views.cotation_webhook_view, name="cotation_webhook"),

    # ── Boutique (vendeurs / promoteurs) ──
    path("boutique/cotation/", cotation_views.boutique_cotation_view, name="boutique_cotation"),
    path("boutique/", cotation_views.boutique_dashboard_view, name="boutique_dashboard"),
    path("boutique/personnaliser/", cotation_views.boutique_edit_view, name="boutique_edit"),
    path("boutiques/", cotation_views.boutiques_list_view, name="boutiques_list"),
    path("boutique/<slug:slug>/", cotation_views.boutique_public_view, name="boutique_public"),
    path("boutique/<slug:slug>/avis/", cotation_views.boutique_review_view, name="boutique_review"),

    # ── Vérification Eye-Foncier ──
    path("verifications/", cotation_views.verification_list_view, name="verification_list"),
    path("verifications/<uuid:pk>/", cotation_views.verification_detail_view, name="verification_detail"),
    path("verifications/<uuid:pk>/avancer/", cotation_views.verification_advance_view, name="verification_advance"),
    path("verifications/<uuid:pk>/assigner/", cotation_views.verification_assign_view, name="verification_assign"),
    path("<uuid:pk>/", views.TransactionDetailView.as_view(), name="detail"),
    path("<uuid:pk>/modifier/", views.transaction_update_view, name="update"),
    # Séquestre (Escrow)
    path("<uuid:pk>/sequestre/", views.escrow_fund_view, name="escrow_fund"),
    path("<uuid:pk>/confirmer-docs/", views.escrow_confirm_docs_view, name="escrow_confirm_docs"),
    path("<uuid:pk>/liberer/", views.escrow_release_view, name="escrow_release"),
    # Compromis
    path("<uuid:pk>/compromis/", views.initiate_compromis_view, name="compromis"),
    path("<uuid:pk>/compromis/pdf/", views.compromis_pdf_view, name="compromis_pdf"),
    # Bon de visite
    path("visite/<uuid:parcelle_pk>/", views.request_visit_view, name="request_visit"),
    path("visite/detail/<uuid:pk>/", views.visit_detail_view, name="visit_detail"),
    # Paiement en ligne
    path("paiement/initier/", views.payment_initiate_view, name="payment_initiate"),
    path("paiement/retour/", views.payment_return_view, name="payment_return"),
    path("paiement/simulation/<str:tx_id>/", views.payment_simulation_view, name="payment_simulation"),
    path("paiement/webhook/", views.payment_webhook_view, name="payment_webhook"),
    # Statistiques (admin)
    path("statistiques/", views.transaction_stats_view, name="stats"),
    # Annulation & Litige
    path("<uuid:pk>/annuler/", views.cancel_transaction_view, name="cancel"),
    path("<uuid:pk>/litige/", views.dispute_transaction_view, name="dispute"),
    # Approbation bipartite
    path("approbation/<uuid:approval_pk>/approuver/", views.approve_operation_view, name="approve_operation"),
    path("approbation/<uuid:approval_pk>/refuser/", views.reject_operation_view, name="reject_operation"),
    path("approbation/<uuid:approval_pk>/quick/", views.quick_approve_api, name="quick_approve"),
    # Signature électronique
    path("<uuid:pk>/signer/", views.contract_sign_view, name="contract_sign"),
    path("<uuid:pk>/verifier-contrat/", views.contract_verify_view, name="contract_verify"),
    # Scoring financier & Simulateur
    path("scoring/", views.financial_score_view, name="financial_score"),
    path("simulateur/", views.simulator_view, name="simulator"),
    path("simulation/<uuid:pk>/", views.simulation_detail_view, name="simulation_detail"),
    # Factures
    path("factures/", views.invoice_list_view, name="invoice_list"),
    path("factures/<uuid:pk>/", views.invoice_detail_view, name="invoice_detail"),
    path("factures/<uuid:pk>/pdf/", views.invoice_download_pdf_view, name="invoice_pdf"),
]
