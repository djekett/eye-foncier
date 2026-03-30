from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from . import api_views

urlpatterns = [
    path("token/", TokenObtainPairView.as_view(), name="token_obtain"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("register/", api_views.RegisterAPIView.as_view(), name="api_register"),
    path("me/", api_views.CurrentUserAPIView.as_view(), name="api_me"),

    # Partenaires
    path("partenaires/", api_views.PartnerListAPIView.as_view(), name="api_partner_list"),
    path("partenaires/<uuid:pk>/", api_views.PartnerDetailAPIView.as_view(), name="api_partner_detail"),
    path("partenaires/referral/", api_views.PartnerReferralCreateAPIView.as_view(), name="api_partner_referral"),
    path("partenaires/mes-demandes/", api_views.MyPartnerReferralsAPIView.as_view(), name="api_my_referrals"),

    # Ambassadeurs
    path("ambassadeur/", api_views.AmbassadorProfileAPIView.as_view(), name="api_ambassador_profile"),
    path("ambassadeur/candidature/", api_views.AmbassadorApplyAPIView.as_view(), name="api_ambassador_apply"),
    path("parrainages/", api_views.ReferralStatsAPIView.as_view(), name="api_referral_stats"),

    # Dashboard KPIs
    path("dashboard-stats/", api_views.DashboardStatsAPIView.as_view(), name="api_dashboard_stats"),
]
