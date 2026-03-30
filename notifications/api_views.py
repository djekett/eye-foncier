"""
API Views Notifications — EYE-FONCIER
"""
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification, NotificationPreference
from .serializers import NotificationPreferenceSerializer, NotificationSerializer
from .services import get_unread_count, mark_all_read, mark_as_read


class NotificationListAPIView(generics.ListAPIView):
    """Liste des notifications de l'utilisateur authentifié."""

    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Notification.objects.filter(
            recipient=self.request.user,
            channel=Notification.Channel.INAPP,
        )
        # Filtres optionnels
        notif_type = self.request.query_params.get("type")
        if notif_type:
            qs = qs.filter(notification_type=notif_type)
        is_read = self.request.query_params.get("is_read")
        if is_read in ("true", "1"):
            qs = qs.filter(is_read=True)
        elif is_read in ("false", "0"):
            qs = qs.filter(is_read=False)
        priority = self.request.query_params.get("priority")
        if priority:
            qs = qs.filter(priority=priority)
        return qs


class UnreadCountAPIView(APIView):
    """Nombre de notifications non lues."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response({"count": get_unread_count(request.user)})


class NotificationMarkReadAPIView(APIView):
    """Marque une notification comme lue."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        updated = mark_as_read(pk, request.user)
        if updated:
            return Response({"status": "ok", "unread_count": get_unread_count(request.user)})
        return Response({"status": "not_found"}, status=status.HTTP_404_NOT_FOUND)


class MarkAllReadAPIView(APIView):
    """Marque toutes les notifications comme lues."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        count = mark_all_read(request.user)
        return Response({"status": "ok", "marked": count})


class NotificationPreferenceAPIView(generics.RetrieveUpdateAPIView):
    """GET/PUT des préférences de notification."""

    serializer_class = NotificationPreferenceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        obj, _ = NotificationPreference.objects.get_or_create(user=self.request.user)
        return obj


class RegisterFCMTokenAPIView(APIView):
    """Enregistre ou met à jour le token FCM pour les push notifications."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        token = request.data.get("fcm_token", "").strip()
        if not token:
            return Response(
                {"error": "fcm_token est requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        prefs, _ = NotificationPreference.objects.get_or_create(user=request.user)
        prefs.fcm_token = token
        prefs.push_enabled = True
        prefs.save(update_fields=["fcm_token", "push_enabled"])

        return Response({"status": "ok", "message": "Token FCM enregistré."})


class RegisterWhatsAppAPIView(APIView):
    """Enregistre et initie la vérification d'un numéro WhatsApp."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        number = request.data.get("whatsapp_number", "").strip()
        if not number:
            return Response(
                {"error": "whatsapp_number est requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        import re
        if not re.match(r"^\+\d{10,15}$", number):
            return Response(
                {"error": "Format invalide. Utilisez le format international (+225XXXXXXXXXX)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        prefs, _ = NotificationPreference.objects.get_or_create(user=request.user)
        prefs.whatsapp_number = number
        prefs.whatsapp_consent = True
        prefs.save(update_fields=["whatsapp_number", "whatsapp_consent"])

        from .whatsapp_service import verify_whatsapp_number
        verification_sid = verify_whatsapp_number(request.user, number)

        if verification_sid:
            return Response({
                "status": "ok",
                "message": "Code de vérification envoyé sur WhatsApp.",
            })
        return Response(
            {"error": "Impossible d'envoyer le code de vérification."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class VerifyWhatsAppAPIView(APIView):
    """Confirme le code de vérification WhatsApp."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        code = request.data.get("code", "").strip()
        if not code:
            return Response(
                {"error": "code est requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        prefs, _ = NotificationPreference.objects.get_or_create(user=request.user)
        number = prefs.whatsapp_number
        if not number:
            return Response(
                {"error": "Aucun numéro WhatsApp enregistré."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from .whatsapp_service import confirm_whatsapp_verification
        if confirm_whatsapp_verification(request.user, number, code):
            return Response({
                "status": "ok",
                "message": "Numéro WhatsApp vérifié avec succès.",
            })
        return Response(
            {"error": "Code invalide."},
            status=status.HTTP_400_BAD_REQUEST,
        )
