from django.apps import AppConfig


class ParcellesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "parcelles"
    verbose_name = "Gestion des parcelles"

    def ready(self):
        import parcelles.signals  # noqa: F401
