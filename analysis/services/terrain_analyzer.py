"""
Service d'Analyse Topographique & Spatiale — EYE-FONCIER
Module 2 : Scanner de terrain à distance.

Analyse MNT (GeoTIFF), pentes, exposition, hydrologie,
croisement avec couches SIG (zones inondables, servitudes, urbanisme),
analyse de proximité aux infrastructures.

Fonctionne avec ou sans données raster réelles (mode démo inclus).
"""
import json
import logging
import math
import os

from django.contrib.gis.geos import Point, GEOSGeometry
from django.contrib.gis.measure import D
from django.contrib.gis.db.models.functions import Distance
from django.utils import timezone

logger = logging.getLogger("analysis")


# ═══════════════════════════════════════════════════════════
# ANALYSE TOPOGRAPHIQUE (MNT / DEM)
# ═══════════════════════════════════════════════════════════

def analyze_terrain(parcelle, dem_path=None):
    """Analyse complète du terrain d'une parcelle.

    Args:
        parcelle: instance Parcelle avec geometry
        dem_path: chemin vers fichier GeoTIFF (optionnel, mode démo sinon)

    Returns:
        TerrainAnalysis instance (saved)
    """
    from analysis.models import TerrainAnalysis

    analysis, _ = TerrainAnalysis.objects.update_or_create(
        parcelle=parcelle,
        defaults={"dem_source": ""},
    )

    if dem_path and os.path.exists(dem_path):
        _analyze_with_raster(analysis, parcelle, dem_path)
    else:
        _analyze_simulated(analysis, parcelle)

    # Catégoriser la pente
    analysis.slope_category = _categorize_slope(analysis.slope_mean or 0)
    analysis.slope_is_constructible = (analysis.slope_mean or 0) < 15.0

    # Calculer le potentiel solaire selon l'exposition
    analysis.solar_potential = _calculate_solar_potential(analysis.aspect_dominant)

    # Calculer la qualité du drainage
    analysis.drainage_quality = _assess_drainage(
        analysis.slope_mean or 0,
        analysis.water_accumulation_risk or 0,
    )

    # Score technique composite
    analysis.technical_score = _compute_technical_score(analysis)

    analysis.analyzed_at = timezone.now()
    analysis.save()

    logger.info(
        "Terrain analysé: %s — Score: %s/100",
        parcelle.lot_number,
        int(analysis.technical_score) if analysis.technical_score else "N/A",
    )
    return analysis


def _analyze_with_raster(analysis, parcelle, dem_path):
    """Analyse réelle avec rasterio à partir d'un GeoTIFF."""
    try:
        import rasterio
        from rasterio.mask import mask as rasterio_mask
        import numpy as np

        geom = parcelle.geometry
        # Convertir en GeoJSON pour rasterio
        geojson = json.loads(geom.json)

        with rasterio.open(dem_path) as src:
            out_image, out_transform = rasterio_mask(
                src, [geojson], crop=True, nodata=src.nodata,
            )
            elevation = out_image[0]

            # Masquer les nodata
            if src.nodata is not None:
                elevation = np.ma.masked_equal(elevation, src.nodata)

            valid = elevation.compressed() if hasattr(elevation, "compressed") else elevation.flatten()
            valid = valid[~np.isnan(valid)] if len(valid) > 0 else np.array([0])

            analysis.elevation_min = float(np.min(valid))
            analysis.elevation_max = float(np.max(valid))
            analysis.elevation_mean = float(np.mean(valid))
            analysis.elevation_range = float(np.ptp(valid))

            # Calcul de pente (gradient)
            pixel_size = abs(out_transform.a)  # taille pixel en degrés
            pixel_m = pixel_size * 111320  # approximation en mètres
            if elevation.shape[0] > 1 and elevation.shape[1] > 1:
                gy, gx = np.gradient(elevation.astype(float), pixel_m)
                slope_rad = np.arctan(np.sqrt(gx ** 2 + gy ** 2))
                slope_pct = np.tan(slope_rad) * 100
                slope_valid = slope_pct.flatten()
                slope_valid = slope_valid[~np.isnan(slope_valid)]
                analysis.slope_mean = float(np.mean(slope_valid))
                analysis.slope_max = float(np.max(slope_valid))

                # Exposition (aspect)
                aspect_rad = np.arctan2(-gy, gx)
                aspect_deg = np.degrees(aspect_rad) % 360
                mean_aspect = float(np.mean(aspect_deg.flatten()[~np.isnan(aspect_deg.flatten())]))
                analysis.aspect_dominant = _degrees_to_aspect(mean_aspect)

                # Hydrologie — accumulation (simplifiée)
                analysis.water_accumulation_risk = _compute_water_risk(elevation, slope_pct)
            else:
                analysis.slope_mean = 0.0
                analysis.slope_max = 0.0
                analysis.aspect_dominant = "FLAT"
                analysis.water_accumulation_risk = 10.0

            analysis.dem_source = os.path.basename(dem_path)
            analysis.raw_data = {
                "pixel_size_m": round(pixel_m, 2),
                "n_pixels": int(valid.size),
                "elevation_std": round(float(np.std(valid)), 2),
            }

    except ImportError:
        logger.warning("rasterio non installé — mode démo activé")
        _analyze_simulated(analysis, parcelle)
    except Exception as e:
        logger.error("Erreur analyse raster: %s", e, exc_info=True)
        _analyze_simulated(analysis, parcelle)


def _analyze_simulated(analysis, parcelle):
    """Analyse simulée basée sur la géométrie de la parcelle.
    Utilisée quand aucun MNT n'est disponible.
    """
    geom = parcelle.geometry
    centroid = geom.centroid

    # Simulation réaliste pour Abidjan / Côte d'Ivoire
    # Élévation basée sur la latitude (zones côtières = basses)
    base_elev = 20.0 + abs(centroid.y - 5.3) * 150
    analysis.elevation_min = round(base_elev - 3, 1)
    analysis.elevation_max = round(base_elev + 5, 1)
    analysis.elevation_mean = round(base_elev, 1)
    analysis.elevation_range = round(analysis.elevation_max - analysis.elevation_min, 1)

    # Pente simulée (basée sur le dénivelé et la taille)
    area_m2 = float(parcelle.surface_m2) if parcelle.surface_m2 else geom.area * 1e10
    diagonal = math.sqrt(area_m2) * 1.4
    analysis.slope_mean = round(
        (analysis.elevation_range / max(diagonal, 1)) * 100, 1,
    )
    analysis.slope_max = round(analysis.slope_mean * 1.8, 1)

    analysis.aspect_dominant = "S"  # Exposition Sud par défaut (Afrique de l'Ouest)
    analysis.water_accumulation_risk = round(max(0, 30 - analysis.slope_mean * 2), 1)
    analysis.dem_source = "Simulation (pas de MNT)"
    analysis.raw_data = {"mode": "simulated"}


def _categorize_slope(slope_pct):
    """Catégorise la pente."""
    from analysis.models import TerrainAnalysis
    if slope_pct < 5:
        return TerrainAnalysis.SlopeCategory.FLAT
    if slope_pct < 10:
        return TerrainAnalysis.SlopeCategory.GENTLE
    if slope_pct < 15:
        return TerrainAnalysis.SlopeCategory.MODERATE
    if slope_pct < 25:
        return TerrainAnalysis.SlopeCategory.STEEP
    return TerrainAnalysis.SlopeCategory.VERY_STEEP


def _degrees_to_aspect(deg):
    """Convertit un angle en orientation cardinale."""
    directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    idx = int(((deg + 22.5) % 360) / 45)
    return directions[idx]


def _calculate_solar_potential(aspect):
    """Score solaire selon l'exposition (0-100). Sud = meilleur en zone tropicale."""
    scores = {
        "S": 90, "SE": 85, "SW": 85,
        "E": 70, "W": 70,
        "NE": 55, "NW": 55,
        "N": 45, "FLAT": 80, "": 70,
    }
    return scores.get(aspect, 70)


def _assess_drainage(slope_mean, water_risk):
    """Évalue la qualité du drainage."""
    if slope_mean > 10 and water_risk < 20:
        return "excellent"
    if slope_mean > 5 and water_risk < 40:
        return "bon"
    if water_risk < 60:
        return "moyen"
    return "mauvais"


def _compute_water_risk(elevation, slope_pct):
    """Calcule le risque d'accumulation d'eau (0-100)."""
    import numpy as np
    flat_pixels = np.sum(slope_pct < 2)
    total_pixels = max(slope_pct.size, 1)
    flat_ratio = flat_pixels / total_pixels

    elev_range = float(np.ptp(elevation.flatten()[~np.isnan(elevation.flatten())]))
    low_relief = max(0, 1 - elev_range / 10)

    risk = (flat_ratio * 60 + low_relief * 40)
    return round(min(100, max(0, risk)), 1)


def _compute_technical_score(analysis):
    """Score technique composite (0-100)."""
    score = 100.0

    # Pénalité pente (> 15% = forte pénalité)
    slope = analysis.slope_mean or 0
    if slope > 25:
        score -= 40
    elif slope > 15:
        score -= 25
    elif slope > 10:
        score -= 10
    elif slope > 5:
        score -= 3

    # Bonus exposition
    solar = analysis.solar_potential or 70
    score += (solar - 70) * 0.2

    # Pénalité risque eau
    water_risk = analysis.water_accumulation_risk or 0
    score -= water_risk * 0.3

    # Bonus terrain plat
    if analysis.elevation_range and analysis.elevation_range < 3:
        score += 5

    return round(max(0, min(100, score)), 1)


# ═══════════════════════════════════════════════════════════
# ANALYSE DES CONTRAINTES SPATIALES
# ═══════════════════════════════════════════════════════════

def analyze_spatial_constraints(parcelle):
    """Croise la parcelle avec toutes les couches SIG de référence actives.

    Returns:
        list[SpatialConstraint]: contraintes détectées
    """
    from analysis.models import GISReferenceLayer, SpatialConstraint

    # Supprimer les anciennes contraintes
    SpatialConstraint.objects.filter(parcelle=parcelle).delete()

    layers = GISReferenceLayer.objects.filter(is_active=True)
    constraints = []

    for layer in layers:
        if not layer.geometry:
            continue

        layer_geom = layer.geometry

        # Appliquer le buffer si défini
        if layer.buffer_distance_m:
            # Approximation : convertir mètres en degrés (~1°≈111km)
            buffer_deg = layer.buffer_distance_m / 111320.0
            layer_geom = layer_geom.buffer(buffer_deg)

        # Vérifier l'intersection
        if parcelle.geometry.intersects(layer_geom):
            intersection = parcelle.geometry.intersection(layer_geom)
            affected_area = intersection.area / max(parcelle.geometry.area, 1e-12) * 100

            constraint_type = _layer_type_to_constraint(layer.layer_type)
            severity = _determine_severity(layer.layer_type, affected_area)

            constraint = SpatialConstraint.objects.create(
                parcelle=parcelle,
                constraint_type=constraint_type,
                severity=severity,
                description="Intersection détectée avec la couche « {} ». "
                            "Surface affectée : {:.1f}%.".format(layer.name, affected_area),
                affected_area_pct=round(affected_area, 1),
                source_layer=layer.name,
                intersection_geometry=intersection,
            )
            constraints.append(constraint)

            logger.info(
                "Contrainte détectée: %s — %s (%.1f%%) sur %s",
                constraint_type, severity, affected_area, parcelle.lot_number,
            )

    return constraints


def _layer_type_to_constraint(layer_type):
    """Convertit un type de couche SIG en type de contrainte."""
    mapping = {
        "flood_zone": "flood_zone",
        "erosion_zone": "erosion",
        "power_line": "power_line",
        "pipeline": "pipeline",
        "green_zone": "green_zone",
        "urban_zone": "green_zone",
    }
    return mapping.get(layer_type, "custom")


def _determine_severity(layer_type, affected_pct):
    """Détermine la gravité selon le type et le % affecté."""
    critical_types = {"flood_zone", "green_zone"}
    if layer_type in critical_types and affected_pct > 30:
        return "critical"
    if affected_pct > 50:
        return "critical"
    if affected_pct > 15:
        return "warning"
    return "info"


# ═══════════════════════════════════════════════════════════
# ANALYSE DE PROXIMITÉ
# ═══════════════════════════════════════════════════════════

def analyze_proximity(parcelle):
    """Calcule les distances aux infrastructures clés.

    Returns:
        list[ProximityAnalysis]: résultats de proximité
    """
    from analysis.models import ProximityAnalysis, GISReferenceLayer

    centroid = parcelle.centroid or parcelle.geometry.centroid
    results = []

    # Chercher les POI dans les couches de référence
    poi_layers = GISReferenceLayer.objects.filter(
        is_active=True,
        layer_type="poi",
    )

    if poi_layers.exists():
        results.extend(_analyze_from_layers(parcelle, centroid, poi_layers))
    else:
        # Mode simulation — données réalistes pour Abidjan
        results.extend(_analyze_simulated_proximity(parcelle, centroid))

    return results


def _analyze_from_layers(parcelle, centroid, poi_layers):
    """Analyse de proximité à partir des couches SIG."""
    from analysis.models import ProximityAnalysis

    results = []
    for layer in poi_layers:
        if not layer.geometry:
            continue

        # Distance au point le plus proche de la couche
        distance = centroid.distance(layer.geometry) * 111320  # approx degrés → mètres

        poi_type = layer.metadata.get("poi_type", "road")
        score = _distance_to_score(distance, poi_type)

        prox, _ = ProximityAnalysis.objects.update_or_create(
            parcelle=parcelle,
            poi_type=poi_type,
            defaults={
                "distance_m": round(distance, 0),
                "poi_name": layer.name,
                "score": score,
            },
        )
        results.append(prox)

    return results


def _analyze_simulated_proximity(parcelle, centroid):
    """Simulation réaliste de proximité pour Abidjan."""
    from analysis.models import ProximityAnalysis
    import random

    # Seed basé sur la position pour des résultats reproductibles
    seed = int(abs(centroid.x * 1000 + centroid.y * 1000)) % (2 ** 31)
    rng = random.Random(seed)

    poi_configs = {
        "road": {"name": "Route nationale A100", "base": 200, "var": 800},
        "electricity": {"name": "Poste transformateur", "base": 100, "var": 500},
        "water": {"name": "Réseau ADE", "base": 50, "var": 400},
        "school": {"name": "Groupe scolaire", "base": 500, "var": 2000},
        "hospital": {"name": "Centre de santé", "base": 800, "var": 3000},
        "market": {"name": "Marché local", "base": 300, "var": 1500},
        "transport": {"name": "Gare routière", "base": 400, "var": 2000},
        "police": {"name": "Commissariat", "base": 600, "var": 2500},
    }

    results = []
    for poi_type, config in poi_configs.items():
        distance = config["base"] + rng.random() * config["var"]
        score = _distance_to_score(distance, poi_type)

        # Générer un point POI simulé
        angle = rng.random() * 2 * math.pi
        offset_deg = distance / 111320
        poi_point = Point(
            centroid.x + offset_deg * math.cos(angle),
            centroid.y + offset_deg * math.sin(angle),
            srid=4326,
        )

        prox, _ = ProximityAnalysis.objects.update_or_create(
            parcelle=parcelle,
            poi_type=poi_type,
            defaults={
                "distance_m": round(distance, 0),
                "poi_name": config["name"],
                "poi_location": poi_point,
                "score": score,
            },
        )
        results.append(prox)

    return results


def _distance_to_score(distance_m, poi_type):
    """Convertit une distance en score (0-100).
    Thresholds adaptés au type de POI.
    """
    thresholds = {
        "road": {"excellent": 100, "good": 300, "ok": 500, "max": 2000},
        "electricity": {"excellent": 50, "good": 200, "ok": 400, "max": 1500},
        "water": {"excellent": 50, "good": 150, "ok": 300, "max": 1000},
        "school": {"excellent": 500, "good": 1000, "ok": 2000, "max": 5000},
        "hospital": {"excellent": 1000, "good": 2000, "ok": 3000, "max": 8000},
        "market": {"excellent": 300, "good": 800, "ok": 1500, "max": 4000},
        "transport": {"excellent": 300, "good": 800, "ok": 1500, "max": 5000},
        "police": {"excellent": 500, "good": 1500, "ok": 3000, "max": 8000},
    }
    t = thresholds.get(poi_type, {"excellent": 200, "good": 500, "ok": 1000, "max": 3000})

    if distance_m <= t["excellent"]:
        return 100
    if distance_m <= t["good"]:
        return round(100 - (distance_m - t["excellent"]) / (t["good"] - t["excellent"]) * 20, 1)
    if distance_m <= t["ok"]:
        return round(80 - (distance_m - t["good"]) / (t["ok"] - t["good"]) * 30, 1)
    if distance_m <= t["max"]:
        return round(50 - (distance_m - t["ok"]) / (t["max"] - t["ok"]) * 40, 1)
    return max(0, round(10 - (distance_m - t["max"]) / t["max"] * 10, 1))


# ═══════════════════════════════════════════════════════════
# ÉVALUATION GLOBALE DES RISQUES
# ═══════════════════════════════════════════════════════════

def compute_risk_assessment(parcelle):
    """Synthétise toutes les analyses en une évaluation globale.

    Returns:
        RiskAssessment instance (saved)
    """
    from analysis.models import (
        TerrainAnalysis, SpatialConstraint,
        ProximityAnalysis, RiskAssessment,
    )

    assessment, _ = RiskAssessment.objects.update_or_create(
        parcelle=parcelle,
        defaults={},
    )

    # ── Terrain ──
    try:
        terrain = parcelle.terrain_analysis
    except TerrainAnalysis.DoesNotExist:
        terrain = analyze_terrain(parcelle)

    # ── Contraintes ──
    constraints = list(parcelle.spatial_constraints.all())
    if not constraints:
        constraints = analyze_spatial_constraints(parcelle)

    # ── Proximité ──
    proximities = list(parcelle.proximity_analyses.all())
    if not proximities:
        proximities = analyze_proximity(parcelle)

    # ═══ Calculer les risques individuels ═══
    assessment.slope_risk = _slope_to_risk(terrain.slope_mean or 0)
    assessment.flood_risk = _constraint_risk(constraints, "flood_zone")
    assessment.erosion_risk = _constraint_risk(constraints, "erosion")
    assessment.legal_risk = _legal_risk(constraints)

    # ═══ Calculer les 5 axes du radar ═══

    # 1. Accessibilité (basée sur proximité)
    prox_scores = [p.score for p in proximities if p.score is not None]
    assessment.score_accessibility = round(
        (sum(prox_scores) / max(len(prox_scores), 1)) / 20, 1
    )  # 0-100 → 0-5

    # 2. Topographie
    tech_score = terrain.technical_score or 50
    assessment.score_topography = round(tech_score / 20, 1)

    # 3. Juridique (inversé : plus de contraintes = pire)
    critical_count = sum(1 for c in constraints if c.severity == "critical")
    warning_count = sum(1 for c in constraints if c.severity == "warning")
    legal_penalty = critical_count * 1.5 + warning_count * 0.5
    assessment.score_legal = round(max(0, min(5, 5 - legal_penalty)), 1)

    # 4. Environnement
    drainage_scores = {"excellent": 5, "bon": 4, "moyen": 2.5, "mauvais": 1}
    drainage = terrain.drainage_quality or "moyen"
    env_score = drainage_scores.get(drainage, 2.5)
    water_penalty = (terrain.water_accumulation_risk or 0) / 50
    assessment.score_environment = round(max(0, min(5, env_score - water_penalty)), 1)

    # 5. Prix (rapport prix/marché local)
    assessment.score_price = _compute_price_score(parcelle)

    # ═══ Score global ═══
    axes = [
        assessment.score_accessibility,
        assessment.score_topography,
        assessment.score_legal,
        assessment.score_environment,
        assessment.score_price,
    ]
    assessment.overall_score = round(sum(axes) / 5 * 20, 1)  # 0-5 → 0-100
    assessment.overall_risk = _score_to_risk_level(assessment.overall_score)

    # ═══ Conclusion IA ═══
    assessment.ai_conclusion = _generate_ai_conclusion(assessment, terrain, constraints)
    assessment.recommendation = _generate_recommendation(assessment)

    assessment.save()
    return assessment


def _slope_to_risk(slope):
    if slope > 25:
        return "critical"
    if slope > 15:
        return "high"
    if slope > 10:
        return "medium"
    return "low"


def _constraint_risk(constraints, constraint_type):
    matching = [c for c in constraints if c.constraint_type == constraint_type]
    if not matching:
        return "low"
    max_severity = max(c.severity for c in matching)
    return {"critical": "critical", "warning": "high", "info": "medium"}.get(max_severity, "low")


def _legal_risk(constraints):
    legal_types = {"power_line", "pipeline", "green_zone", "road_setback", "heritage"}
    legal = [c for c in constraints if c.constraint_type in legal_types]
    if not legal:
        return "low"
    if any(c.severity == "critical" for c in legal):
        return "critical"
    if any(c.severity == "warning" for c in legal):
        return "high"
    return "medium"


def _compute_price_score(parcelle):
    """Score prix par rapport au marché local (0-5)."""
    from parcelles.models import Parcelle

    if not parcelle.price_per_m2:
        return 3.0

    # Moyenne du marché dans la même zone
    zone_prices = Parcelle.objects.filter(
        zone=parcelle.zone,
        status="disponible",
        price_per_m2__isnull=False,
    ).exclude(pk=parcelle.pk).values_list("price_per_m2", flat=True)

    if not zone_prices:
        return 3.0

    avg_price = sum(float(p) for p in zone_prices) / len(zone_prices)
    ratio = float(parcelle.price_per_m2) / max(avg_price, 1)

    # ratio < 0.9 = bon prix, ratio > 1.1 = cher
    if ratio < 0.8:
        return 5.0
    if ratio < 0.9:
        return 4.5
    if ratio < 1.0:
        return 4.0
    if ratio < 1.1:
        return 3.0
    if ratio < 1.3:
        return 2.0
    return 1.0


def _score_to_risk_level(score):
    if score >= 75:
        return "low"
    if score >= 55:
        return "medium"
    if score >= 35:
        return "high"
    return "critical"


def _generate_ai_conclusion(assessment, terrain, constraints):
    """Génère une conclusion textuelle basée sur l'analyse."""
    parts = []

    # Topographie
    slope = terrain.slope_mean or 0
    if slope < 5:
        parts.append("Terrain plat, idéal pour la construction")
    elif slope < 15:
        parts.append("Pente modérée, construction possible avec aménagement léger")
    else:
        parts.append("Forte pente nécessitant des travaux de terrassement importants")

    # Contraintes
    critical_constraints = [c for c in constraints if c.severity == "critical"]
    if critical_constraints:
        types = [c.get_constraint_type_display() for c in critical_constraints]
        parts.append(
            "ATTENTION : Contraintes critiques détectées ({})".format(
                ", ".join(types)
            )
        )
    elif not constraints:
        parts.append("Aucune contrainte spatiale détectée")

    # Drainage
    if terrain.drainage_quality in ("excellent", "bon"):
        parts.append("Bon drainage naturel")
    elif terrain.drainage_quality == "mauvais":
        parts.append("Drainage insuffisant — risque de stagnation d'eau")

    # Score global
    score = assessment.overall_score or 0
    if score >= 75:
        parts.append("Verdict : Terrain de qualité supérieure pour investissement")
    elif score >= 55:
        parts.append("Verdict : Terrain acceptable avec quelques points de vigilance")
    else:
        parts.append("Verdict : Terrain présentant des risques significatifs")

    return ". ".join(parts) + "."


def _generate_recommendation(assessment):
    score = assessment.overall_score or 0
    if score >= 80:
        return "ideal"
    if score >= 65:
        return "good"
    if score >= 45:
        return "caution"
    if score >= 25:
        return "risky"
    return "no_go"


# ═══════════════════════════════════════════════════════════
# PIPELINE COMPLET — analyse_parcelle_complete
# ═══════════════════════════════════════════════════════════

def analyze_parcelle_complete(parcelle, dem_path=None):
    """Lance l'analyse complète d'une parcelle (les 3 étapes).

    Returns:
        dict avec terrain, constraints, proximities, risk_assessment
    """
    logger.info("=== Analyse complète de %s ===", parcelle.lot_number)

    terrain = analyze_terrain(parcelle, dem_path)
    constraints = analyze_spatial_constraints(parcelle)
    proximities = analyze_proximity(parcelle)
    risk = compute_risk_assessment(parcelle)

    # ── Synchroniser vers ParcelleAnalysis (module parcelles) ──
    _sync_to_parcelle_analysis(parcelle, terrain, risk, constraints)

    return {
        "terrain": terrain,
        "constraints": constraints,
        "proximities": proximities,
        "risk_assessment": risk,
    }


def _sync_to_parcelle_analysis(parcelle, terrain, risk, constraints):
    """Pousse les résultats de l'analyse SIG vers ParcelleAnalysis.

    Interconnexion bidirectionnelle :
    - TerrainAnalysis.technical_score → ParcelleAnalysis.score_terrain
    - RiskAssessment infos → ParcelleAnalysis.analysis_report
    - SpatialConstraints → pénalités sur score_overlap
    """
    try:
        from parcelles.models import ParcelleAnalysis

        analysis, created = ParcelleAnalysis.objects.get_or_create(
            parcelle=parcelle,
            defaults={"status": ParcelleAnalysis.AnalysisStatus.IN_PROGRESS},
        )

        # Score terrain depuis le score technique topographique
        if terrain and terrain.technical_score is not None:
            analysis.score_terrain = min(100, max(0, int(terrain.technical_score)))
            analysis.terrain_notes = (
                "Score topographique auto : {}/100\n"
                "Pente moy: {}% | Cat: {} | Drainage: {} | Solaire: {}/100\n"
                "Élévation: {}-{}m (moy {}m) | Source: {}".format(
                    int(terrain.technical_score),
                    terrain.slope_mean or 0,
                    terrain.get_slope_category_display() if terrain.slope_category else "N/A",
                    terrain.drainage_quality or "N/A",
                    int(terrain.solar_potential) if terrain.solar_potential else "N/A",
                    terrain.elevation_min or 0,
                    terrain.elevation_max or 0,
                    terrain.elevation_mean or 0,
                    terrain.dem_source or "N/A",
                )
            )

        # Pénalité contraintes spatiales
        if constraints:
            critical = sum(1 for c in constraints if c.severity == "critical")
            warnings = sum(1 for c in constraints if c.severity == "warning")
            penalty = critical * 15 + warnings * 5
            if analysis.score_overlap > 0:
                analysis.score_overlap = max(0, analysis.score_overlap - penalty)

        # Enrichir le rapport
        report_lines = []
        if risk:
            report_lines.append(
                "[SIG] Risque global: {} — Score: {}/100".format(
                    risk.get_overall_risk_display(),
                    int(risk.overall_score) if risk.overall_score else "N/A",
                )
            )
            if risk.ai_conclusion:
                report_lines.append("[IA] {}".format(risk.ai_conclusion[:300]))
            if risk.recommendation:
                report_lines.append("[Recommandation] {}".format(risk.get_recommendation_display()))

        if constraints:
            for c in constraints:
                report_lines.append(
                    "[Contrainte] {} — {} — {:.0f}% affecté".format(
                        c.get_constraint_type_display(),
                        c.get_severity_display(),
                        c.affected_area_pct or 0,
                    )
                )

        if report_lines:
            existing = analysis.analysis_report or ""
            analysis.analysis_report = (existing + "\n" + "\n".join(report_lines)).strip()

        # Recalculer le score global et sauvegarder
        analysis.compute_overall_score()
        analysis.save()

        logger.info(
            "ParcelleAnalysis synchro ← analysis : lot %s → score %d/100 (%s)",
            parcelle.lot_number, analysis.overall_score, analysis.reliability_grade,
        )

    except ImportError:
        logger.debug("Module parcelles.models.ParcelleAnalysis non disponible")
    except Exception as e:
        logger.warning("Erreur sync vers ParcelleAnalysis: %s", e)
