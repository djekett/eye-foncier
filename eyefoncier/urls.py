"""EYE-FONCIER URL Configuration."""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("websig.urls")),
    path("compte/", include("accounts.urls")),
    path("parcelles/", include("parcelles.urls")),
    path("documents/", include("documents.urls")),
    path("transactions/", include("transactions.urls")),
    path("analyse/", include("analysis.urls")),
    path("contenu/", include("content.urls")),
    path("notifications/", include("notifications.urls")),
    # API
    path("api/v1/parcelles/", include("parcelles.api_urls")),
    path("api/v1/auth/", include("accounts.api_urls")),
    path("api/v1/transactions/", include("transactions.api_urls")),
    path("api/v1/notifications/", include("notifications.api_urls")),
    path("api/v1/analysis/", include("analysis.api_urls")),
    # Documentation API — Swagger / OpenAPI
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # Static files are served automatically by runserver when django.contrib.staticfiles is installed

# Admin customisation
admin.site.site_header = "EYE-FONCIER Administration"
admin.site.site_title = "EYE-FONCIER"
admin.site.index_title = "Tableau de bord d'administration"
