"""
Générateur de Rapport "État des Lieux" — EYE-FONCIER
Module 3 : Certificat d'Analyse Eye-Foncier (PDF)

Contenu :
  1. En-tête : ID parcelle, coordonnées GPS, QR Code
  2. Carte de situation (image statique)
  3. Radar Chart (5 axes)
  4. Diagnostic des risques
  5. Conclusion IA
"""
import hashlib
import io
import logging
import math
import os
from datetime import datetime

from django.conf import settings
from django.utils import timezone

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor, Color, white, black
from reportlab.lib.units import mm, cm
from reportlab.lib.utils import ImageReader

logger = logging.getLogger("analysis")

WIDTH, HEIGHT = A4  # 595.28 × 841.89 points


def generate_analysis_report(parcelle, requested_by=None):
    """Génère le Certificat d'Analyse Eye-Foncier (PDF).

    Returns:
        AnalysisReport instance avec pdf_file rempli.
    """
    from analysis.models import AnalysisReport, RiskAssessment, TerrainAnalysis
    from analysis.services.terrain_analyzer import analyze_parcelle_complete

    # S'assurer que l'analyse est complète
    try:
        risk = parcelle.risk_assessment
    except RiskAssessment.DoesNotExist:
        result = analyze_parcelle_complete(parcelle)
        risk = result["risk_assessment"]

    try:
        terrain = parcelle.terrain_analysis
    except TerrainAnalysis.DoesNotExist:
        terrain = None

    # Créer le rapport
    report, _ = AnalysisReport.objects.get_or_create(
        parcelle=parcelle,
        requested_by=requested_by,
        defaults={"status": "pending"},
    )

    # QR Code de vérification
    qr_code = hashlib.sha256(
        "{}:{}:{}".format(parcelle.pk, report.pk, timezone.now().isoformat()).encode()
    ).hexdigest()[:16].upper()
    report.qr_verification_code = qr_code

    try:
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)

        # ═══ PAGE 1 ═══
        _draw_header(p, parcelle, qr_code)
        y = HEIGHT - 140

        # Infos parcelle
        y = _draw_parcelle_info(p, parcelle, y)

        # Radar Chart
        y = _draw_radar_chart(p, risk, y)

        # Diagnostic des risques
        y = _draw_risk_diagnostic(p, risk, terrain, y)

        # ═══ PAGE 2 ═══
        p.showPage()
        _draw_header_light(p, parcelle)
        y = HEIGHT - 80

        # Détails topographiques
        y = _draw_terrain_details(p, terrain, y)

        # Analyse de proximité
        y = _draw_proximity_details(p, parcelle, y)

        # Contraintes spatiales
        y = _draw_constraints_details(p, parcelle, y)

        # Conclusion IA
        y = _draw_conclusion(p, risk, y)

        # Pied de page
        _draw_footer(p, qr_code)

        p.save()

        # Sauvegarder le PDF
        from django.core.files.base import ContentFile
        pdf_content = buffer.getvalue()
        filename = "Analyse_EYF_{}_{}.pdf".format(
            parcelle.lot_number.replace(" ", "_"),
            timezone.now().strftime("%Y%m%d"),
        )
        report.pdf_file.save(filename, ContentFile(pdf_content), save=False)
        report.status = "ready"
        report.generated_at = timezone.now()

        # Snapshot des données (fusion analysis + parcelles.ParcelleAnalysis)
        snapshot = {
            "overall_score": risk.overall_score,
            "overall_risk": risk.overall_risk,
            "radar": risk.radar_data,
            "ai_conclusion": risk.ai_conclusion,
            "recommendation": risk.recommendation,
            "terrain": {
                "slope_mean": terrain.slope_mean if terrain else None,
                "elevation_mean": terrain.elevation_mean if terrain else None,
                "technical_score": terrain.technical_score if terrain else None,
            },
            "generated_at": timezone.now().isoformat(),
        }

        # Intégrer les données ParcelleAnalysis (analyse foncière)
        try:
            foncier = parcelle.analysis
            snapshot["foncier"] = {
                "overall_score": foncier.overall_score,
                "grade": foncier.reliability_grade,
                "label": foncier.reliability_label,
                "score_geometry": foncier.score_geometry,
                "score_documents": foncier.score_documents,
                "score_overlap": foncier.score_overlap,
                "score_terrain": foncier.score_terrain,
                "score_ownership": foncier.score_ownership,
                "has_overlap": foncier.has_overlap,
                "has_titre_foncier": foncier.has_titre_foncier,
                "has_attestation": foncier.has_attestation,
                "terrain_inspected": foncier.terrain_inspected,
                "status": foncier.status,
            }
        except Exception:
            snapshot["foncier"] = None

        report.snapshot_data = snapshot
        report.save()

        logger.info("Rapport généré: %s — %s", parcelle.lot_number, filename)
        return report

    except Exception as e:
        logger.error("Erreur génération rapport: %s", e, exc_info=True)
        report.status = "error"
        report.save()
        raise


# ═══════════════════════════════════════════════════════════
# COMPOSANTS PDF
# ═══════════════════════════════════════════════════════════

def _draw_header(p, parcelle, qr_code):
    """En-tête principal avec bannière verte EYE-FONCIER."""
    # Bannière
    p.setFillColor(HexColor("#166534"))
    p.rect(0, HEIGHT - 100, WIDTH, 100, fill=True, stroke=False)

    # Logo texte
    p.setFillColor(white)
    p.setFont("Helvetica-Bold", 24)
    p.drawString(30, HEIGHT - 45, "EYE-FONCIER")
    p.setFont("Helvetica", 10)
    p.drawString(30, HEIGHT - 62, "Certificat d'Analyse Foncière")

    # Référence
    p.setFont("Helvetica-Bold", 12)
    p.drawRightString(WIDTH - 30, HEIGHT - 40, "Lot {}".format(parcelle.lot_number))
    p.setFont("Helvetica", 9)
    p.drawRightString(WIDTH - 30, HEIGHT - 55, "Réf: {}".format(qr_code))
    p.drawRightString(
        WIDTH - 30, HEIGHT - 68,
        "Date: {}".format(timezone.now().strftime("%d/%m/%Y")),
    )

    # Coordonnées GPS
    if parcelle.centroid:
        p.setFont("Helvetica", 8)
        p.drawRightString(
            WIDTH - 30, HEIGHT - 82,
            "GPS: {:.6f}, {:.6f}".format(parcelle.centroid.y, parcelle.centroid.x),
        )

    # Ligne séparatrice
    p.setStrokeColor(HexColor("#22c55e"))
    p.setLineWidth(3)
    p.line(0, HEIGHT - 102, WIDTH, HEIGHT - 102)


def _draw_header_light(p, parcelle):
    """En-tête léger pour les pages suivantes."""
    p.setFillColor(HexColor("#f0fdf4"))
    p.rect(0, HEIGHT - 55, WIDTH, 55, fill=True, stroke=False)
    p.setFillColor(HexColor("#166534"))
    p.setFont("Helvetica-Bold", 14)
    p.drawString(30, HEIGHT - 35, "EYE-FONCIER — Analyse détaillée")
    p.setFont("Helvetica", 9)
    p.setFillColor(HexColor("#6b7280"))
    p.drawRightString(WIDTH - 30, HEIGHT - 35, "Lot {}".format(parcelle.lot_number))
    p.setStrokeColor(HexColor("#22c55e"))
    p.setLineWidth(2)
    p.line(0, HEIGHT - 57, WIDTH, HEIGHT - 57)


def _draw_parcelle_info(p, parcelle, y):
    """Informations principales de la parcelle."""
    p.setFont("Helvetica-Bold", 13)
    p.setFillColor(HexColor("#166534"))
    p.drawString(30, y, "INFORMATIONS PARCELLE")
    y -= 20

    infos = [
        ("Titre", parcelle.title),
        ("Lot", parcelle.lot_number),
        ("Zone", str(parcelle.zone) if parcelle.zone else "—"),
        ("Type", parcelle.get_land_type_display()),
        ("Surface", "{:,.2f} m²".format(float(parcelle.surface_m2)) if parcelle.surface_m2 else "—"),
        ("Prix", "{:,.0f} FCFA".format(float(parcelle.price)) if parcelle.price else "—"),
        ("Adresse", parcelle.address or "—"),
        ("Propriétaire", parcelle.owner.get_full_name() if parcelle.owner else "—"),
        ("Validé géomètre", "Oui" if parcelle.is_validated else "Non"),
        ("Badge confiance", "Oui" if parcelle.trust_badge else "Non"),
    ]

    for label, value in infos:
        p.setFont("Helvetica-Bold", 9)
        p.setFillColor(HexColor("#6b7280"))
        p.drawString(40, y, "{} :".format(label))
        p.setFont("Helvetica", 9)
        p.setFillColor(HexColor("#1e293b"))
        p.drawString(160, y, str(value)[:60])
        y -= 14

    return y - 10


def _draw_radar_chart(p, risk, y):
    """Dessine un radar chart (pentagonal) des 5 axes."""
    p.setFont("Helvetica-Bold", 13)
    p.setFillColor(HexColor("#166534"))
    p.drawString(30, y, "PROFIL DE LA PARCELLE")
    y -= 15

    # Centre du radar
    cx, cy = 170, y - 90
    radius = 75
    axes = [
        ("Accessibilité", risk.score_accessibility),
        ("Topographie", risk.score_topography),
        ("Juridique", risk.score_legal),
        ("Environnement", risk.score_environment),
        ("Prix", risk.score_price),
    ]
    n = len(axes)

    # Grille de fond (cercles concentriques)
    for level in [1, 2, 3, 4, 5]:
        r = radius * level / 5
        p.setStrokeColor(HexColor("#e2e8f0"))
        p.setLineWidth(0.5)
        points = []
        for i in range(n):
            angle = math.pi / 2 + 2 * math.pi * i / n
            px = cx + r * math.cos(angle)
            py = cy + r * math.sin(angle)
            points.append((px, py))
        # Dessiner le polygone de grille
        path = p.beginPath()
        path.moveTo(points[0][0], points[0][1])
        for px, py in points[1:]:
            path.lineTo(px, py)
        path.close()
        p.drawPath(path, stroke=True, fill=False)

    # Axes
    for i in range(n):
        angle = math.pi / 2 + 2 * math.pi * i / n
        ex = cx + radius * math.cos(angle)
        ey = cy + radius * math.sin(angle)
        p.setStrokeColor(HexColor("#cbd5e1"))
        p.setLineWidth(0.5)
        p.line(cx, cy, ex, ey)

        # Labels
        lx = cx + (radius + 15) * math.cos(angle)
        ly = cy + (radius + 15) * math.sin(angle)
        p.setFont("Helvetica", 7)
        p.setFillColor(HexColor("#475569"))
        label = "{} ({:.1f})".format(axes[i][0], axes[i][1])
        p.drawCentredString(lx, ly - 3, label)

    # Polygone des valeurs
    value_points = []
    for i in range(n):
        angle = math.pi / 2 + 2 * math.pi * i / n
        val = axes[i][1] / 5 * radius
        px = cx + val * math.cos(angle)
        py = cy + val * math.sin(angle)
        value_points.append((px, py))

    # Remplissage semi-transparent
    p.setFillColor(Color(0.133, 0.545, 0.133, alpha=0.25))
    p.setStrokeColor(HexColor("#22c55e"))
    p.setLineWidth(2)
    path = p.beginPath()
    path.moveTo(value_points[0][0], value_points[0][1])
    for px, py in value_points[1:]:
        path.lineTo(px, py)
    path.close()
    p.drawPath(path, stroke=True, fill=True)

    # Points
    for px, py in value_points:
        p.setFillColor(HexColor("#166534"))
        p.circle(px, py, 3, fill=True, stroke=False)

    # Score global à droite
    score = risk.overall_score or 0
    score_x = 370
    score_y = y - 30

    # Cercle de score
    score_color = _score_color(score)
    p.setFillColor(HexColor(score_color))
    p.circle(score_x + 50, score_y - 30, 40, fill=True, stroke=False)
    p.setFillColor(white)
    p.setFont("Helvetica-Bold", 28)
    p.drawCentredString(score_x + 50, score_y - 40, "{:.0f}".format(score))
    p.setFont("Helvetica", 10)
    p.drawCentredString(score_x + 50, score_y - 55, "/ 100")

    # Recommandation
    rec_labels = {
        "ideal": ("Idéal", "#16a34a"),
        "good": ("Bon", "#22c55e"),
        "caution": ("Prudence", "#f59e0b"),
        "risky": ("Risqué", "#ef4444"),
        "no_go": ("Déconseillé", "#dc2626"),
    }
    rec = risk.recommendation or "caution"
    rec_text, rec_color = rec_labels.get(rec, ("—", "#6b7280"))
    p.setFillColor(HexColor(rec_color))
    p.setFont("Helvetica-Bold", 14)
    p.drawCentredString(score_x + 50, score_y - 85, rec_text)

    # Détails des risques à droite
    risk_y = score_y - 110
    risks = [
        ("Inondation", risk.flood_risk),
        ("Érosion", risk.erosion_risk),
        ("Pente", risk.slope_risk),
        ("Juridique", risk.legal_risk),
    ]
    p.setFont("Helvetica-Bold", 9)
    p.setFillColor(HexColor("#475569"))
    p.drawString(score_x, risk_y, "Risques :")
    risk_y -= 15

    for label, level in risks:
        risk_colors = {
            "low": "#22c55e", "medium": "#f59e0b",
            "high": "#ef4444", "critical": "#dc2626",
        }
        risk_labels = {
            "low": "Faible", "medium": "Moyen",
            "high": "Élevé", "critical": "Critique",
        }
        color = risk_colors.get(level, "#6b7280")
        p.setFillColor(HexColor(color))
        p.circle(score_x + 5, risk_y + 3, 4, fill=True, stroke=False)
        p.setFillColor(HexColor("#1e293b"))
        p.setFont("Helvetica", 8)
        p.drawString(score_x + 15, risk_y, "{} : {}".format(label, risk_labels.get(level, "—")))
        risk_y -= 13

    return y - 200


def _draw_risk_diagnostic(p, risk, terrain, y):
    """Section diagnostic des risques."""
    if y < 100:
        p.showPage()
        y = HEIGHT - 60

    p.setFont("Helvetica-Bold", 13)
    p.setFillColor(HexColor("#166534"))
    p.drawString(30, y, "DIAGNOSTIC RAPIDE")
    y -= 18

    diags = []
    if terrain:
        slope = terrain.slope_mean or 0
        if slope < 5:
            diags.append(("Terrain plat", "Construction standard possible", "#22c55e"))
        elif slope < 15:
            diags.append(("Pente modérée", "Fondations adaptées nécessaires", "#f59e0b"))
        else:
            diags.append(("Forte pente", "Terrassement important requis", "#ef4444"))

        if terrain.drainage_quality == "mauvais":
            diags.append(("Drainage", "Risque de stagnation d'eau", "#ef4444"))
        elif terrain.drainage_quality in ("excellent", "bon"):
            diags.append(("Drainage", "Bon écoulement naturel", "#22c55e"))

    if risk.flood_risk in ("high", "critical"):
        diags.append(("Zone inondable", "ATTENTION — Zone à risque", "#dc2626"))
    else:
        diags.append(("Zone inondable", "Hors zone inondable", "#22c55e"))

    for label, desc, color in diags:
        p.setFillColor(HexColor(color))
        p.circle(43, y + 3, 4, fill=True, stroke=False)
        p.setFont("Helvetica-Bold", 9)
        p.setFillColor(HexColor("#1e293b"))
        p.drawString(55, y, label)
        p.setFont("Helvetica", 9)
        p.setFillColor(HexColor("#6b7280"))
        p.drawString(170, y, desc)
        y -= 15

    return y - 10


def _draw_terrain_details(p, terrain, y):
    """Détails topographiques."""
    p.setFont("Helvetica-Bold", 13)
    p.setFillColor(HexColor("#166534"))
    p.drawString(30, y, "ANALYSE TOPOGRAPHIQUE")
    y -= 20

    if not terrain:
        p.setFont("Helvetica-Oblique", 10)
        p.setFillColor(HexColor("#6b7280"))
        p.drawString(40, y, "Analyse non disponible")
        return y - 20

    details = [
        ("Altitude moyenne", "{:.1f} m".format(terrain.elevation_mean or 0)),
        ("Dénivelé", "{:.1f} m".format(terrain.elevation_range or 0)),
        ("Pente moyenne", "{:.1f} %".format(terrain.slope_mean or 0)),
        ("Pente maximale", "{:.1f} %".format(terrain.slope_max or 0)),
        ("Catégorie", terrain.get_slope_category_display() if terrain.slope_category else "—"),
        ("Constructible (pente)", "Oui" if terrain.slope_is_constructible else "Non — Pente > 15%"),
        ("Exposition", terrain.get_aspect_dominant_display() if terrain.aspect_dominant else "—"),
        ("Potentiel solaire", "{:.0f}/100".format(terrain.solar_potential or 0)),
        ("Risque accumulation eau", "{:.0f}/100".format(terrain.water_accumulation_risk or 0)),
        ("Drainage", terrain.get_drainage_quality_display() if terrain.drainage_quality else "—"),
        ("Score technique", "{:.0f}/100".format(terrain.technical_score or 0)),
        ("Source MNT", terrain.dem_source or "—"),
    ]

    for label, value in details:
        p.setFont("Helvetica-Bold", 8)
        p.setFillColor(HexColor("#6b7280"))
        p.drawString(40, y, label)
        p.setFont("Helvetica", 8)
        p.setFillColor(HexColor("#1e293b"))
        p.drawString(200, y, str(value))
        y -= 13

    return y - 15


def _draw_proximity_details(p, parcelle, y):
    """Détails de proximité aux infrastructures."""
    if y < 200:
        p.showPage()
        _draw_header_light(p, parcelle)
        y = HEIGHT - 80

    p.setFont("Helvetica-Bold", 13)
    p.setFillColor(HexColor("#166534"))
    p.drawString(30, y, "ANALYSE DE PROXIMITÉ")
    y -= 20

    proximities = parcelle.proximity_analyses.all()
    if not proximities:
        p.setFont("Helvetica-Oblique", 10)
        p.setFillColor(HexColor("#6b7280"))
        p.drawString(40, y, "Analyse non disponible")
        return y - 20

    # En-tête tableau
    p.setFont("Helvetica-Bold", 8)
    p.setFillColor(HexColor("#166534"))
    p.drawString(40, y, "Infrastructure")
    p.drawString(200, y, "Distance")
    p.drawString(300, y, "Score")
    p.drawString(370, y, "Point le plus proche")
    y -= 3
    p.setStrokeColor(HexColor("#e2e8f0"))
    p.setLineWidth(0.5)
    p.line(40, y, WIDTH - 30, y)
    y -= 12

    for prox in proximities:
        dist_str = "{:,.0f} m".format(prox.distance_m) if prox.distance_m else "—"
        score_str = "{:.0f}/100".format(prox.score) if prox.score else "—"
        score_val = prox.score or 0

        # Indicateur couleur
        if score_val >= 70:
            color = "#22c55e"
        elif score_val >= 40:
            color = "#f59e0b"
        else:
            color = "#ef4444"

        p.setFillColor(HexColor(color))
        p.circle(35, y + 3, 3, fill=True, stroke=False)

        p.setFont("Helvetica", 8)
        p.setFillColor(HexColor("#1e293b"))
        p.drawString(40, y, prox.get_poi_type_display())
        p.drawString(200, y, dist_str)
        p.drawString(300, y, score_str)
        p.setFillColor(HexColor("#6b7280"))
        p.drawString(370, y, (prox.poi_name or "—")[:30])
        y -= 12

    return y - 15


def _draw_constraints_details(p, parcelle, y):
    """Détails des contraintes spatiales."""
    if y < 150:
        p.showPage()
        _draw_header_light(p, parcelle)
        y = HEIGHT - 80

    p.setFont("Helvetica-Bold", 13)
    p.setFillColor(HexColor("#166534"))
    p.drawString(30, y, "CONTRAINTES SPATIALES")
    y -= 20

    constraints = parcelle.spatial_constraints.all()
    if not constraints:
        p.setFillColor(HexColor("#22c55e"))
        p.circle(43, y + 3, 4, fill=True, stroke=False)
        p.setFont("Helvetica", 10)
        p.setFillColor(HexColor("#1e293b"))
        p.drawString(55, y, "Aucune contrainte spatiale détectée")
        return y - 25

    for c in constraints:
        sev_colors = {"info": "#3b82f6", "warning": "#f59e0b", "critical": "#ef4444"}
        color = sev_colors.get(c.severity, "#6b7280")

        p.setFillColor(HexColor(color))
        p.circle(43, y + 3, 4, fill=True, stroke=False)

        p.setFont("Helvetica-Bold", 8)
        p.setFillColor(HexColor("#1e293b"))
        p.drawString(55, y, c.get_constraint_type_display())

        p.setFont("Helvetica", 8)
        p.setFillColor(HexColor("#6b7280"))
        sev_text = c.get_severity_display()
        area_text = " — {:.1f}% affecté".format(c.affected_area_pct) if c.affected_area_pct else ""
        p.drawString(200, y, "{}{}".format(sev_text, area_text))
        y -= 12

    return y - 15


def _draw_conclusion(p, risk, y):
    """Conclusion IA avec encadré."""
    if y < 180:
        return y

    p.setFont("Helvetica-Bold", 13)
    p.setFillColor(HexColor("#166534"))
    p.drawString(30, y, "CONCLUSION")
    y -= 20

    # Encadré de conclusion
    conclusion = risk.ai_conclusion or "Analyse non disponible."
    box_height = max(60, len(conclusion) // 60 * 14 + 40)

    p.setFillColor(HexColor("#f0fdf4"))
    p.setStrokeColor(HexColor("#22c55e"))
    p.setLineWidth(1.5)
    p.roundRect(30, y - box_height, WIDTH - 60, box_height, 8, fill=True, stroke=True)

    # Texte de conclusion (word wrap)
    p.setFont("Helvetica", 9)
    p.setFillColor(HexColor("#1e293b"))
    text_y = y - 15
    words = conclusion.split()
    line = ""
    for word in words:
        test = "{} {}".format(line, word).strip()
        if p.stringWidth(test, "Helvetica", 9) < WIDTH - 100:
            line = test
        else:
            p.drawString(45, text_y, line)
            text_y -= 13
            line = word
    if line:
        p.drawString(45, text_y, line)

    return y - box_height - 20


def _draw_footer(p, qr_code):
    """Pied de page avec mentions légales."""
    p.setFillColor(HexColor("#f8fafc"))
    p.rect(0, 0, WIDTH, 50, fill=True, stroke=False)
    p.setStrokeColor(HexColor("#e2e8f0"))
    p.setLineWidth(0.5)
    p.line(0, 50, WIDTH, 50)

    p.setFont("Helvetica", 7)
    p.setFillColor(HexColor("#6b7280"))
    p.drawString(
        30, 30,
        "Certificat d'Analyse EYE-FONCIER — Réf: {} — Généré le {}".format(
            qr_code, timezone.now().strftime("%d/%m/%Y à %H:%M"),
        ),
    )
    p.drawString(
        30, 18,
        "Ce document est une analyse indicative. Il ne remplace pas une expertise foncière officielle.",
    )
    p.drawString(
        30, 7,
        "EYE-FONCIER — Plateforme WebSIG de Transaction Foncière Sécurisée — www.eye-foncier.ci",
    )


def _score_color(score):
    """Couleur selon le score."""
    if score >= 75:
        return "#16a34a"
    if score >= 55:
        return "#22c55e"
    if score >= 35:
        return "#f59e0b"
    return "#ef4444"
