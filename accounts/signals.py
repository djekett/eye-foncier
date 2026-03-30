"""Signals pour créer automatiquement un profil à l'inscription."""
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import User, Profile


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Crée un profil si inexistant — get_or_create évite le conflit
    avec le ProfileInline de l'admin qui crée aussi un Profile."""
    if created:
        Profile.objects.get_or_create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, "profile"):
        try:
            instance.profile.save()
        except Exception:
            pass
