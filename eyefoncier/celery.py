"""
Configuration Celery — EYE-FONCIER
File d'attente asynchrone pour les notifications et tâches lourdes.

Celery est optionnel : si le package n'est pas installé, les tâches
s'exécutent en mode synchrone via le fallback dans notifications/services.py.
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "eyefoncier.settings")

app = Celery("eyefoncier")

# Charger la config depuis settings.py avec le préfixe CELERY_
app.config_from_object("django.conf:settings", namespace="CELERY")

# Découverte automatique des tâches dans chaque app Django
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Tâche de test pour vérifier que Celery fonctionne."""
    print(f"Request: {self.request!r}")
