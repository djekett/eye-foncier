"""Backend d'authentification par email pour EYE-FONCIER."""
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

User = get_user_model()


class EmailBackend(ModelBackend):
    """
    Authentifie les utilisateurs par email au lieu du username.
    Supporte à la fois email et username pour compatibilité admin.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get("email", kwargs.get(User.USERNAME_FIELD))
        if username is None or password is None:
            return None

        # Essayer par email d'abord, puis par username
        try:
            user = User.objects.get(email__iexact=username)
        except User.DoesNotExist:
            try:
                user = User.objects.get(username__iexact=username)
            except User.DoesNotExist:
                # Run the default password hasher to mitigate timing attacks
                User().set_password(password)
                return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
