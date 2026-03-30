"""
Monkey-patch pour compatibilité Django 4.2 + Python 3.14.

Python 3.14 a modifié l'implémentation de super() qui ne possède plus
d'attribut __dict__, ce qui casse copy(super()) dans
django.template.context.BaseContext.__copy__().

Ce patch remplace __copy__ par une version compatible.
"""
import sys

# Celery — chargement conditionnel (optionnel en développement)
try:
    from .celery import app as celery_app  # noqa: F401
    __all__ = ("celery_app",)
except ImportError:
    celery_app = None
    __all__ = ()

if sys.version_info >= (3, 14):
    from copy import copy
    import django.template.context as _ctx

    def _patched_base_context_copy(self):
        """Version compatible Python 3.14 de BaseContext.__copy__."""
        cls = self.__class__
        duplicate = cls.__new__(cls)
        duplicate.__dict__.update(self.__dict__)
        duplicate.dicts = self.dicts[:]
        return duplicate

    _ctx.BaseContext.__copy__ = _patched_base_context_copy
