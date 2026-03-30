"""
Service de facturation — EYE-FONCIER
Génération automatique de factures + export PDF.
"""
import io
import logging
from decimal import Decimal
from datetime import timedelta

from django.utils import timezone
from django.core.files.base import ContentFile
from django.template.loader import render_to_string

from .models import Invoice

logger = logging.getLogger("transactions.invoice")


# ═══════════════════════════════════════════════════════
#  CRÉATION DE FACTURES
# ═══════════════════════════════════════════════════════

def create_invoice_for_cotation(cotation):
    """Crée une facture pour un paiement de cotation confirmé.

    Args:
        cotation: Cotation instance (status=VALIDATED ou PAID)
    Returns:
        Invoice instance
    """
    from .cotation_models import Cotation

    user = cotation.payer

    # Déterminer le type de facture
    if cotation.cotation_type == Cotation.CotationType.BOUTIQUE:
        inv_type = Invoice.InvoiceType.BOUTIQUE
        description = "Cotisation boutique vendeur — Activation espace de publication"
        line_items = [{
            "description": "Cotisation boutique EYE-FONCIER",
            "quantity": 1,
            "unit_price": float(cotation.amount),
            "total": float(cotation.amount),
        }]
    else:
        inv_type = Invoice.InvoiceType.COTATION
        parcelle_info = ""
        if cotation.parcelle:
            parcelle_info = f" — Lot {cotation.parcelle.lot_number}"
        description = f"Cotation achat (10%){parcelle_info}"
        line_items = [{
            "description": f"Cotation 10% — Parcelle {cotation.parcelle.lot_number if cotation.parcelle else 'N/A'}",
            "quantity": 1,
            "unit_price": float(cotation.amount),
            "total": float(cotation.amount),
        }]
        if cotation.parcelle:
            line_items[0]["detail"] = f"Prix du bien : {cotation.property_price:,.0f} FCFA"

    invoice = Invoice(
        client=user,
        client_name=user.get_full_name() or user.username,
        client_email=user.email,
        client_phone=getattr(user, "phone", "") or "",
        invoice_type=inv_type,
        status=Invoice.InvoiceStatus.PAID,
        subtotal=cotation.amount,
        tax_rate=Decimal("0"),
        description=description,
        line_items=line_items,
        payment_reference=cotation.payment_reference or "",
        payment_method=cotation.payment_method or "",
        paid_at=cotation.paid_at or timezone.now(),
        cotation=cotation,
        parcelle=cotation.parcelle,
        issued_at=timezone.now(),
        due_date=timezone.now().date(),
    )
    invoice.save()

    # Générer le PDF
    try:
        _generate_invoice_pdf(invoice)
    except Exception as e:
        logger.warning("Erreur génération PDF facture %s: %s", invoice.invoice_number, e)

    logger.info("Facture %s créée pour cotation %s", invoice.invoice_number, cotation.reference)
    return invoice


def create_invoice_for_promotion(campaign):
    """Crée une facture pour une campagne de promotion payée."""
    user = campaign.seller

    invoice = Invoice(
        client=user,
        client_name=user.get_full_name() or user.username,
        client_email=user.email,
        client_phone=getattr(user, "phone", "") or "",
        invoice_type=Invoice.InvoiceType.PROMOTION,
        status=Invoice.InvoiceStatus.PAID,
        subtotal=campaign.amount_paid or Decimal("0"),
        tax_rate=Decimal("0"),
        description=f"Campagne {campaign.get_campaign_type_display()} — Lot {campaign.parcelle.lot_number}",
        line_items=[{
            "description": f"Promotion {campaign.get_campaign_type_display()} ({campaign.duration_weeks} sem.)",
            "quantity": campaign.duration_weeks,
            "unit_price": float(campaign.unit_price),
            "total": float(campaign.total_price),
        }],
        payment_reference=campaign.payment_reference or "",
        payment_method=campaign.payment_method or "",
        paid_at=timezone.now(),
        parcelle=campaign.parcelle,
        issued_at=timezone.now(),
        due_date=timezone.now().date(),
    )
    invoice.save()

    try:
        _generate_invoice_pdf(invoice)
    except Exception as e:
        logger.warning("Erreur PDF facture promo %s: %s", invoice.invoice_number, e)

    return invoice


def create_invoice_for_visit(bon_visite, amount=5000):
    """Crée une facture pour un bon de visite."""
    user = bon_visite.buyer

    invoice = Invoice(
        client=user,
        client_name=user.get_full_name() or user.username,
        client_email=user.email,
        invoice_type=Invoice.InvoiceType.VISITE,
        status=Invoice.InvoiceStatus.PAID,
        subtotal=Decimal(str(amount)),
        tax_rate=Decimal("0"),
        description=f"Bon de visite — Lot {bon_visite.parcelle.lot_number}",
        line_items=[{
            "description": f"Visite terrain — Parcelle Lot {bon_visite.parcelle.lot_number}",
            "quantity": 1,
            "unit_price": float(amount),
            "total": float(amount),
        }],
        parcelle=bon_visite.parcelle,
        paid_at=timezone.now(),
        issued_at=timezone.now(),
        due_date=timezone.now().date(),
    )
    invoice.save()

    try:
        _generate_invoice_pdf(invoice)
    except Exception as e:
        logger.warning("Erreur PDF facture visite %s: %s", invoice.invoice_number, e)

    return invoice


# ═══════════════════════════════════════════════════════
#  GÉNÉRATION PDF
# ═══════════════════════════════════════════════════════

def _generate_invoice_pdf(invoice):
    """Génère le fichier PDF de la facture via xhtml2pdf."""
    try:
        from xhtml2pdf import pisa
    except ImportError:
        logger.warning("xhtml2pdf non installé — PDF non généré")
        return None

    html_content = render_to_string("invoices/invoice_pdf.html", {
        "invoice": invoice,
        "company": {
            "name": "EYE-FONCIER SAS",
            "address": "Abidjan, Côte d'Ivoire",
            "phone": "+225 07 00 00 00 00",
            "email": "contact@eye-foncier.com",
            "rccm": "CI-ABJ-2024-B-XXXXX",
            "cc": "2411111 A",
        },
    })

    buffer = io.BytesIO()
    pisa_status = pisa.CreatePDF(
        io.BytesIO(html_content.encode("utf-8")),
        dest=buffer,
        encoding="utf-8",
    )

    if pisa_status.err:
        logger.error("Erreur xhtml2pdf: %d erreur(s)", pisa_status.err)
        return None

    pdf_content = buffer.getvalue()
    buffer.close()

    filename = f"{invoice.invoice_number}.pdf"
    invoice.pdf_file.save(filename, ContentFile(pdf_content), save=True)

    logger.info("PDF généré: %s (%d octets)", filename, len(pdf_content))
    return invoice.pdf_file


def regenerate_pdf(invoice):
    """Regénère le PDF d'une facture existante."""
    if invoice.pdf_file:
        invoice.pdf_file.delete(save=False)
    return _generate_invoice_pdf(invoice)


# ═══════════════════════════════════════════════════════
#  HISTORIQUE & REQUÊTES
# ═══════════════════════════════════════════════════════

def get_user_invoices(user, invoice_type=None, status=None):
    """Récupère les factures d'un utilisateur avec filtres optionnels."""
    qs = Invoice.objects.filter(client=user)
    if invoice_type:
        qs = qs.filter(invoice_type=invoice_type)
    if status:
        qs = qs.filter(status=status)
    return qs.order_by("-created_at")


def get_platform_revenue(period_days=30):
    """Calcule les revenus plateforme sur une période."""
    start = timezone.now() - timedelta(days=period_days)
    paid = Invoice.objects.filter(
        status__in=[Invoice.InvoiceStatus.PAID],
        paid_at__gte=start,
    )
    from django.db.models import Sum, Count
    return {
        "total_revenue": paid.aggregate(s=Sum("total"))["s"] or 0,
        "invoice_count": paid.count(),
        "by_type": dict(
            paid.values_list("invoice_type")
            .annotate(s=Sum("total"))
            .values_list("invoice_type", "s")
        ),
        "by_method": dict(
            paid.exclude(payment_method="")
            .values_list("payment_method")
            .annotate(c=Count("id"))
            .values_list("payment_method", "c")
        ),
    }
