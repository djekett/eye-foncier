"""
Vues du coffre-fort documentaire — EYE-FONCIER
Phase 3 : Génération PDF corrigée avec contenu réel des documents et miniatures.
"""
import io
import hashlib
import os
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, Http404
from django.utils import timezone
from django.conf import settings

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import Color, HexColor
from reportlab.lib.units import mm, cm
from reportlab.lib.utils import ImageReader

try:
    from PyPDF2 import PdfReader, PdfWriter
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False

from django.db import models
from .models import ParcelleDocument, DocumentAccessLog
from .forms import DocumentUploadForm
from accounts.models import AccessLog


@login_required
def document_list_view(request, parcelle_pk):
    """Liste des documents d'une parcelle.

    Accès aux documents filigranés conditionné par la cotation :
      - Public : visible par tous
      - Buyer-only : acheteur avec cotation validée uniquement
      - Private : admin / propriétaire seulement
    """
    from parcelles.models import Parcelle
    parcelle = get_object_or_404(Parcelle, pk=parcelle_pk)

    user = request.user
    docs = ParcelleDocument.objects.filter(parcelle=parcelle)

    # Vérifier si l'acheteur a une cotation validée
    has_cotation = False
    cotation = None
    if user.is_acheteur:
        from transactions.cotation_service import check_cotation_access
        cotation = check_cotation_access(user, parcelle)
        has_cotation = cotation is not None and cotation.is_valid

    # Filtrage selon le rôle ET la cotation
    if user.is_admin_role or user.is_geometre or parcelle.owner == user:
        pass  # Voir tout
    elif user.is_acheteur and has_cotation:
        # Cotation payée → accès aux docs buyer_only (filigranés)
        docs = docs.exclude(confidentiality="private")
    elif user.is_acheteur and not has_cotation:
        # Pas de cotation → seulement les docs publics
        docs = docs.filter(confidentiality="public")
    else:
        docs = docs.filter(confidentiality="public")

    return render(request, "documents/document_list.html", {
        "parcelle": parcelle,
        "documents": docs,
        "is_owner": parcelle.owner == request.user or request.user.is_staff,
        "has_cotation": has_cotation,
        "cotation": cotation,
    })


@login_required
def document_upload_view(request, parcelle_pk):
    """Upload sécurisé d'un document."""
    from parcelles.models import Parcelle
    parcelle = get_object_or_404(Parcelle, pk=parcelle_pk)

    if parcelle.owner != request.user and not request.user.is_admin_role:
        messages.error(request, "Non autorisé.")
        return redirect("parcelles:detail", pk=parcelle_pk)

    if request.method == "POST":
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.parcelle = parcelle
            doc.uploaded_by = request.user

            # Calcul du hash SHA-256
            file_content = doc.file.read()
            doc.file_hash = hashlib.sha256(file_content).hexdigest()
            doc.file.seek(0)

            doc.save()

            AccessLog.objects.create(
                user=request.user,
                action=AccessLog.ActionType.UPLOAD,
                resource_type="ParcelleDocument",
                resource_id=str(doc.pk),
            )

            messages.success(request, "Document uploadé et sécurisé avec succès.")
            return redirect("documents:list", parcelle_pk=parcelle_pk)
    else:
        form = DocumentUploadForm()

    return render(request, "documents/document_upload.html", {
        "form": form,
        "parcelle": parcelle,
    })


def _get_file_absolute_path(file_field):
    """Retourne le chemin absolu d'un FileField. Gère MEDIA_ROOT correctement."""
    if not file_field:
        return None
    try:
        file_path = file_field.path
        if os.path.isfile(file_path):
            return file_path
    except (ValueError, NotImplementedError):
        pass

    # Fallback : construire le chemin depuis MEDIA_ROOT
    try:
        media_root = getattr(settings, "MEDIA_ROOT", "")
        relative = str(file_field)
        full_path = os.path.join(media_root, relative)
        if os.path.isfile(full_path):
            return full_path
    except Exception:
        pass

    return None


def _is_image_file(file_path):
    """Vérifie si un fichier est une image supportée par ReportLab."""
    if not file_path:
        return False
    ext = os.path.splitext(file_path)[1].lower()
    return ext in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif")


def _draw_watermark(p, width, height, watermark_text, font_size=None, opacity=None):
    """Dessine un watermark en diagonale sur la page."""
    font_size = font_size or getattr(settings, "WATERMARK_FONT_SIZE", 24)
    opacity = opacity or getattr(settings, "WATERMARK_OPACITY", 0.3)

    p.saveState()
    p.setFont("Helvetica", font_size)
    p.setFillColor(Color(0.8, 0.1, 0.1, alpha=opacity))
    p.translate(width / 2, height / 2)
    p.rotate(45)
    p.drawCentredString(0, 0, watermark_text)
    p.restoreState()


def _draw_header(p, width, height, y_start):
    """Dessine l'en-tête EYE-FONCIER avec logo si disponible."""
    # Logo
    logo_path = os.path.join(settings.BASE_DIR, "static", "img", "logo.png")
    if not os.path.isfile(logo_path):
        logo_path = os.path.join(settings.BASE_DIR, "logo.png")

    x = 40
    y = y_start

    if os.path.isfile(logo_path):
        try:
            img = ImageReader(logo_path)
            p.drawImage(img, x, y - 35, width=35, height=35, preserveAspectRatio=True, mask="auto")
            x += 42
        except Exception:
            pass

    p.setFont("Helvetica-Bold", 16)
    p.setFillColor(HexColor("#16a34a"))
    p.drawString(x, y - 15, "EYE-FONCIER")
    p.setFont("Helvetica", 8)
    p.setFillColor(HexColor("#6b7280"))
    p.drawString(x, y - 28, "Plateforme WebSIG de Transaction Foncière Sécurisée")

    # Ligne de séparation
    p.setStrokeColor(HexColor("#22c55e"))
    p.setLineWidth(2)
    p.line(40, y - 42, width - 40, y - 42)

    return y - 60


@login_required
def document_view_watermarked(request, pk):
    """
    Consultation de document avec watermark dynamique.
    CORRIGÉ Phase 3 : Inclut le contenu réel du document (images) dans le PDF.
    """
    doc = get_object_or_404(ParcelleDocument, pk=pk)
    user = request.user

    # Vérification des permissions
    if doc.confidentiality == "private" and not (user.is_admin_role or user.is_geometre):
        raise Http404("Document non accessible.")
    if doc.confidentiality == "buyer_only" and not (
        user.is_acheteur or user.is_admin_role or
        user.is_geometre or doc.parcelle.owner == user
    ):
        raise Http404("Réservé aux acheteurs vérifiés.")

    # Log de consultation
    DocumentAccessLog.objects.create(
        document=doc,
        user=user,
        ip_address=_get_ip(request),
        action="view_watermarked",
    )
    AccessLog.objects.create(
        user=user,
        action=AccessLog.ActionType.VIEW_DOC,
        resource_type="ParcelleDocument",
        resource_id=str(doc.pk),
        details={"doc_type": doc.doc_type, "parcelle": doc.parcelle.lot_number},
    )

    # ─── Génération du PDF avec watermark + contenu réel ───
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Watermark text
    watermark_text = settings.WATERMARK_TEXT_TEMPLATE.format(
        user=user.get_full_name() or user.email,
        date=timezone.now().strftime("%d/%m/%Y à %H:%M"),
    )

    # ─── PAGE 1 : Fiche d'information du document ───
    _draw_watermark(p, width, height, watermark_text)
    y = _draw_header(p, width, height, height - 30)

    # Titre du document
    p.setFont("Helvetica-Bold", 14)
    p.setFillColor(HexColor("#0f172a"))
    p.drawString(40, y, f"Document Sécurisé — {doc.get_doc_type_display()}")
    y -= 30

    # Informations
    p.setFont("Helvetica", 11)
    p.setFillColor(HexColor("#1e293b"))
    infos = [
        ("Titre", doc.title),
        ("Type", doc.get_doc_type_display()),
        ("Parcelle", f"Lot {doc.parcelle.lot_number} — {doc.parcelle.title}"),
        ("Propriétaire", doc.parcelle.owner.get_full_name()),
        ("Surface", "{:,.2f} m²".format(float(doc.parcelle.surface_m2)) if doc.parcelle.surface_m2 else "—"),
        ("Prix", "{:,.0f} FCFA".format(float(doc.parcelle.price)) if doc.parcelle.price else "—"),
        ("Vérifié", "Oui ✓" if doc.is_verified else "Non — En attente"),
        ("Confidentialité", doc.get_confidentiality_display()),
        ("Hash SHA-256", doc.file_hash[:40] + "..." if doc.file_hash else "—"),
    ]

    for label, value in infos:
        p.setFont("Helvetica-Bold", 10)
        p.setFillColor(HexColor("#6b7280"))
        p.drawString(40, y, f"{label} :")
        p.setFont("Helvetica", 10)
        p.setFillColor(HexColor("#1e293b"))
        p.drawString(160, y, str(value))
        y -= 20

    # Description
    if doc.description:
        y -= 10
        p.setFont("Helvetica-Oblique", 9)
        p.setFillColor(HexColor("#64748b"))
        # Tronquer si trop long
        desc = doc.description[:300] + ("..." if len(doc.description) > 300 else "")
        p.drawString(40, y, f"Description : {desc}")
        y -= 20

    # Traçabilité
    y -= 15
    p.setStrokeColor(HexColor("#e2e8f0"))
    p.setLineWidth(0.5)
    p.line(40, y + 8, width - 40, y + 8)
    y -= 5

    p.setFont("Helvetica-Bold", 10)
    p.setFillColor(HexColor("#ef4444"))
    p.drawString(40, y, "⚠ Traçabilité de consultation")
    y -= 18
    p.setFont("Helvetica", 9)
    p.setFillColor(HexColor("#64748b"))
    trace_infos = [
        f"Consulté par : {user.get_full_name()} ({user.email})",
        f"Date : {timezone.now().strftime('%d/%m/%Y %H:%M:%S')}",
        f"IP : {_get_ip(request) or 'N/A'}",
        "Ce document est protégé. Toute reproduction non autorisée est tracée.",
    ]
    for info in trace_infos:
        p.drawString(40, y, info)
        y -= 15

    # ─── PAGE 2+ : Contenu réel du document (images) ───
    file_path = _get_file_absolute_path(doc.file)

    if file_path and _is_image_file(file_path):
        p.showPage()
        _draw_watermark(p, width, height, watermark_text, font_size=18, opacity=0.15)

        try:
            img = ImageReader(file_path)
            img_w, img_h = img.getSize()

            # Calculer les dimensions pour tenir dans la page avec marges
            max_w = width - 80
            max_h = height - 120
            ratio = min(max_w / img_w, max_h / img_h)
            draw_w = img_w * ratio
            draw_h = img_h * ratio

            # Centrer l'image
            x = (width - draw_w) / 2
            y_img = (height - draw_h) / 2

            # Cadre
            p.setStrokeColor(HexColor("#e2e8f0"))
            p.setLineWidth(1)
            p.rect(x - 4, y_img - 4, draw_w + 8, draw_h + 8)

            p.drawImage(img, x, y_img, width=draw_w, height=draw_h,
                        preserveAspectRatio=True, mask="auto")

            # Légende sous l'image
            p.setFont("Helvetica", 8)
            p.setFillColor(HexColor("#6b7280"))
            p.drawCentredString(width / 2, y_img - 20,
                                f"{doc.title} — Lot {doc.parcelle.lot_number}")

        except Exception as e:
            p.setFont("Helvetica", 10)
            p.setFillColor(HexColor("#ef4444"))
            p.drawString(40, height / 2, f"Erreur de chargement de l'image : {e}")

    elif file_path and file_path.lower().endswith(".pdf") and HAS_PYPDF2:
        # Watermarker le PDF original page par page
        p.showPage()
        p.save()
        # Créer le PDF info (page 1) depuis le buffer existant
        buffer.seek(0)
        info_reader = PdfReader(buffer)

        # Lire le PDF original
        try:
            original_reader = PdfReader(file_path)
            writer = PdfWriter()

            # Ajouter la page d'info en premier
            for pg in info_reader.pages:
                writer.add_page(pg)

            # Ajouter chaque page du PDF original avec watermark
            for page_num, page in enumerate(original_reader.pages):
                wm_buffer = io.BytesIO()
                wm_canvas = canvas.Canvas(wm_buffer, pagesize=A4)
                _draw_watermark(wm_canvas, width, height, watermark_text, font_size=18, opacity=0.15)
                wm_canvas.save()
                wm_buffer.seek(0)
                wm_reader = PdfReader(wm_buffer)
                page.merge_page(wm_reader.pages[0])
                writer.add_page(page)

            merged_buffer = io.BytesIO()
            writer.write(merged_buffer)
            merged_buffer.seek(0)

            response = HttpResponse(merged_buffer, content_type="application/pdf")
            response["Content-Disposition"] = f'inline; filename="doc_{doc.pk}_watermarked.pdf"'
            response["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response["Pragma"] = "no-cache"
            return response

        except Exception as e:
            # Fallback : recréer le buffer et continuer avec le message d'erreur
            buffer = io.BytesIO()
            p = canvas.Canvas(buffer, pagesize=A4)
            _draw_watermark(p, width, height, watermark_text)
            y_new = _draw_header(p, width, height, height - 30)
            p.setFont("Helvetica-Bold", 10)
            p.setFillColor(HexColor("#ef4444"))
            p.drawString(40, y_new, f"Erreur lecture PDF original : {e}")

    elif file_path and file_path.lower().endswith(".pdf"):
        # Fallback sans PyPDF2
        y -= 30
        p.setFont("Helvetica-Bold", 10)
        p.setFillColor(HexColor("#3b82f6"))
        p.drawString(40, y, "[PDF] Le document original est un PDF.")
        y -= 15
        p.setFont("Helvetica", 9)
        p.drawString(40, y, "Consultez l'original via l'interface EYE-FONCIER pour le contenu complet.")

    elif file_path:
        y -= 30
        p.setFont("Helvetica", 9)
        p.setFillColor(HexColor("#6b7280"))
        ext = os.path.splitext(file_path)[1]
        p.drawString(40, y, f"[FICHIER] Fichier joint : {os.path.basename(file_path)} ({ext})")

    p.showPage()
    p.save()

    buffer.seek(0)
    response = HttpResponse(buffer, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="doc_{doc.pk}_watermarked.pdf"'
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["Pragma"] = "no-cache"
    return response


@login_required
def parcelle_fiche_pdf(request, parcelle_pk):
    """
    Fiche technique complète d'une parcelle en PDF.
    Inclut : détails, carte statique (si disponible), documents annexés avec miniatures.
    """
    from parcelles.models import Parcelle
    parcelle = get_object_or_404(Parcelle, pk=parcelle_pk)

    user = request.user
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    watermark_text = f"EYE-FONCIER — {user.get_full_name()} — {timezone.now().strftime('%d/%m/%Y')}"

    # ─── PAGE 1 : Fiche technique ───
    _draw_watermark(p, width, height, watermark_text, font_size=16, opacity=0.12)
    y = _draw_header(p, width, height, height - 30)

    p.setFont("Helvetica-Bold", 16)
    p.setFillColor(HexColor("#0f172a"))
    p.drawString(40, y, f"Fiche Technique — Lot {parcelle.lot_number}")
    y -= 10

    p.setFont("Helvetica", 9)
    p.setFillColor(HexColor("#6b7280"))
    p.drawString(40, y, f"Générée le {timezone.now().strftime('%d/%m/%Y à %H:%M')}")
    y -= 25

    # Détails
    details = [
        ("Titre", parcelle.title),
        ("N° de Lot", parcelle.lot_number),
        ("Zone", str(parcelle.zone) if parcelle.zone else "—"),
        ("Îlot", str(parcelle.ilot) if parcelle.ilot else "—"),
        ("Adresse", parcelle.address or "—"),
        ("Type", parcelle.get_land_type_display()),
        ("Surface", "{:,.2f} m²".format(float(parcelle.surface_m2)) if parcelle.surface_m2 else "—"),
        ("Prix", "{:,.0f} FCFA".format(float(parcelle.price)) if parcelle.price else "—"),
        ("Prix/m²", "{:,.0f} FCFA/m²".format(float(parcelle.price_per_m2)) if parcelle.price_per_m2 else "—"),
        ("Statut", parcelle.get_status_display()),
        ("Validé", "Oui ✓" if parcelle.is_validated else "Non"),
        ("Badge confiance", "Oui ✓" if parcelle.trust_badge else "Non"),
        ("Propriétaire", parcelle.owner.get_full_name()),
        ("Vues", str(parcelle.views_count)),
    ]

    for label, value in details:
        if y < 80:
            p.showPage()
            _draw_watermark(p, width, height, watermark_text, font_size=16, opacity=0.12)
            y = height - 60

        p.setFont("Helvetica-Bold", 10)
        p.setFillColor(HexColor("#6b7280"))
        p.drawString(40, y, f"{label} :")
        p.setFont("Helvetica", 10)
        p.setFillColor(HexColor("#1e293b"))
        p.drawString(180, y, str(value))
        y -= 18

    # Description
    if parcelle.description:
        y -= 10
        p.setFont("Helvetica-Bold", 10)
        p.setFillColor(HexColor("#0f172a"))
        p.drawString(40, y, "Description :")
        y -= 15
        p.setFont("Helvetica", 9)
        p.setFillColor(HexColor("#475569"))
        # Découper la description en lignes
        desc = parcelle.description[:800]
        words = desc.split()
        line = ""
        for word in words:
            test_line = f"{line} {word}".strip()
            if p.stringWidth(test_line, "Helvetica", 9) < width - 80:
                line = test_line
            else:
                p.drawString(40, y, line)
                y -= 13
                line = word
                if y < 80:
                    p.showPage()
                    _draw_watermark(p, width, height, watermark_text, font_size=16, opacity=0.12)
                    y = height - 60
        if line:
            p.drawString(40, y, line)
            y -= 13

    # ─── Documents annexés ───
    docs = parcelle.documents.all()
    if docs.exists():
        y -= 20
        if y < 120:
            p.showPage()
            _draw_watermark(p, width, height, watermark_text, font_size=16, opacity=0.12)
            y = height - 60

        p.setStrokeColor(HexColor("#22c55e"))
        p.setLineWidth(1.5)
        p.line(40, y + 8, width - 40, y + 8)
        y -= 5

        p.setFont("Helvetica-Bold", 12)
        p.setFillColor(HexColor("#0f172a"))
        p.drawString(40, y, f"Documents annexés ({docs.count()})")
        y -= 20

        for doc in docs:
            if y < 100:
                p.showPage()
                _draw_watermark(p, width, height, watermark_text, font_size=16, opacity=0.12)
                y = height - 60

            # Icône selon type
            icons = {
                "titre_foncier": "[TF]", "acd": "[ACD]", "certificat": "[CERT]",
                "plan": "[PLAN]", "permis": "[PERMIS]", "attestation": "[ATT]", "autre": "[DOC]",
            }
            icon = icons.get(doc.doc_type, "[DOC]")

            p.setFont("Helvetica-Bold", 9)
            p.setFillColor(HexColor("#1e293b"))
            p.drawString(40, y, f"{icon}  {doc.title}")

            p.setFont("Helvetica", 8)
            p.setFillColor(HexColor("#6b7280"))
            p.drawString(40, y - 13,
                         f"Type : {doc.get_doc_type_display()} | "
                         f"Vérifié : {'Oui' if doc.is_verified else 'Non'} | "
                         f"Confid. : {doc.get_confidentiality_display()}")

            # Miniature si c'est une image
            file_path = _get_file_absolute_path(doc.file)
            if file_path and _is_image_file(file_path):
                try:
                    img = ImageReader(file_path)
                    thumb_h = 50
                    thumb_w = 70
                    p.drawImage(img, width - 40 - thumb_w, y - 25, width=thumb_w,
                                height=thumb_h, preserveAspectRatio=True, mask="auto")
                except Exception:
                    pass

            y -= 40

    # Coordonnées du centroïde
    if parcelle.centroid:
        y -= 10
        p.setFont("Helvetica", 8)
        p.setFillColor(HexColor("#6b7280"))
        p.drawString(40, y,
                     f"Centroïde : {parcelle.centroid.y:.6f}°N, {parcelle.centroid.x:.6f}°W")

    p.showPage()
    p.save()

    buffer.seek(0)
    response = HttpResponse(buffer, content_type="application/pdf")
    filename = f"fiche_{parcelle.lot_number}.pdf"
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@login_required
def digital_vault_view(request):
    """Coffre-fort numérique — tous les documents accessibles à l'utilisateur."""
    user = request.user
    from parcelles.models import Parcelle
    from transactions.models import Transaction

    # Documents des parcelles de l'utilisateur (vendeur)
    own_parcelles = Parcelle.objects.filter(owner=user)
    # Parcelles où l'utilisateur est acheteur
    buyer_transactions = Transaction.objects.filter(buyer=user).exclude(
        status="cancelled"
    ).values_list("parcelle_id", flat=True)

    docs = ParcelleDocument.objects.filter(
        models.Q(parcelle__in=own_parcelles) | models.Q(parcelle_id__in=buyer_transactions)
    ).select_related("parcelle", "uploaded_by").order_by("-created_at")

    # Filtrage
    doc_type = request.GET.get("type")
    if doc_type:
        docs = docs.filter(doc_type=doc_type)

    confidentiality = request.GET.get("conf")
    if confidentiality:
        docs = docs.filter(confidentiality=confidentiality)

    parcelle_pk = request.GET.get("parcelle")
    if parcelle_pk:
        docs = docs.filter(parcelle_id=parcelle_pk)

    # Stats
    total_docs = docs.count()
    verified_count = docs.filter(is_verified=True).count()
    parcelles_with_docs = docs.values("parcelle").distinct().count()

    # Filtrer selon le rôle pour la confidentialité
    if not (user.is_admin_role or user.is_geometre or user.is_superuser):
        if user.is_acheteur and user.is_verified:
            docs = docs.exclude(confidentiality="private")
        elif not user.is_vendeur:
            docs = docs.filter(confidentiality="public")

    context = {
        "documents": docs[:100],
        "total_docs": total_docs,
        "verified_count": verified_count,
        "parcelles_with_docs": parcelles_with_docs,
        "doc_types": ParcelleDocument.DOC_TYPE_CHOICES if hasattr(ParcelleDocument, "DOC_TYPE_CHOICES") else [],
        "current_type": doc_type,
        "current_conf": confidentiality,
    }
    return render(request, "documents/digital_vault.html", context)


def _get_ip(request):
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    return x_forwarded.split(",")[0].strip() if x_forwarded else request.META.get("REMOTE_ADDR")
