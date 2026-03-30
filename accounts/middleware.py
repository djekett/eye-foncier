"""Middleware de journalisation des accès."""
import logging

logger = logging.getLogger("accounts")


class AccessLogMiddleware:
    """Log les requêtes sensibles (documents, parcelles)."""

    TRACKED_PATHS = ["/documents/", "/parcelles/", "/api/"]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        path = request.path

        if any(path.startswith(p) for p in self.TRACKED_PATHS):
            if request.user.is_authenticated:
                logger.info(
                    "ACCESS | user=%s | path=%s | method=%s | status=%s | ip=%s",
                    request.user.email,
                    path,
                    request.method,
                    response.status_code,
                    self._get_ip(request),
                )

        return response

    @staticmethod
    def _get_ip(request):
        x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        return x_forwarded.split(",")[0].strip() if x_forwarded else request.META.get("REMOTE_ADDR")
