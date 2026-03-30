"""
EYE-FONCIER — Configuration Swagger / OpenAPI
Documentation interactive de l'API REST.
"""
from drf_spectacular.extensions import OpenApiAuthenticationExtension


class JWTAuthenticationScheme(OpenApiAuthenticationExtension):
    """Extension pour documenter l'authentification JWT dans Swagger."""

    target_class = "rest_framework_simplejwt.authentication.JWTAuthentication"
    name = "JWT"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "Authentification par token JWT.\n\n"
                "Obtenez un token via `POST /api/v1/auth/token/`\n"
                "puis ajoutez le header : `Authorization: Bearer <token>`"
            ),
        }


# Configuration drf-spectacular
SPECTACULAR_SETTINGS = {
    "TITLE": "EYE-FONCIER API",
    "DESCRIPTION": (
        "## API REST de la plateforme EYE-FONCIER\n\n"
        "Plateforme WebSIG de transaction fonciere securisee en Afrique de l'Ouest.\n\n"
        "### Fonctionnalites principales\n"
        "- **Parcelles** : Recherche, filtrage geospatial, publication\n"
        "- **Transactions** : Reservation, sequestre, compromis de vente\n"
        "- **Cotations** : Paiement 10% pour debloquer une parcelle\n"
        "- **Boutiques** : Abonnement vendeur pour publier des parcelles\n"
        "- **Notifications** : Multicanal (email, SMS, WhatsApp, push, in-app)\n"
        "- **Analyse** : Scoring financier, matching acheteur-parcelle\n"
        "- **Documents** : Upload securise avec filigrane automatique\n\n"
        "### Authentification\n"
        "L'API utilise **JWT (JSON Web Tokens)** :\n"
        "1. `POST /api/v1/auth/token/` avec email + password\n"
        "2. Utilisez le `access` token dans le header `Authorization: Bearer <token>`\n"
        "3. Rafraichissez via `POST /api/v1/auth/token/refresh/`\n\n"
        "### Pagination\n"
        "Toutes les listes sont paginées (20 elements par page par defaut).\n"
        "Parametres : `?page=2&page_size=50`\n\n"
        "### Throttling\n"
        "- Anonyme : 60 requetes/minute\n"
        "- Authentifie : 200 requetes/minute\n"
    ),
    "VERSION": "1.0.0",
    "CONTACT": {
        "name": "EYE-FONCIER Support",
        "email": "support@eye-foncier.com",
        "url": "https://eye-foncier.com",
    },
    "LICENSE": {
        "name": "Proprietary",
    },
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/v1/",
    "COMPONENT_SPLIT_REQUEST": True,
    "TAGS": [
        {"name": "Auth", "description": "Authentification et gestion des comptes"},
        {"name": "Parcelles", "description": "Gestion des parcelles foncieres"},
        {"name": "Transactions", "description": "Transactions et paiements"},
        {"name": "Cotations", "description": "Systeme de cotation (10% achat / boutique)"},
        {"name": "Notifications", "description": "Notifications multicanal"},
        {"name": "Analysis", "description": "Analyse geospatiale et scoring"},
        {"name": "Documents", "description": "Documents et pieces justificatives"},
        {"name": "Litiges", "description": "Gestion des litiges et resolutions"},
    ],
    "ENUM_NAME_OVERRIDES": {
        "TransactionStatusEnum": "transactions.models.Transaction.Status",
        "ParcelleStatusEnum": "parcelles.models.Parcelle.Status",
    },
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayOperationId": False,
        "filter": True,
        "docExpansion": "list",
        "defaultModelsExpandDepth": 2,
        "tryItOutEnabled": True,
    },
    "REDOC_UI_SETTINGS": {
        "hideDownloadButton": False,
        "expandResponses": "200,201",
    },
}
