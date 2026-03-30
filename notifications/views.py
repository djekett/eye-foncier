"""
Vues Notifications — EYE-FONCIER
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .forms import NotificationPreferenceForm
from .models import Notification, NotificationPreference
from .services import get_unread_count, mark_all_read, mark_as_read


@login_required
def notification_list_view(request):
    """Liste des notifications in-app de l'utilisateur."""
    notifications = Notification.objects.filter(
        recipient=request.user,
        channel=Notification.Channel.INAPP,
    ).order_by("-created_at")

    # Filtrage optionnel
    filter_type = request.GET.get("type")
    if filter_type:
        notifications = notifications.filter(notification_type=filter_type)

    filter_read = request.GET.get("read")
    if filter_read == "0":
        notifications = notifications.filter(is_read=False)
    elif filter_read == "1":
        notifications = notifications.filter(is_read=True)

    notifications = notifications[:100]

    return render(request, "notifications/notification_list.html", {
        "notifications": notifications,
        "unread_count": get_unread_count(request.user),
        "filter_type": filter_type,
        "filter_read": filter_read,
        "notification_types": Notification.NotificationType.choices,
    })


@login_required
@require_POST
def mark_read_view(request, pk):
    """Marque une notification comme lue (AJAX)."""
    mark_as_read(pk, request.user)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"status": "ok", "unread_count": get_unread_count(request.user)})
    return redirect("notifications:list")


@login_required
@require_POST
def mark_all_read_view(request):
    """Marque toutes les notifications comme lues."""
    mark_all_read(request.user)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"status": "ok", "unread_count": 0})
    return redirect("notifications:list")


@login_required
def preferences_view(request):
    """Gestion des préférences de notification."""
    prefs, _ = NotificationPreference.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = NotificationPreferenceForm(request.POST, instance=prefs)
        if form.is_valid():
            preference = form.save(commit=False)

            # Construire disabled_types depuis les checkboxes enabled_types
            enabled_types = request.POST.getlist("enabled_types")
            all_types = [t[0] for t in Notification.NotificationType.choices]
            preference.disabled_types = [t for t in all_types if t not in enabled_types]

            preference.save()
            messages.success(request, "Préférences de notification mises à jour.")
            return redirect("notifications:preferences")
    else:
        form = NotificationPreferenceForm(instance=prefs)

    return render(request, "notifications/preferences.html", {"form": form})


@login_required
def verify_whatsapp_view(request):
    """Page de vérification du numéro WhatsApp."""
    prefs, _ = NotificationPreference.objects.get_or_create(user=request.user)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "send_code":
            number = prefs.whatsapp_number
            if not number:
                messages.error(request, "Veuillez d'abord configurer votre numéro WhatsApp.")
                return redirect("notifications:preferences")

            from .whatsapp_service import verify_whatsapp_number
            result = verify_whatsapp_number(request.user, number)
            if result:
                messages.success(request, f"Code de vérification envoyé sur WhatsApp au {number}.")
            else:
                messages.error(request, "Impossible d'envoyer le code. Vérifiez le numéro.")

        elif action == "verify_code":
            code = request.POST.get("code", "").strip()
            number = prefs.whatsapp_number

            from .whatsapp_service import confirm_whatsapp_verification
            if confirm_whatsapp_verification(request.user, number, code):
                messages.success(request, "Numéro WhatsApp vérifié avec succès !")
                return redirect("notifications:preferences")
            else:
                messages.error(request, "Code invalide. Veuillez réessayer.")

    return render(request, "notifications/verify_whatsapp.html", {
        "prefs": prefs,
    })
