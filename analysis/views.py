"""
Vues du module Analyse SIG, Matching & Rapports — EYE-FONCIER
"""
import json
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, Http404
from django.views.generic import ListView
from django.db.models import Avg, Count, Q

from parcelles.models import Parcelle, Zone
from .models import (
    TerrainAnalysis, SpatialConstraint, ProximityAnalysis,
    RiskAssessment, BuyerProfile, MatchScore, MatchNotification,
    AnalysisReport, GISReferenceLayer,
)
from .forms import BuyerProfileForm

logger = logging.getLogger("analysis")


# ═══════════════════════════════════════════════════════════
# DASHBOARD ANALYSE
# ═══════════════════════════════════════════════════════════

@login_required
def analysis_dashboard(request):
    """Dashboard principal — vue d'ensemble des analyses."""
    context = {
        "total_parcelles": Parcelle.objects.count(),
        "analyzed_parcelles": TerrainAnalysis.objects.count(),
        "risk_assessments": RiskAssessment.objects.count(),
        "reports_count": AnalysisReport.objects.filter(status="ready").count(),
        "avg_score": RiskAssessment.objects.aggregate(
            avg=Avg("overall_score"),
        )["avg"],
        "risk_distribution": {
            "low": RiskAssessment.objects.filter(overall_risk="low").count(),
            "medium": RiskAssessment.objects.filter(overall_risk="medium").count(),
            "high": RiskAssessment.objects.filter(overall_risk="high").count(),
            "critical": RiskAssessment.objects.filter(overall_risk="critical").count(),
        },
        "recent_analyses": TerrainAnalysis.objects.select_related(
            "parcelle",
        ).order_by("-analyzed_at")[:10],
        "top_parcelles": RiskAssessment.objects.filter(
            overall_score__isnull=False,
        ).select_related("parcelle").order_by("-overall_score")[:5],
    }
    return render(request, "analysis/dashboard.html", context)


# ═══════════════════════════════════════════════════════════
# ANALYSE PARCELLE (Module 2)
# ═══════════════════════════════════════════════════════════

@login_required
def parcelle_analysis_view(request, pk):
    """Vue détaillée de l'analyse d'une parcelle."""
    parcelle = get_object_or_404(Parcelle, pk=pk)

    terrain = getattr(parcelle, "terrain_analysis", None)
    risk = getattr(parcelle, "risk_assessment", None)
    constraints = list(parcelle.spatial_constraints.all()) if hasattr(parcelle, "spatial_constraints") else []
    proximities = list(parcelle.proximity_analyses.all()) if hasattr(parcelle, "proximity_analyses") else []
    reports = parcelle.analysis_reports.filter(status="ready").order_by("-generated_at")

    # Données pour radar chart JS
    radar_data = risk.radar_data if risk else {
        "Accessibilité": 0, "Topographie": 0,
        "Juridique": 0, "Environnement": 0, "Prix": 0,
    }

    # Données ParcelleAnalysis (module parcelles — analyse foncière)
    foncier = getattr(parcelle, "analysis", None)

    context = {
        "parcelle": parcelle,
        "terrain": terrain,
        "risk": risk,
        "constraints": constraints,
        "proximities": proximities,
        "reports": reports,
        "radar_data_json": json.dumps(radar_data),
        "is_analyzed": terrain is not None,
        # Fusion avec ParcelleAnalysis
        "foncier": foncier,
        "foncier_score_json": json.dumps({
            "labels": ["Géométrie", "Documents", "Chevauchement", "Terrain", "Propriété"],
            "scores": [
                foncier.score_geometry if foncier else 0,
                foncier.score_documents if foncier else 0,
                foncier.score_overlap if foncier else 0,
                foncier.score_terrain if foncier else 0,
                foncier.score_ownership if foncier else 0,
            ],
        }) if foncier else "null",
    }
    return render(request, "analysis/parcelle_analysis.html", context)


@login_required
def run_analysis_view(request, pk):
    """Lance l'analyse complète d'une parcelle."""
    parcelle = get_object_or_404(Parcelle, pk=pk)

    if not request.user.is_staff and request.user != parcelle.owner:
        messages.error(request, "Vous n'avez pas les droits pour analyser cette parcelle.")
        return redirect("parcelles:detail", pk=pk)

    try:
        from .services.terrain_analyzer import analyze_parcelle_complete
        result = analyze_parcelle_complete(parcelle)
        score = result["risk_assessment"].overall_score or 0
        messages.success(
            request,
            "Analyse complète terminée ! Score global : {:.0f}/100.".format(score),
        )
    except Exception as e:
        logger.error("Erreur analyse: %s", e, exc_info=True)
        messages.error(request, "Erreur lors de l'analyse : {}".format(str(e)[:200]))

    return redirect("analysis:parcelle_analysis", pk=pk)


# ═══════════════════════════════════════════════════════════
# PROFIL ACHETEUR & MATCHING (Module 1)
# ═══════════════════════════════════════════════════════════

@login_required
def buyer_profile_view(request):
    """Création/modification du profil acheteur."""
    profile, created = BuyerProfile.objects.get_or_create(
        user=request.user,
        defaults={"is_active": True},
    )

    if request.method == "POST":
        form = BuyerProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Profil acheteur mis à jour avec succès !")

            # Recalculer le matching
            try:
                from .services.matching_engine import compute_match_for_buyer
                scores = compute_match_for_buyer(profile)
                if scores:
                    best = scores[0].final_score
                    messages.info(
                        request,
                        "{} correspondance(s) calculée(s) — Meilleur score : {:.0f}%.".format(
                            len(scores), best,
                        ),
                    )
            except Exception as e:
                logger.error("Erreur matching: %s", e)

            return redirect("analysis:matching_results")
    else:
        form = BuyerProfileForm(instance=profile)

    context = {
        "form": form,
        "profile": profile,
        "is_new": created,
    }
    return render(request, "analysis/buyer_profile.html", context)


@login_required
def matching_results_view(request):
    """Résultats du Smart Matching pour l'acheteur connecté."""
    try:
        profile = request.user.buyer_profile
    except (BuyerProfile.DoesNotExist, AttributeError):
        messages.info(request, "Configurez d'abord votre profil acheteur pour voir vos correspondances.")
        return redirect("analysis:buyer_profile")

    # Queryset de base (NON slicé) pour les stats
    base_qs = MatchScore.objects.filter(
        buyer_profile=profile,
        parcelle__status="disponible",
    ).select_related(
        "parcelle", "parcelle__zone", "parcelle__owner",
    ).order_by("-final_score")

    # Statistiques AVANT le slice
    total_count = base_qs.count()
    golden_count = base_qs.filter(
        final_score__gte=profile.match_threshold,
    ).count()

    # Slice APRÈS les stats
    matches = base_qs[:50]

    context = {
        "profile": profile,
        "matches": matches,
        "golden_count": golden_count,
        "total_count": total_count,
    }
    return render(request, "analysis/matching_results.html", context)


@login_required
def recalculate_matching_view(request):
    """Recalcule tous les scores de matching pour l'acheteur."""
    try:
        profile = request.user.buyer_profile
    except (BuyerProfile.DoesNotExist, AttributeError):
        messages.info(request, "Créez d'abord votre profil acheteur.")
        return redirect("analysis:buyer_profile")

    try:
        from .services.matching_engine import compute_match_for_buyer
        scores = compute_match_for_buyer(profile)
        messages.success(
            request,
            "Matching recalculé — {} résultat(s).".format(len(scores)),
        )
    except Exception as e:
        logger.error("Erreur recalcul: %s", e)
        messages.error(request, "Erreur lors du recalcul.")

    return redirect("analysis:matching_results")


# ═══════════════════════════════════════════════════════════
# NOTIFICATIONS
# ═══════════════════════════════════════════════════════════

@login_required
def notifications_view(request):
    """Notifications de matching pour l'acheteur."""
    # Queryset de base (NON slicé) pour le update
    base_qs = MatchNotification.objects.filter(
        match_score__buyer_profile__user=request.user,
    ).select_related(
        "match_score", "match_score__parcelle",
    ).order_by("-sent_at")

    # Marquer comme lues AVANT le slice
    unread = base_qs.filter(is_read=False)
    if unread.exists():
        from django.utils import timezone
        unread.update(is_read=True, read_at=timezone.now())

    # Slice APRÈS le update
    notifications = base_qs[:50]

    context = {"notifications": notifications}
    return render(request, "analysis/notifications.html", context)


@login_required
def notifications_count_api(request):
    """API: nombre de notifications non lues."""
    count = MatchNotification.objects.filter(
        match_score__buyer_profile__user=request.user,
        is_read=False,
    ).count()
    return JsonResponse({"count": count})


# ═══════════════════════════════════════════════════════════
# RAPPORT PDF (Module 3)
# ═══════════════════════════════════════════════════════════

@login_required
def generate_report_view(request, pk):
    """Génère un rapport d'analyse PDF."""
    parcelle = get_object_or_404(Parcelle, pk=pk)

    try:
        from .services.report_generator import generate_analysis_report
        report = generate_analysis_report(parcelle, requested_by=request.user)
        messages.success(request, "Rapport d'analyse généré avec succès !")
        return redirect("analysis:report_detail", pk=report.pk)
    except Exception as e:
        logger.error("Erreur rapport: %s", e, exc_info=True)
        messages.error(request, "Erreur lors de la génération : {}".format(str(e)[:200]))
        return redirect("analysis:parcelle_analysis", pk=pk)


@login_required
def report_detail_view(request, pk):
    """Vue d'un rapport généré."""
    report = get_object_or_404(AnalysisReport, pk=pk)
    context = {"report": report, "parcelle": report.parcelle}
    return render(request, "analysis/report_detail.html", context)


@login_required
def report_download_view(request, pk):
    """Téléchargement direct du PDF."""
    report = get_object_or_404(AnalysisReport, pk=pk, status="ready")
    if not report.pdf_file:
        raise Http404("PDF non disponible.")

    response = HttpResponse(report.pdf_file.read(), content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="{}"'.format(
        report.pdf_file.name.split("/")[-1],
    )
    return response


# ═══════════════════════════════════════════════════════════
# API — HEATMAP & DONNÉES CARTE
# ═══════════════════════════════════════════════════════════

def heatmap_data_api(request):
    """API publique : données pour la carte thermique (Heatmap).
    Retourne les parcelles avec leur score et prix.
    """
    parcelles = Parcelle.objects.filter(
        status="disponible",
        is_validated=True,
        centroid__isnull=False,
    ).select_related("zone")

    features = []
    for p in parcelles:
        risk = getattr(p, "risk_assessment", None)
        score = 50
        if risk:
            score = risk.overall_score or 50

        price_per_m2 = float(p.price_per_m2) if p.price_per_m2 else 0
        # Intensité = combinaison prix bas + score élevé
        intensity = (score / 100) * 0.6 + (1 - min(price_per_m2 / 50000, 1)) * 0.4

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [p.centroid.x, p.centroid.y],
            },
            "properties": {
                "id": str(p.pk),
                "lot_number": p.lot_number,
                "title": p.title,
                "price": float(p.price) if p.price else 0,
                "surface": float(p.surface_m2) if p.surface_m2 else 0,
                "score": score,
                "intensity": round(intensity, 2),
                "zone": p.zone.name if p.zone else "",
            },
        })

    return JsonResponse({
        "type": "FeatureCollection",
        "features": features,
    })


def parcelle_scores_api(request, pk):
    """API: scores d'analyse d'une parcelle."""
    parcelle = get_object_or_404(Parcelle, pk=pk)

    data = {"parcelle_id": str(pk), "lot_number": parcelle.lot_number}

    try:
        risk = parcelle.risk_assessment
        data["risk_assessment"] = {
            "overall_score": risk.overall_score,
            "overall_risk": risk.overall_risk,
            "radar": risk.radar_data,
            "recommendation": risk.recommendation,
            "ai_conclusion": risk.ai_conclusion,
            "flood_risk": risk.flood_risk,
            "erosion_risk": risk.erosion_risk,
            "slope_risk": risk.slope_risk,
            "legal_risk": risk.legal_risk,
        }
    except RiskAssessment.DoesNotExist:
        data["risk_assessment"] = None

    try:
        terrain = parcelle.terrain_analysis
        data["terrain"] = {
            "slope_mean": terrain.slope_mean,
            "slope_category": terrain.slope_category,
            "elevation_mean": terrain.elevation_mean,
            "drainage_quality": terrain.drainage_quality,
            "technical_score": terrain.technical_score,
            "aspect": terrain.aspect_dominant,
        }
    except TerrainAnalysis.DoesNotExist:
        data["terrain"] = None

    data["constraints"] = [
        {
            "type": c.constraint_type,
            "severity": c.severity,
            "description": c.description,
            "affected_pct": c.affected_area_pct,
        }
        for c in parcelle.spatial_constraints.all()
    ]

    data["proximity"] = [
        {
            "type": p.poi_type,
            "distance_m": p.distance_m,
            "score": p.score,
            "name": p.poi_name,
        }
        for p in parcelle.proximity_analyses.all()
    ]

    return JsonResponse(data)
