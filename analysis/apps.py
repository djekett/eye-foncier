from django.apps import AppConfig


class AnalysisConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "analysis"
    verbose_name = "Analyse SIG & Matching"

    def ready(self):
        import analysis.signals  # noqa: F401
