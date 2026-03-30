"""
EYE-FONCIER — Plateforme WebSIG de Transaction Fonciere Securisee
Settings
"""
import logging
import os
import sys
from pathlib import Path
from datetime import timedelta

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Charger les variables d'environnement depuis .env
load_dotenv(BASE_DIR / ".env")

# ─── GDAL / GEOS — détection automatique ─────────────────────────────
if sys.platform == "win32":
    OSGEO4W = os.environ.get("OSGEO4W_ROOT", r"C:\OSGeo4W")
    os.environ.setdefault("PATH", "")
    os.environ["PATH"] = OSGEO4W + r"\bin;" + os.environ["PATH"]
    os.environ["GDAL_DATA"] = OSGEO4W + r"\share\gdal"
    os.environ["PROJ_LIB"] = OSGEO4W + r"\share\proj"
    GDAL_LIBRARY_PATH = os.environ.get(
        "GDAL_LIBRARY_PATH", OSGEO4W + r"\bin\gdal312.dll"
    )
    GEOS_LIBRARY_PATH = os.environ.get(
        "GEOS_LIBRARY_PATH", OSGEO4W + r"\bin\geos_c.dll"
    )

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if os.environ.get("DJANGO_DEBUG", "False").lower() in ("true", "1", "yes"):
        SECRET_KEY = "django-insecure-dev-only-key-do-not-use-in-production"
    else:
        raise ValueError(
            "DJANGO_SECRET_KEY est obligatoire en production. "
            "Definissez-le dans le fichier .env ou les variables d'environnement."
        )

DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() in ("true", "1", "yes")

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# ──────────────────────────────────────────────
# Applications
# ──────────────────────────────────────────────
INSTALLED_APPS = [
    "jazzmin",  # ← Doit être AVANT django.contrib.admin
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "django.contrib.humanize",
    "rest_framework",
    "rest_framework_gis",
    "rest_framework_simplejwt",
    "corsheaders",
    "django_filters",
    "crispy_forms",
    "crispy_bootstrap5",
    "accounts.apps.AccountsConfig",
    "parcelles.apps.ParcellesConfig",
    "documents.apps.DocumentsConfig",
    "transactions.apps.TransactionsConfig",
    "websig.apps.WebsigConfig",
    "analysis.apps.AnalysisConfig",
    "content.apps.ContentConfig",
    "notifications.apps.NotificationsConfig",
    # Documentation API
    "drf_spectacular",
]

# ──────────────────────────────────────────────
# Jazzmin — Interface Admin moderne
# ──────────────────────────────────────────────
JAZZMIN_SETTINGS = {
    "site_title": "EYE-FONCIER Admin",
    "site_header": "EYE-FONCIER",
    "site_brand": "EYE-FONCIER",
    "site_logo": "img/logo.png",
    "login_logo": "img/logo.png",
    "welcome_sign": "Bienvenue sur l'administration EYE-FONCIER",
    "copyright": "EYE-FONCIER — Plateforme WebSIG Foncière Sécurisée",
    "search_model": ["accounts.User", "parcelles.Parcelle"],
    "topmenu_links": [
        {"name": "Accueil Site", "url": "/", "new_window": True},
        {"name": "Carte", "url": "/carte/", "new_window": True},
        {"model": "accounts.User"},
    ],
    "show_sidebar": True,
    "navigation_expanded": True,
    "order_with_respect_to": [
        "accounts",
        "parcelles",
        "analysis",
        "documents",
        "transactions",
    ],
    "icons": {
        "accounts.User": "fas fa-users",
        "accounts.Profile": "fas fa-id-card",
        "accounts.AccessLog": "fas fa-clipboard-list",
        "accounts.CertificationRequest": "fas fa-certificate",
        "parcelles.Zone": "fas fa-map",
        "parcelles.Ilot": "fas fa-vector-square",
        "parcelles.Parcelle": "fas fa-map-marked-alt",
        "parcelles.ParcelleMedia": "fas fa-images",
        "parcelles.ParcelleReaction": "fas fa-heart",
        "parcelles.PromotionCampaign": "fas fa-bullhorn",
        "content.Article": "fas fa-newspaper",
        "content.Announcement": "fas fa-bullhorn",
        "content.Documentation": "fas fa-book",
        "content.Category": "fas fa-folder",
        "documents.ParcelleDocument": "fas fa-file-shield",
        "documents.DocumentAccessLog": "fas fa-eye",
        "transactions.Transaction": "fas fa-handshake",
        "transactions.BonDeVisite": "fas fa-ticket",
        "transactions.FinancialScore": "fas fa-chart-line",
        "transactions.SimulationResult": "fas fa-calculator",
        "transactions.TransactionEvent": "fas fa-history",
        "analysis.TerrainAnalysis": "fas fa-mountain",
        "analysis.SpatialConstraint": "fas fa-exclamation-triangle",
        "analysis.ProximityAnalysis": "fas fa-route",
        "analysis.RiskAssessment": "fas fa-shield-alt",
        "analysis.BuyerProfile": "fas fa-user-tag",
        "analysis.MatchScore": "fas fa-percentage",
        "analysis.MatchNotification": "fas fa-bell",
        "analysis.AnalysisReport": "fas fa-file-pdf",
        "analysis.GISReferenceLayer": "fas fa-layer-group",
        "auth.Group": "fas fa-users-cog",
        "notifications.Notification": "fas fa-bell",
        "notifications.NotificationPreference": "fas fa-sliders-h",
        "transactions.Dispute": "fas fa-gavel",
        "transactions.DisputeEvidence": "fas fa-folder-open",
        "transactions.DisputeMessage": "fas fa-comments",
        "transactions.Invoice": "fas fa-file-invoice",
        "transactions.ContractSignature": "fas fa-signature",
    },
    "custom_links": {
        "parcelles": [{
            "name": "Carte Interactive",
            "url": "/carte/",
            "icon": "fas fa-globe-africa",
            "permissions": ["parcelles.view_parcelle"],
        }],
        "analysis": [{
            "name": "Dashboard Analyse",
            "url": "/analyse/",
            "icon": "fas fa-chart-radar",
            "permissions": ["analysis.view_terrainanalysis"],
        }],
    },
    "hide_apps": ["auth"],
    "hide_models": [],
    "default_icon_parents": "fas fa-folder",
    "default_icon_children": "fas fa-circle",
    "related_modal_active": True,
    "use_google_fonts_cdn": True,
    "show_ui_builder": False,
    "custom_css": "css/admin_custom.css",
    "changeform_format": "collapsible",
    "changeform_format_overrides": {
        "accounts.User": "collapsible",
        "parcelles.Parcelle": "collapsible",
        "parcelles.Zone": "collapsible",
        "parcelles.Ilot": "collapsible",
        "analysis.BuyerProfile": "collapsible",
        "analysis.GISReferenceLayer": "collapsible",
    },
}

JAZZMIN_UI_TWEAKS = {
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": False,
    "brand_small_text": False,
    "brand_colour": False,
    "accent": "accent-success",
    "navbar": "navbar-dark",
    "no_navbar_border": False,
    "navbar_fixed": True,
    "layout_boxed": False,
    "footer_fixed": False,
    "sidebar_fixed": True,
    "sidebar": "sidebar-dark-success",
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": False,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,
    "theme": "default",
    "dark_mode_theme": None,
    "button_classes": {
        "primary": "btn-outline-primary",
        "secondary": "btn-outline-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success",
    },
}

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "accounts.middleware.AccessLogMiddleware",
]

ROOT_URLCONF = "eyefoncier.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "eyefoncier.context_processors.site_context",
            ],
        },
    },
]

WSGI_APPLICATION = "eyefoncier.wsgi.application"

# ──────────────────────────────────────────────
# Database — PostgreSQL + PostGIS
# ──────────────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": os.environ.get("DATABASE_NAME", "websig_foncier"),
        "USER": os.environ.get("DATABASE_USER", "postgres"),
        "PASSWORD": os.environ.get("DATABASE_PASSWORD", ""),
        "HOST": os.environ.get("DATABASE_HOST", "localhost"),
        "PORT": os.environ.get("DATABASE_PORT", "5432"),
    }
}

# ──────────────────────────────────────────────
# Cache
# ──────────────────────────────────────────────
REDIS_URL = os.environ.get("REDIS_URL", "")

if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
            },
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "unique-snowflake",
        }
    }

SESSION_ENGINE = "django.contrib.sessions.backends.db"

# ──────────────────────────────────────────────
# Auth
# ──────────────────────────────────────────────
AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "accounts.backends.EmailBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:dashboard"
LOGOUT_REDIRECT_URL = "websig:home"

# ──────────────────────────────────────────────
# Internationalisation
# ──────────────────────────────────────────────
LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Africa/Abidjan"
USE_I18N = True
USE_TZ = True
USE_L10N = False

# ──────────────────────────────────────────────
# Messages — tags Bootstrap
# ──────────────────────────────────────────────
from django.contrib.messages import constants as message_constants

MESSAGE_TAGS = {
    message_constants.DEBUG: "secondary",
    message_constants.INFO: "info",
    message_constants.SUCCESS: "success",
    message_constants.WARNING: "warning",
    message_constants.ERROR: "danger",
}

# ──────────────────────────────────────────────
# Static & Media files
# ──────────────────────────────────────────────
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# URL publique pour accéder aux fichiers
MEDIA_URL = '/media/'

# Chemin physique sur votre ordinateur/serveur
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# ──────────────────────────────────────────────
# S3 Storage (optionnel)
# ──────────────────────────────────────────────
USE_S3 = os.environ.get("USE_S3", "False").lower() in ("true", "1")

if USE_S3:
    AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = os.environ.get("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_ENDPOINT_URL = os.environ.get("AWS_S3_ENDPOINT_URL")
    AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME", "us-east-1")
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None
    AWS_S3_SIGNATURE_VERSION = "s3v4"
    AWS_QUERYSTRING_EXPIRE = 300
    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"

# ──────────────────────────────────────────────
# Django REST Framework
# ──────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/minute",
        "user": "200/minute",
    },
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# drf-spectacular (Swagger / OpenAPI)
from eyefoncier.swagger import SPECTACULAR_SETTINGS  # noqa: E402

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=2),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
}

# ──────────────────────────────────────────────
# Crispy Forms
# ──────────────────────────────────────────────
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# ──────────────────────────────────────────────
# CORS
# ──────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000"
).split(",")

# ──────────────────────────────────────────────
# Security (production)
# ──────────────────────────────────────────────
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    X_FRAME_OPTIONS = "DENY"
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True

# ──────────────────────────────────────────────
# File Upload limits
# ──────────────────────────────────────────────
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024   # 50 MB

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ──────────────────────────────────────────────
# Watermark / Document settings
# ──────────────────────────────────────────────
WATERMARK_FONT_SIZE = 24
WATERMARK_OPACITY = 0.3
WATERMARK_TEXT_TEMPLATE = "Document consulté par {user} le {date} - Usage interne uniquement"

# Image Watermark (filigrane automatique sur les photos de parcelles)
IMAGE_WATERMARK_LOGO_OPACITY = 200     # 0-255 (200 ≈ 78% — logo bien visible)
IMAGE_WATERMARK_LOGO_RATIO = 0.15      # Ratio largeur logo / largeur image

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "file": {
            "level": "WARNING",
            "class": "logging.FileHandler",
            "filename": BASE_DIR / "logs" / "eyefoncier.log",
            "formatter": "verbose",
        },
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": "INFO",
    },
    "loggers": {
        "django": {"handlers": ["console", "file"], "level": "WARNING", "propagate": False},
        "accounts": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
        "parcelles": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
    },
}

# ──────────────────────────────────────────────
# CinetPay — Passerelle de paiement
# ──────────────────────────────────────────────
CINETPAY_API_KEY = os.environ.get("CINETPAY_API_KEY", "")
CINETPAY_SITE_ID = os.environ.get("CINETPAY_SITE_ID", "")
CINETPAY_SECRET_KEY = os.environ.get("CINETPAY_SECRET_KEY", "")
CINETPAY_MODE = os.environ.get("CINETPAY_MODE", "TEST")
CINETPAY_NOTIFY_URL = os.environ.get("CINETPAY_NOTIFY_URL", "")
CINETPAY_RETURN_URL = os.environ.get("CINETPAY_RETURN_URL", "")

# ──────────────────────────────────────────────
# Notifications — SMS (InfoBip) & Email
# ──────────────────────────────────────────────
INFOBIP_API_KEY = os.environ.get("INFOBIP_API_KEY", "")
INFOBIP_BASE_URL = os.environ.get("INFOBIP_BASE_URL", "https://api.infobip.com")
INFOBIP_SENDER = os.environ.get("INFOBIP_SENDER", "EYE-FONCIER")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "noreply@eye-foncier.com")
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend" if DEBUG else "django.core.mail.backends.smtp.EmailBackend"

# Push — Firebase Cloud Messaging
FCM_SERVER_KEY = os.environ.get("FCM_SERVER_KEY", "")

# ──────────────────────────────────────────────
# WhatsApp — Twilio
# ──────────────────────────────────────────────
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "")
TWILIO_VERIFY_SERVICE_SID = os.environ.get("TWILIO_VERIFY_SERVICE_SID", "")
# Templates WhatsApp approuvés (Content SID → nom logique)
TWILIO_CONTENT_SIDS = {}
# URL publique de la plateforme (utilisée dans les liens WhatsApp)
PLATFORM_URL = os.environ.get("PLATFORM_URL", "https://eye-foncier.com")

# ──────────────────────────────────────────────
# Sentry — Monitoring & Error Tracking
# ──────────────────────────────────────────────
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")

if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.redis import RedisIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(
                transaction_style="url",
                middleware_spans=True,
            ),
            CeleryIntegration(monitor_beat_tasks=True),
            RedisIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        environment=os.environ.get("SENTRY_ENVIRONMENT", "development"),
        release=os.environ.get("SENTRY_RELEASE", "eye-foncier@1.0.0"),
        # Envoyer 20% des transactions en production pour les performances
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.2")),
        # Profiling (optionnel)
        profiles_sample_rate=float(os.environ.get("SENTRY_PROFILES_SAMPLE_RATE", "0.1")),
        # Ne pas envoyer les donnees sensibles
        send_default_pii=False,
        # Filtrer les erreurs non pertinentes
        before_send=lambda event, hint: _sentry_before_send(event, hint),
    )


def _sentry_before_send(event, hint):
    """Filtre les erreurs avant envoi a Sentry."""
    # Ignorer les erreurs 404 (trop de bruit)
    if "logger" in event and event.get("logger") == "django.security.DisallowedHost":
        return None
    # Ignorer les erreurs de throttling
    exc_info = hint.get("exc_info")
    if exc_info:
        exc_type = exc_info[0]
        if exc_type and exc_type.__name__ in ("Throttled", "PermissionDenied"):
            return None
    return event


# ──────────────────────────────────────────────
# Celery — File d'attente asynchrone
# ──────────────────────────────────────────────
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", REDIS_URL or "redis://localhost:6379/1")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", REDIS_URL or "redis://localhost:6379/2")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ALWAYS_EAGER = DEBUG and not REDIS_URL  # Synchrone si pas de Redis en dev
CELERY_BEAT_SCHEDULE = {
    "retry-failed-notifications": {
        "task": "notifications.tasks.retry_failed_notifications",
        "schedule": 300.0,  # Toutes les 5 minutes
    },
    "cleanup-old-notifications": {
        "task": "notifications.tasks.cleanup_old_notifications",
        "schedule": 86400.0,  # Une fois par jour
    },
    "cleanup-old-logs": {
        "task": "notifications.tasks.cleanup_old_logs",
        "schedule": 86400.0,  # Une fois par jour
    },
    # ── Transactions — Timeouts & Expirations ──
    "check-escrow-timeouts": {
        "task": "transactions.tasks.check_escrow_timeouts",
        "schedule": 3600.0,  # Toutes les heures
    },
    "check-dispute-deadlines": {
        "task": "transactions.tasks.check_dispute_deadlines",
        "schedule": 3600.0,  # Toutes les heures
    },
    "check-cotation-expiration": {
        "task": "transactions.tasks.check_cotation_expiration",
        "schedule": 3600.0,  # Toutes les heures
    },
    "daily-transaction-report": {
        "task": "transactions.tasks.generate_daily_transaction_report",
        "schedule": 86400.0,  # Une fois par jour
    },
}
