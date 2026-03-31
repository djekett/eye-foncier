"""Middleware de journalisation des acces et tracing."""
import logging
import uuid

logger = logging.getLogger("accounts")


class RequestIdMiddleware:
    """Ajoute un identifiant unique a chaque requete pour le tracing distribue.

    Le X-Request-ID est propage dans les logs et les reponses HTTP,
    ce qui facilite le debug en production et la correlation avec Sentry.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Reutiliser le X-Request-ID entrant (load balancer) ou en generer un
        request_id = request.META.get("HTTP_X_REQUEST_ID") or str(uuid.uuid4())
        request.id = request_id

        response = self.get_response(request)
        response["X-Request-ID"] = request_id
        return response


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
