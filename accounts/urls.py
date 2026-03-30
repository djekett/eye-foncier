from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("inscription/", views.register_view, name="register"),
    path("connexion/", views.CustomLoginView.as_view(), name="login"),
    path("deconnexion/", views.CustomLogoutView.as_view(), name="logout"),
    path("profil/", views.profile_view, name="profile"),
    path("tableau-de-bord/", views.dashboard_view, name="dashboard"),
    path("vendeur/<uuid:pk>/", views.SellerProfileView.as_view(), name="seller_profile"),
    path("logs/", views.AccessLogListView.as_view(), name="access_logs"),
    # Certification
    path("certification/", views.certification_request_view, name="certification"),
    path("certification/chat/", views.certification_chat_api, name="certification_chat"),
    # Espace Partenaires
    path("partenaires/", views.partner_list_view, name="partner_list"),
    path("partenaires/<uuid:pk>/", views.partner_detail_view, name="partner_detail"),
    path("partenaires/<uuid:pk>/contact/", views.partner_referral_view, name="partner_referral"),
    # Parrainage & Affiliation
    path("parrainage/", views.referral_dashboard_view, name="referral_dashboard"),
    path("ambassadeur/", views.ambassador_dashboard_view, name="ambassador_dashboard"),
    path("ambassadeur/candidature/", views.ambassador_apply_view, name="ambassador_apply"),
    # Modération Admin
    path("admin/moderation/", views.admin_moderation_view, name="admin_moderation"),
    path("admin/kyc/<int:pk>/", views.admin_kyc_review_view, name="admin_kyc_review"),
    path("admin/certification/<uuid:pk>/", views.admin_certification_review_view, name="admin_certification_review"),
]
