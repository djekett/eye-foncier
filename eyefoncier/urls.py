"""EYE-FONCIER URL Configuration."""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.db import connection


def health_check(request):
    """Endpoint de sante pour Kubernetes/Docker/load balancer."""
    checks = {"status": "ok"}
    status_code = 200
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = str(e)
        checks["status"] = "degraded"
        status_code = 503
    try:
        from django.core.cache import cache
        cache.set("_health_check", "1", 5)
        if cache.get("_health_check") == "1":
            checks["cache"] = "ok"
        else:
            checks["cache"] = "unreachable"
            checks["status"] = "degraded"
    except Exception:
        checks["cache"] = "unavailable"
    return JsonResponse(checks, status=status_code)


urlpatterns = [
    path("health/", health_check, name="health_check"),
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
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # Static files are served automatically by runserver when django.contrib.staticfiles is installed

# Admin customisation
admin.site.site_header = "EYE-FONCIER Administration"
admin.site.site_title = "EYE-FONCIER"
admin.site.index_title = "Tableau de bord d'administration"
