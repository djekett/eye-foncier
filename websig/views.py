"""Vues WebSIG — Carte interactive et page d'accueil."""
from django.shortcuts import render
from parcelles.models import Parcelle, Zone


def home_view(request):
    """Page d'accueil."""
    context = {
        "total_parcelles": Parcelle.objects.filter(is_validated=True).count(),
        "available_parcelles": Parcelle.objects.filter(
            is_validated=True, status="disponible"
        ).count(),
        "total_zones": Zone.objects.count(),
        "zones": Zone.objects.all(),
        "recent_parcelles": Parcelle.objects.filter(
            is_validated=True, status="disponible"
        ).select_related("zone", "owner").prefetch_related("medias")[:6],
    }
    # IDs des parcelles likées par l'utilisateur connecté
    if request.user.is_authenticated:
        from parcelles.models import ParcelleReaction
        context["user_liked_ids"] = set(
            ParcelleReaction.objects.filter(
                user=request.user, reaction_type="like"
            ).values_list("parcelle_id", flat=True)
        )
    else:
        context["user_liked_ids"] = set()
    return render(request, "websig/home.html", context)


def map_view(request):
    """Vue carte interactive principale.

    Paramètres GET optionnels :
      • focus=<uuid>  → zoom automatique sur cette parcelle au chargement
    """
    zones = Zone.objects.all().order_by("name")

    # ID de parcelle à focaliser (provient de la redirection après création)
    focus_id = request.GET.get("focus", "")

    # Centrer sur Abidjan par défaut, mais si une zone spécifique est dans le filtre
    # on pourrait recentrer côté JS
    context = {
        "zones": zones,
        "default_lat": 5.3600,
        "default_lng": -4.0083,
        "default_zoom": 12,
        "is_authenticated": request.user.is_authenticated,
        "is_superuser": request.user.is_superuser if request.user.is_authenticated else False,
        "focus_parcelle_id": focus_id,
    }
    return render(request, "websig/map.html", context)
