"""Décorateurs RBAC pour Eye-Foncier.

Usage :
    @role_required('vendeur', 'promoteur')
    def my_view(request):
        ...

    @role_required('admin')
    def admin_only_view(request):
        ...
"""
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required


ROLE_LABELS = {
    "visiteur": "Visiteur",
    "acheteur": "Acheteur",
    "vendeur": "Vendeur",
    "promoteur": "Promoteur",
    "geometre": "Géomètre",
    "admin": "Administrateur",
}


def role_required(*roles, redirect_url="accounts:dashboard", message=None):
    """Décorateur : restreint l'accès aux rôles spécifiés.

    Paramètres :
        *roles : str — rôles autorisés ('acheteur', 'vendeur', 'promoteur', 'geometre', 'admin')
        redirect_url : str — URL de redirection si refusé (défaut: dashboard)
        message : str — message d'erreur personnalisé (optionnel)

    Notes :
        - Les superusers et staff sont toujours autorisés
        - 'vendeur' inclut automatiquement 'promoteur' (car is_vendeur couvre les deux)
        - 'admin' accepte aussi is_staff et is_superuser
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            user = request.user

            # Superusers / staff passent toujours
            if user.is_superuser or user.is_staff:
                return view_func(request, *args, **kwargs)

            # Vérifier le rôle
            allowed = False
            for role in roles:
                if role == "admin" and user.is_admin_role:
                    allowed = True
                elif role == "vendeur" and user.is_vendeur:
                    allowed = True
                elif role == "promoteur" and user.is_promoteur:
                    allowed = True
                elif role == "acheteur" and user.is_acheteur:
                    allowed = True
                elif role == "geometre" and user.is_geometre:
                    allowed = True
                elif user.role == role:
                    allowed = True

                if allowed:
                    break

            if not allowed:
                role_names = ", ".join(ROLE_LABELS.get(r, r) for r in roles)
                error_msg = message or f"Accès réservé aux profils : {role_names}."
                messages.error(request, error_msg)
                return redirect(redirect_url)

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def vendeur_required(view_func):
    """Raccourci : accès vendeur ou promoteur uniquement."""
    return role_required("vendeur", "promoteur")(view_func)


def acheteur_required(view_func):
    """Raccourci : accès acheteur uniquement."""
    return role_required("acheteur")(view_func)


def geometre_required(view_func):
    """Raccourci : accès géomètre ou admin uniquement."""
    return role_required("geometre", "admin")(view_func)


def admin_required(view_func):
    """Raccourci : accès admin uniquement."""
    return role_required("admin")(view_func)
