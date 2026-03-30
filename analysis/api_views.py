"""
API Views Analysis — EYE-FONCIER (Smart Matching REST API)
"""
import logging

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import BuyerProfile, MatchScore
from .serializers import BuyerProfileSerializer, MatchScoreSerializer
from .services.matching_engine import compute_match_for_buyer, compute_match_for_parcelle

logger = logging.getLogger("analysis")


class MatchingResultsAPIView(generics.ListAPIView):
    """Résultats de matching pour l'acheteur authentifié."""

    serializer_class = MatchScoreSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        try:
            profile = self.request.user.buyer_profile
        except BuyerProfile.DoesNotExist:
            return MatchScore.objects.none()

        qs = MatchScore.objects.filter(
            buyer_profile=profile,
            parcelle__status="disponible",
        ).select_related("parcelle", "parcelle__zone")

        # Filtres optionnels
        min_score = self.request.query_params.get("min_score")
        if min_score:
            qs = qs.filter(final_score__gte=float(min_score))

        zone = self.request.query_params.get("zone")
        if zone:
            qs = qs.filter(parcelle__zone_id=zone)

        land_type = self.request.query_params.get("land_type")
        if land_type:
            qs = qs.filter(parcelle__land_type=land_type)

        price_min = self.request.query_params.get("price_min")
        if price_min:
            qs = qs.filter(parcelle__price__gte=price_min)

        price_max = self.request.query_params.get("price_max")
        if price_max:
            qs = qs.filter(parcelle__price__lte=price_max)

        return qs


class TriggerMatchingAPIView(APIView):
    """Force le recalcul du matching pour l'acheteur authentifié."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            profile = request.user.buyer_profile
        except BuyerProfile.DoesNotExist:
            return Response(
                {"detail": "Profil acheteur non trouvé. Créez votre profil d'abord."},
                status=status.HTTP_404_NOT_FOUND,
            )

        scores = compute_match_for_buyer(profile)
        best = max((s.final_score for s in scores), default=0)

        return Response({
            "computed": len(scores),
            "best_score": round(best, 1),
        })


class BuyerProfileAPIView(generics.RetrieveUpdateAPIView):
    """GET/PUT du profil acheteur."""

    serializer_class = BuyerProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        obj, created = BuyerProfile.objects.get_or_create(
            user=self.request.user,
            defaults={"is_active": True},
        )
        return obj

    def perform_update(self, serializer):
        instance = serializer.save()
        # Recalculer le matching après mise à jour du profil
        compute_match_for_buyer(instance)


class ParcelleMatchesAPIView(generics.ListAPIView):
    """Buyers matches pour une parcelle (vue vendeur uniquement)."""

    serializer_class = MatchScoreSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        from parcelles.models import Parcelle
        from rest_framework.exceptions import PermissionDenied

        parcelle_pk = self.kwargs["pk"]

        # Verification : seul le proprietaire peut voir les acheteurs matches
        try:
            parcelle = Parcelle.objects.get(pk=parcelle_pk)
        except Parcelle.DoesNotExist:
            return MatchScore.objects.none()

        user = self.request.user
        if parcelle.owner != user and not user.is_admin_role:
            raise PermissionDenied(
                "Vous n'avez pas acces aux correspondances de cette parcelle."
            )

        return MatchScore.objects.filter(
            parcelle_id=parcelle_pk,
            final_score__gte=50,
        ).select_related(
            "buyer_profile__user", "parcelle", "parcelle__zone"
        ).order_by("-final_score")[:20]


# ─── Heatmap & Parcelle Scores (fusion module analysis ↔ parcelles) ───


class HeatmapDataAPIView(APIView):
    """Données de heatmap prix/demande par zone."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from parcelles.models import Parcelle, Zone
        from django.db.models import Avg, Count, Min, Max

        zone_filter = request.query_params.get("zone")
        zones_qs = Zone.objects.all()
        if zone_filter:
            zones_qs = zones_qs.filter(name__icontains=zone_filter)

        parcelles_qs = Parcelle.objects.filter(status="disponible")
        global_stats = parcelles_qs.aggregate(
            avg_price=Avg("price"),
            total=Count("id"),
        )

        zones_data = []
        for zone in zones_qs:
            zone_parcelles = parcelles_qs.filter(zone=zone)
            agg = zone_parcelles.aggregate(
                price_min=Min("price"),
                price_max=Max("price"),
                avg_price=Avg("price"),
                count=Count("id"),
            )
            if agg["count"] > 0:
                zones_data.append({
                    "id": str(zone.id),
                    "name": zone.name,
                    "code": zone.code,
                    "price_min": float(agg["price_min"] or 0),
                    "price_max": float(agg["price_max"] or 0),
                    "avg_price": float(agg["avg_price"] or 0),
                    "parcelles": agg["count"],
                    "demand": min(100, agg["count"] * 10),
                })

        return Response({
            "stats": {
                "avg_price": float(global_stats["avg_price"] or 0),
                "total": global_stats["total"],
            },
            "zones": zones_data,
        })


class ParcelleScoresAPIView(APIView):
    """Scores d'analyse unifiés d'une parcelle (analysis + parcelles.ParcelleAnalysis)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        from parcelles.models import Parcelle

        try:
            parcelle = Parcelle.objects.get(pk=pk)
        except Parcelle.DoesNotExist:
            return Response(
                {"detail": "Parcelle introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        scores = {
            "parcelle_id": str(parcelle.id),
            "lot_number": parcelle.lot_number,
            "overall_score": 0,
            "accessibility": 0,
            "risk_level": "unknown",
            "constraints": [],
            "terrain": None,
            "proximity": None,
            # Données ParcelleAnalysis (analyse foncière)
            "foncier": None,
        }

        # ── Module analysis: TerrainAnalysis ──
        try:
            ta = parcelle.terrain_analysis
            scores["terrain"] = {
                "elevation_mean": ta.elevation_mean,
                "slope_mean": ta.slope_mean,
                "slope_category": ta.slope_category,
                "technical_score": ta.technical_score,
                "drainage_quality": ta.drainage_quality,
                "solar_potential": ta.solar_potential,
            }
            if ta.slope_mean is not None:
                if ta.slope_mean < 5:
                    scores["overall_score"] += 40
                elif ta.slope_mean < 10:
                    scores["overall_score"] += 30
                elif ta.slope_mean < 15:
                    scores["overall_score"] += 20
                else:
                    scores["overall_score"] += 10
        except Exception:
            scores["overall_score"] += 25

        # ── Module analysis: ProximityAnalysis ──
        try:
            proxs = list(parcelle.proximity_analyses.all())
            if proxs:
                avg_score = sum(p.score or 0 for p in proxs) / len(proxs)
                scores["proximity"] = [
                    {"type": p.poi_type, "distance_m": p.distance_m, "score": p.score, "name": p.poi_name}
                    for p in proxs
                ]
                scores["accessibility"] = round(avg_score, 1)
                scores["overall_score"] += min(30, avg_score * 0.3)
        except Exception:
            scores["accessibility"] = 50
            scores["overall_score"] += 15

        # ── Module analysis: RiskAssessment ──
        try:
            ra = parcelle.risk_assessment
            scores["risk_level"] = ra.overall_risk
            risk_scores = {"low": 30, "medium": 20, "high": 10, "critical": 5}
            scores["overall_score"] += risk_scores.get(ra.overall_risk, 15)
            scores["constraints"] = [
                {
                    "type": c.constraint_type,
                    "severity": c.severity,
                    "description": c.description,
                    "affected_pct": c.affected_area_pct,
                }
                for c in parcelle.spatial_constraints.all()
            ]
        except Exception:
            scores["risk_level"] = "unknown"
            scores["overall_score"] += 15

        # ── Module parcelles: ParcelleAnalysis (analyse foncière) ──
        try:
            pa = parcelle.analysis
            scores["foncier"] = {
                "status": pa.status,
                "overall_score": pa.overall_score,
                "grade": pa.reliability_grade,
                "label": pa.reliability_label,
                "score_geometry": pa.score_geometry,
                "score_documents": pa.score_documents,
                "score_overlap": pa.score_overlap,
                "score_terrain": pa.score_terrain,
                "score_ownership": pa.score_ownership,
                "has_overlap": pa.has_overlap,
                "has_titre_foncier": pa.has_titre_foncier,
                "terrain_inspected": pa.terrain_inspected,
            }
            # Intégrer le score foncier dans le score global (pondéré 50/50)
            foncier_contribution = pa.overall_score * 0.5
            scores["overall_score"] = round(
                scores["overall_score"] * 0.5 + foncier_contribution, 1
            )
        except Exception:
            pass

        scores["overall_score"] = min(100, round(scores["overall_score"]))

        return Response(scores)
