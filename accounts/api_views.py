"""Vues API pour les comptes."""
import uuid as uuid_mod

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import User, Partner, PartnerReferral, AmbassadorProfile, ReferralProgram
from .serializers import (
    RegisterSerializer, UserPrivateSerializer,
    PartnerSerializer, PartnerReferralSerializer, PartnerReferralCreateSerializer,
    AmbassadorProfileSerializer, ReferralProgramSerializer,
)


class RegisterAPIView(generics.CreateAPIView):
    """Inscription via API."""
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {"message": "Compte créé avec succès.", "user_id": str(user.id)},
            status=status.HTTP_201_CREATED,
        )


class CurrentUserAPIView(generics.RetrieveUpdateAPIView):
    """Profil de l'utilisateur connecté."""
    serializer_class = UserPrivateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


# ─── Partenaires ──────────────────────────────────────────


class PartnerListAPIView(generics.ListAPIView):
    """Liste des partenaires actifs, filtrable par type."""
    serializer_class = PartnerSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = Partner.objects.filter(is_active=True)
        partner_type = self.request.query_params.get("type")
        if partner_type:
            qs = qs.filter(partner_type=partner_type)
        return qs


class PartnerDetailAPIView(generics.RetrieveAPIView):
    """Détail d'un partenaire."""
    serializer_class = PartnerSerializer
    permission_classes = [permissions.AllowAny]
    queryset = Partner.objects.filter(is_active=True)


class PartnerReferralCreateAPIView(APIView):
    """Créer une demande de mise en relation avec un partenaire."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = PartnerReferralCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            partner = Partner.objects.get(
                pk=serializer.validated_data["partner_id"], is_active=True
            )
        except Partner.DoesNotExist:
            return Response(
                {"error": "Partenaire introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        from .partner_service import create_referral
        from transactions.models import Transaction

        transaction = None
        tx_id = serializer.validated_data.get("transaction_id")
        if tx_id:
            transaction = Transaction.objects.filter(pk=tx_id).first()

        referral = create_referral(
            partner=partner,
            user=request.user,
            referral_type=serializer.validated_data.get("referral_type", ""),
            transaction=transaction,
            notes=serializer.validated_data.get("notes", ""),
        )

        return Response(
            PartnerReferralSerializer(referral).data,
            status=status.HTTP_201_CREATED,
        )


class MyPartnerReferralsAPIView(generics.ListAPIView):
    """Liste des demandes partenaires de l'utilisateur connecté."""
    serializer_class = PartnerReferralSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return PartnerReferral.objects.filter(user=self.request.user)


# ─── Ambassadeurs ────────────────────────────────────────


class AmbassadorProfileAPIView(APIView):
    """Dashboard ambassadeur : profil + stats."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            ambassador = AmbassadorProfile.objects.get(user=request.user)
        except AmbassadorProfile.DoesNotExist:
            return Response(
                {"error": "Vous n'êtes pas ambassadeur.", "is_ambassador": False},
                status=status.HTTP_404_NOT_FOUND,
            )

        from .ambassador_service import get_ambassador_stats
        stats = get_ambassador_stats(ambassador)

        return Response({
            "profile": AmbassadorProfileSerializer(ambassador).data,
            "stats": stats,
        })


class AmbassadorApplyAPIView(APIView):
    """Candidature au programme ambassadeur."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if AmbassadorProfile.objects.filter(user=request.user).exists():
            return Response(
                {"error": "Vous êtes déjà ambassadeur."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Générer un code unique
        code = f"AMB-{request.user.username[:4].upper()}-{uuid_mod.uuid4().hex[:6].upper()}"

        ambassador = AmbassadorProfile.objects.create(
            user=request.user,
            ambassador_code=code,
        )

        return Response(
            AmbassadorProfileSerializer(ambassador).data,
            status=status.HTTP_201_CREATED,
        )


class ReferralStatsAPIView(generics.ListAPIView):
    """Parrainages de l'utilisateur connecté."""
    serializer_class = ReferralProgramSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ReferralProgram.objects.filter(referrer=self.request.user)


# ═══════════════════════════════════════════════════════
#  DASHBOARD API — KPIs temps réel pour graphiques
# ═══════════════════════════════════════════════════════

class DashboardStatsAPIView(APIView):
    """API endpoint pour les KPIs du dashboard.

    Retourne des données structurées pour graphiques/charts.
    Adapté au rôle de l'utilisateur connecté.

    GET /api/v1/auth/dashboard-stats/
    Optional: ?period=30 (jours, défaut 30)
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from django.utils import timezone
        from django.db.models import Sum, Count
        from datetime import timedelta
        from parcelles.models import Parcelle
        from transactions.models import Transaction

        user = request.user
        period = int(request.query_params.get("period", 30))
        now = timezone.now()
        start_date = now - timedelta(days=period)

        data = {"role": user.role, "period_days": period}

        if user.is_vendeur or getattr(user, "is_promoteur", False):
            parcelles_qs = user.parcelles.all()
            tx_qs = user.sales.all()

            # Parcelles par statut
            data["parcelles"] = {
                "total": parcelles_qs.count(),
                "disponible": parcelles_qs.filter(status="disponible").count(),
                "reserve": parcelles_qs.filter(status="reserve").count(),
                "vendu": parcelles_qs.filter(status="vendu").count(),
                "pending_validation": parcelles_qs.filter(is_validated=False).count(),
            }

            # Revenue
            completed = tx_qs.filter(status="completed")
            data["revenue"] = {
                "total": float(completed.aggregate(s=Sum("amount"))["s"] or 0),
                "period": float(
                    completed.filter(updated_at__gte=start_date).aggregate(
                        s=Sum("amount")
                    )["s"] or 0
                ),
            }

            # Vues par parcelle (top 10)
            data["top_parcelles"] = list(
                parcelles_qs.order_by("-views_count")[:10].values(
                    "id", "lot_number", "title", "views_count", "status", "price"
                )
            )

            # Transactions récentes
            data["transactions"] = {
                "total": tx_qs.count(),
                "pending": tx_qs.filter(
                    status__in=["pending", "reserved", "escrow_funded"]
                ).count(),
                "completed": completed.count(),
            }

            # Timeline : ventes par semaine
            data["timeline"] = self._weekly_counts(
                completed, "updated_at", period, start_date
            )

        elif user.is_acheteur:
            tx_qs = user.purchases.all()
            from transactions.cotation_models import Cotation

            data["transactions"] = {
                "total": tx_qs.count(),
                "pending": tx_qs.filter(
                    status__in=["pending", "reserved", "escrow_funded"]
                ).count(),
                "completed": tx_qs.filter(status="completed").count(),
            }

            cotations_qs = Cotation.objects.filter(payer=user)
            data["cotations"] = {
                "total": cotations_qs.count(),
                "active": cotations_qs.filter(status=Cotation.Status.VALIDATED).count(),
                "total_spent": float(
                    cotations_qs.filter(
                        status__in=[Cotation.Status.VALIDATED, Cotation.Status.PAID]
                    ).aggregate(s=Sum("amount"))["s"] or 0
                ),
            }

        elif user.is_admin_role or user.is_superuser:
            all_parcelles = Parcelle.objects.all()
            all_tx = Transaction.objects.all()

            # KPIs globaux
            completed = all_tx.filter(status="completed")
            data["kpis"] = {
                "total_revenue": float(completed.aggregate(s=Sum("amount"))["s"] or 0),
                "revenue_period": float(
                    completed.filter(updated_at__gte=start_date).aggregate(
                        s=Sum("amount")
                    )["s"] or 0
                ),
                "total_users": User.objects.count(),
                "new_users_period": User.objects.filter(
                    date_joined__gte=start_date
                ).count(),
                "total_parcelles": all_parcelles.count(),
                "new_parcelles_period": all_parcelles.filter(
                    created_at__gte=start_date
                ).count(),
            }

            # Utilisateurs par rôle
            data["users_by_role"] = dict(
                User.objects.values_list("role").annotate(
                    c=Count("id")
                ).values_list("role", "c")
            )

            # Parcelles par statut
            data["parcelles_by_status"] = dict(
                all_parcelles.values_list("status").annotate(
                    c=Count("id")
                ).values_list("status", "c")
            )

            # Transactions par statut
            data["transactions_by_status"] = dict(
                all_tx.values_list("status").annotate(
                    c=Count("id")
                ).values_list("status", "c")
            )

            # Timeline : nouvelles parcelles + ventes par semaine
            data["timeline_parcelles"] = self._weekly_counts(
                all_parcelles, "created_at", period, start_date
            )
            data["timeline_transactions"] = self._weekly_counts(
                completed, "updated_at", period, start_date
            )

        return Response(data)

    @staticmethod
    def _weekly_counts(queryset, date_field, period, start_date):
        """Agrège par semaine pour les graphiques timeline."""
        from django.db.models.functions import TruncWeek
        from django.db.models import Count

        return list(
            queryset.filter(
                **{f"{date_field}__gte": start_date}
            ).annotate(
                week=TruncWeek(date_field)
            ).values("week").annotate(
                count=Count("id")
            ).order_by("week").values("week", "count")
        )
