"""
Service d'analyse foncière — EYE-FONCIER
Évalue la fiabilité d'une parcelle : géométrie, documents, chevauchement, terrain.
"""
import logging
from decimal import Decimal
from django.utils import timezone
from django.contrib.gis.db.models.functions import Area, Intersection
from django.contrib.gis.measure import A as AreaMeasure
from django.db.models import Q

from .models import Parcelle, ParcelleAnalysis

logger = logging.getLogger("parcelles.analysis")


class AnalysisError(Exception):
    pass


def run_full_analysis(parcelle, inspector=None):
    """Lance l'analyse complète d'une parcelle.

    Crée ou met à jour le ParcelleAnalysis associé.
    Returns: ParcelleAnalysis instance.
    """
    analysis, created = ParcelleAnalysis.objects.get_or_create(
        parcelle=parcelle,
        defaults={"status": ParcelleAnalysis.AnalysisStatus.IN_PROGRESS},
    )
    if not created:
        analysis.status = ParcelleAnalysis.AnalysisStatus.IN_PROGRESS
        analysis.save(update_fields=["status"])

    logger.info("Analyse foncière — parcelle %s (lot %s)", parcelle.pk, parcelle.lot_number)

    # 1. Analyse géométrique
    _analyze_geometry(analysis, parcelle)

    # 2. Détection chevauchement
    _detect_overlap(analysis, parcelle)

    # 3. Vérification documentaire
    _check_documents(analysis, parcelle)

    # 4. Vérification propriété
    _check_ownership(analysis, parcelle)

    # 5. Contrôle terrain (si inspecteur fourni)
    if inspector:
        analysis.terrain_inspector = inspector

    # 6. Intégrer les données du module analysis (topographie, risques, proximité)
    _sync_from_analysis_module(analysis, parcelle)

    # 7. Calcul score global
    analysis.compute_overall_score()
    analysis.analyzed_at = timezone.now()
    if inspector:
        analysis.analyzed_by = inspector
    analysis.save()

    logger.info(
        "Analyse terminée — lot %s — score %d/100 (%s)",
        parcelle.lot_number, analysis.overall_score, analysis.reliability_grade,
    )
    return analysis


def _analyze_geometry(analysis, parcelle):
    """Vérifie la cohérence géométrique : surface déclarée vs calculée."""
    analysis.declared_surface = parcelle.surface_m2

    if parcelle.geometry:
        # Calcul surface réelle via PostGIS (en m² — reprojection UTM zone 30N pour l'Afrique de l'Ouest)
        from django.contrib.gis.geos import GEOSGeometry
        geom = parcelle.geometry

        # Utiliser la surface géographique (geography=True pour résultat en m²)
        try:
            # Transformer en projection métrique (UTM 30N — EPSG:32630 pour Côte d'Ivoire)
            geom_utm = geom.transform(32630, clone=True)
            computed = Decimal(str(round(geom_utm.area, 2)))
        except Exception:
            # Fallback : estimation par degrés (approximatif)
            computed = Decimal(str(round(geom.area * 1e10, 2)))  # très approximatif

        analysis.computed_surface = computed

        if analysis.declared_surface and analysis.declared_surface > 0:
            deviation = abs(computed - analysis.declared_surface) / analysis.declared_surface * 100
            analysis.surface_deviation_pct = round(deviation, 2)

            # Score géométrie : 100 si écart < 5%, 0 si écart > 50%
            if deviation <= 5:
                analysis.score_geometry = 100
            elif deviation <= 10:
                analysis.score_geometry = 85
            elif deviation <= 20:
                analysis.score_geometry = 60
            elif deviation <= 35:
                analysis.score_geometry = 30
            else:
                analysis.score_geometry = 10
        else:
            analysis.score_geometry = 50  # Pas de surface déclarée, neutre
    else:
        analysis.score_geometry = 0  # Pas de géométrie du tout


def _detect_overlap(analysis, parcelle):
    """Détecte les chevauchements avec d'autres parcelles validées."""
    analysis.has_overlap = False
    analysis.overlap_parcelles = []
    analysis.overlap_area_m2 = Decimal("0")

    if not parcelle.geometry:
        analysis.score_overlap = 50
        return

    # Chercher les parcelles dont le polygon intersecte celui-ci
    overlapping = (
        Parcelle.objects
        .exclude(pk=parcelle.pk)
        .filter(geometry__intersects=parcelle.geometry)
        .only("id", "lot_number", "geometry")
    )

    overlap_ids = []
    total_overlap_m2 = Decimal("0")

    for other in overlapping:
        try:
            intersection = parcelle.geometry.intersection(other.geometry)
            if intersection and not intersection.empty:
                # Calculer la surface de l'intersection
                try:
                    inter_utm = intersection.transform(32630, clone=True)
                    inter_area = Decimal(str(round(inter_utm.area, 2)))
                except Exception:
                    inter_area = Decimal(str(round(intersection.area * 1e10, 2)))

                # Ne compter que si > 1 m² (filtrer les artefacts de bordure)
                if inter_area > 1:
                    overlap_ids.append({
                        "id": str(other.pk),
                        "lot_number": other.lot_number,
                        "overlap_m2": float(inter_area),
                    })
                    total_overlap_m2 += inter_area
        except Exception as e:
            logger.warning("Erreur intersection lot %s vs %s: %s", parcelle.lot_number, other.lot_number, e)

    analysis.overlap_parcelles = overlap_ids
    analysis.overlap_area_m2 = total_overlap_m2
    analysis.has_overlap = len(overlap_ids) > 0

    # Score chevauchement
    if not overlap_ids:
        analysis.score_overlap = 100
    else:
        # Ratio surface chevauchement / surface parcelle
        parcelle_surface = analysis.computed_surface or analysis.declared_surface or Decimal("1")
        overlap_ratio = float(total_overlap_m2 / parcelle_surface * 100)
        if overlap_ratio < 1:
            analysis.score_overlap = 90  # Chevauchement négligeable
        elif overlap_ratio < 5:
            analysis.score_overlap = 60
        elif overlap_ratio < 20:
            analysis.score_overlap = 30
        else:
            analysis.score_overlap = 0  # Conflit majeur


def _check_documents(analysis, parcelle):
    """Vérifie la présence des documents fonciers clés."""
    medias = parcelle.medias.all()
    media_types = set(medias.values_list("media_type", flat=True))
    media_titles = set(m.title.lower() for m in medias if m.title)

    # Vérification par type de média et titre
    analysis.has_images_terrain = "image" in media_types or "drone" in media_types
    analysis.has_plan_cadastral = "plan" in media_types

    # Chercher dans les titres des documents
    for title in media_titles:
        if "titre foncier" in title or "titre" in title:
            analysis.has_titre_foncier = True
        if "attestation" in title:
            analysis.has_attestation = True
        if "cadastr" in title or "plan" in title:
            analysis.has_plan_cadastral = True

    # Score documentaire
    doc_points = 0
    if analysis.has_titre_foncier:
        doc_points += 35  # Document le plus important
    if analysis.has_attestation:
        doc_points += 25
    if analysis.has_plan_cadastral:
        doc_points += 20
    if analysis.has_images_terrain:
        doc_points += 10
    if medias.count() >= 3:
        doc_points += 10  # Bonus pour plusieurs documents

    analysis.score_documents = min(doc_points, 100)


def _sync_from_analysis_module(analysis, parcelle):
    """Tire les scores depuis le module analysis (TerrainAnalysis, RiskAssessment).

    Interconnexion : analysis.TerrainAnalysis.technical_score → score_terrain
    si aucune inspection terrain manuelle n'a été faite.
    Les contraintes spatiales enrichissent le rapport.
    """
    try:
        from analysis.models import TerrainAnalysis, RiskAssessment, SpatialConstraint

        # ── Intégrer le score terrain depuis TerrainAnalysis ──
        if not analysis.terrain_inspected:
            try:
                terrain = parcelle.terrain_analysis
                if terrain and terrain.technical_score is not None:
                    analysis.score_terrain = min(100, max(0, int(terrain.technical_score)))
                    analysis.terrain_notes = (
                        (analysis.terrain_notes or "") +
                        "\n[Auto] Score topographique : {}/100 — Pente : {}% ({}) — "
                        "Drainage : {} — Source : {}".format(
                            int(terrain.technical_score),
                            terrain.slope_mean or 0,
                            terrain.get_slope_category_display() if terrain.slope_category else "N/A",
                            terrain.drainage_quality or "N/A",
                            terrain.dem_source or "N/A",
                        )
                    ).strip()
                    logger.info(
                        "Score terrain synchro depuis TerrainAnalysis: %d/100 (lot %s)",
                        analysis.score_terrain, parcelle.lot_number,
                    )
            except Exception as e:
                logger.debug("Pas de TerrainAnalysis pour lot %s: %s", parcelle.lot_number, e)

        # ── Enrichir avec les contraintes spatiales ──
        try:
            constraints = list(SpatialConstraint.objects.filter(parcelle=parcelle))
            if constraints:
                critical = sum(1 for c in constraints if c.severity == "critical")
                warnings = sum(1 for c in constraints if c.severity == "warning")

                # Les contraintes spatiales pénalisent le score de chevauchement/géométrie
                penalty = critical * 15 + warnings * 5
                analysis.score_overlap = max(0, analysis.score_overlap - penalty)

                constraint_info = " | ".join(
                    "{} ({})".format(c.get_constraint_type_display(), c.get_severity_display())
                    for c in constraints
                )
                analysis.analysis_report = (
                    (analysis.analysis_report or "") +
                    "\n[Contraintes spatiales] {}".format(constraint_info)
                ).strip()
        except Exception as e:
            logger.debug("Pas de contraintes spatiales pour lot %s: %s", parcelle.lot_number, e)

        # ── Intégrer le RiskAssessment global ──
        try:
            risk = parcelle.risk_assessment
            if risk and risk.overall_score is not None:
                risk_info = "Score risque global : {}/100 — Niveau : {} — {}".format(
                    int(risk.overall_score),
                    risk.get_overall_risk_display(),
                    risk.ai_conclusion[:200] if risk.ai_conclusion else "Pas de conclusion IA",
                )
                analysis.analysis_report = (
                    (analysis.analysis_report or "") +
                    "\n[Évaluation risques] {}".format(risk_info)
                ).strip()
        except Exception as e:
            logger.debug("Pas de RiskAssessment pour lot %s: %s", parcelle.lot_number, e)

    except ImportError:
        logger.debug("Module analysis non disponible — synchronisation ignorée")


def _check_ownership(analysis, parcelle):
    """Vérifie la cohérence propriétaire."""
    score = 0

    # Nom sur titre foncier vs nom du compte
    if parcelle.trust_badge:
        score += 50  # Correspondance confirmée

    if parcelle.title_holder_name:
        score += 20  # Au moins renseigné

    # Profil vérifié (KYC)
    if parcelle.owner and hasattr(parcelle.owner, "profile"):
        profile = parcelle.owner.profile
        if hasattr(profile, "kyc_status") and profile.kyc_status == "verified":
            score += 30

    # Historique renseigné
    if analysis.ownership_history:
        score += min(len(analysis.ownership_history) * 10, 30)

    analysis.score_ownership = min(score, 100)


def validate_analysis(analysis, validator, notes=""):
    """Un vérificateur valide ou rejette l'analyse."""
    if analysis.overall_score >= 40:
        analysis.status = ParcelleAnalysis.AnalysisStatus.VALIDATED
        analysis.parcelle.is_validated = True
        analysis.parcelle.validated_by = validator
        analysis.parcelle.validated_at = timezone.now()
        analysis.parcelle.save(update_fields=["is_validated", "validated_by", "validated_at"])
    else:
        analysis.status = ParcelleAnalysis.AnalysisStatus.REJECTED

    analysis.validated_at = timezone.now()
    analysis.analyzed_by = validator
    if notes:
        analysis.analysis_report = (analysis.analysis_report or "") + f"\n[{timezone.now():%d/%m/%Y %H:%M}] {validator.get_full_name()}: {notes}"
    analysis.save()

    # Notification au propriétaire
    try:
        from notifications.services import send_notification
        result = "validée" if analysis.status == "validated" else "rejetée"
        send_notification(
            recipient=analysis.parcelle.owner,
            notification_type="transaction_status",
            title=f"Analyse foncière {result}",
            message=(
                f"L'analyse de votre parcelle « {analysis.parcelle.title} » (Lot {analysis.parcelle.lot_number}) "
                f"est {result}. Score de fiabilité : {analysis.overall_score}/100 ({analysis.reliability_label})."
            ),
            data={
                "parcelle_id": str(analysis.parcelle.pk),
                "score": analysis.overall_score,
                "grade": analysis.reliability_grade,
            },
        )
    except Exception as e:
        logger.warning("Erreur notification analyse: %s", e)

    return analysis


def record_terrain_inspection(analysis, inspector, score, notes="", photos=None):
    """Enregistre le résultat d'une inspection terrain."""
    analysis.terrain_inspected = True
    analysis.terrain_inspector = inspector
    analysis.terrain_inspection_date = timezone.now()
    analysis.score_terrain = min(max(score, 0), 100)
    if notes:
        analysis.terrain_notes = notes
    if photos:
        analysis.terrain_photos = photos

    # Recalculer le score global
    analysis.compute_overall_score()
    analysis.save()

    # Notification au propriétaire
    try:
        from notifications.services import send_notification
        send_notification(
            recipient=analysis.parcelle.owner,
            notification_type="transaction_status",
            title="Inspection terrain effectuée",
            message=(
                f"L'inspection terrain de votre parcelle « {analysis.parcelle.title} » "
                f"(Lot {analysis.parcelle.lot_number}) est terminée. "
                f"Score terrain : {score}/100. Score global : {analysis.overall_score}/100."
            ),
            data={
                "parcelle_id": str(analysis.parcelle.pk),
                "score_terrain": score,
                "overall_score": analysis.overall_score,
            },
        )
    except Exception as e:
        logger.warning("Erreur notification inspection: %s", e)

    return analysis


def submit_for_validation(parcelle, requester):
    """Un vendeur soumet sa parcelle pour validation par un géomètre.

    Lance l'analyse automatisée si elle n'existe pas, puis notifie
    les géomètres disponibles.
    """
    # S'assurer qu'une analyse existe
    analysis, created = ParcelleAnalysis.objects.get_or_create(
        parcelle=parcelle,
        defaults={"status": ParcelleAnalysis.AnalysisStatus.PENDING},
    )

    # Si c'est une soumission initiale, lancer l'analyse auto
    if created or analysis.status == ParcelleAnalysis.AnalysisStatus.PENDING:
        try:
            analysis = run_full_analysis(parcelle, inspector=requester)
        except Exception as e:
            logger.error("Erreur analyse auto: %s", e)

    # Passer en statut "en cours" (attente validation géomètre)
    if analysis.status != ParcelleAnalysis.AnalysisStatus.VALIDATED:
        analysis.status = ParcelleAnalysis.AnalysisStatus.IN_PROGRESS
        analysis.save(update_fields=["status", "updated_at"])

    # Notifier les géomètres
    try:
        from notifications.services import send_notification
        from accounts.models import User
        geometres = User.objects.filter(role="geometre", is_active=True)
        for geo in geometres[:10]:  # Limiter à 10 géomètres
            send_notification(
                recipient=geo,
                notification_type="transaction_status",
                title="Nouvelle parcelle à valider",
                message=(
                    f"{requester.get_full_name()} a soumis la parcelle "
                    f"« {parcelle.title} » (Lot {parcelle.lot_number}) pour validation. "
                    f"Score auto : {analysis.overall_score}/100."
                ),
                data={
                    "parcelle_id": str(parcelle.pk),
                    "action": "validation_request",
                },
            )
    except Exception as e:
        logger.warning("Erreur notification géomètres: %s", e)

    return analysis
