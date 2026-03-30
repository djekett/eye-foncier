"""Vues des transactions — réservation, séquestre, bon de visite, compromis."""
import json
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone
from django.views.generic import ListView, DetailView
from django.http import JsonResponse, HttpResponse

from django.db.models import Count, Sum

from .models import Transaction, TransactionApproval, ContractSignature, BonDeVisite, FinancialScore, SimulationResult
from .forms import ReservationForm, TransactionUpdateForm, FinancialProfileForm, SimulatorForm
from parcelles.models import Parcelle
from accounts.models import AccessLog
from accounts.decorators import role_required, acheteur_required, admin_required

logger = logging.getLogger("transactions")


@acheteur_required
def reserve_parcelle_view(request, parcelle_pk):
    """Réservation d'une parcelle par un acheteur.

    PREREQUIS : Cotation de 10 % payée et validée.
    « Ne réserve pas une parcelle qui veut, mais qui peut. »
    """
    parcelle = get_object_or_404(Parcelle, pk=parcelle_pk)

    if parcelle.status != Parcelle.Status.DISPONIBLE:
        messages.warning(request, "Cette parcelle n'est plus disponible.")
        return redirect("parcelles:detail", pk=parcelle_pk)

    # ── GARDE COTATION : vérifier qu'une cotation validée existe ──
    from .cotation_service import check_cotation_access
    cotation = check_cotation_access(request.user, parcelle)
    if not cotation or not cotation.is_valid:
        messages.warning(
            request,
            "Vous devez d'abord payer la cotation (10 % du prix) "
            "avant de pouvoir réserver cette parcelle."
        )
        return redirect("transactions:cotation_create", parcelle_pk=parcelle_pk)

    if request.method == "POST":
        form = ReservationForm(request.POST)
        if form.is_valid():
            from .approval_service import request_approval

            use_escrow = form.cleaned_data.get("use_escrow", False)

            # Montant = prix total - cotation déjà payée
            remaining_amount = parcelle.price - cotation.amount

            tx = Transaction.objects.create(
                parcelle=parcelle,
                buyer=request.user,
                seller=parcelle.owner,
                amount=parcelle.price,
                status=Transaction.Status.PENDING,
                payment_method="escrow" if use_escrow else "",
                notes=form.cleaned_data.get("notes", ""),
            )

            # Lier la cotation à la transaction
            cotation.transaction = tx
            cotation.save(update_fields=["transaction"])

            # Demande d'approbation au vendeur
            request_approval(tx, "reserve", request.user)

            AccessLog.objects.create(
                user=request.user,
                action=AccessLog.ActionType.RESERVATION,
                resource_type="Parcelle",
                resource_id=str(parcelle.pk),
                details={
                    "transaction": str(tx.pk),
                    "amount": str(tx.amount),
                    "cotation": str(cotation.pk),
                    "cotation_amount": str(cotation.amount),
                },
            )

            messages.success(
                request,
                f"Demande de réservation envoyée au vendeur de {parcelle.lot_number}. "
                f"Référence : {tx.reference}. "
                f"Cotation de {cotation.amount:,.0f} FCFA déduite du prix total.",
            )
            return redirect("transactions:detail", pk=tx.pk)
    else:
        form = ReservationForm()

    return render(request, "transactions/reserve.html", {
        "form": form,
        "parcelle": parcelle,
        "cotation": cotation,
        "remaining_amount": parcelle.price - cotation.amount,
    })


# ─── Séquestre (Escrow) ────────────────────────────────
@login_required
def escrow_fund_view(request, pk):
    """Alimenter le séquestre — l'acheteur verse les fonds."""
    tx = get_object_or_404(Transaction, pk=pk)
    if tx.buyer != request.user:
        messages.error(request, "Seul l'acheteur peut alimenter le séquestre.")
        return redirect("transactions:detail", pk=pk)
    if tx.escrow_funded:
        messages.info(request, "Le séquestre est déjà alimenté.")
        return redirect("transactions:detail", pk=pk)

    if request.method == "POST":
        from .approval_service import request_approval

        request_approval(
            tx, "escrow_fund", request.user,
            metadata={"escrow_amount": str(tx.amount)},
        )

        msg = "Demande d'alimentation du séquestre ({:,.0f} FCFA) envoyée au vendeur pour validation.".format(float(tx.amount))
        messages.success(request, msg)
        return redirect("transactions:detail", pk=pk)

    return render(request, "transactions/escrow_fund.html", {"transaction": tx})


@login_required
def escrow_confirm_docs_view(request, pk):
    """L'acheteur confirme avoir reçu les documents légaux."""
    tx = get_object_or_404(Transaction, pk=pk)
    if tx.buyer != request.user:
        messages.error(request, "Non autorisé.")
        return redirect("transactions:detail", pk=pk)
    if not tx.escrow_funded:
        messages.warning(request, "Le séquestre n'est pas encore alimenté.")
        return redirect("transactions:detail", pk=pk)

    if request.method == "POST":
        from .approval_service import request_approval

        request_approval(tx, "docs_confirm", request.user)

        messages.success(
            request,
            "Demande de confirmation des documents envoyée au vendeur pour validation."
        )
        return redirect("transactions:detail", pk=pk)

    return render(request, "transactions/escrow_confirm.html", {"transaction": tx})


@admin_required
def escrow_release_view(request, pk):
    """Admin/EYE-Foncier libère le séquestre vers le vendeur."""
    tx = get_object_or_404(Transaction, pk=pk)

    if request.method == "POST":
        from .transaction_service import transition_status

        transition_status(tx, "completed", request.user, "Séquestre libéré par l'administrateur")

        msg = "Séquestre libéré — {:,.0f} FCFA transférés au vendeur.".format(float(tx.amount))
        messages.success(request, msg)
        return redirect("transactions:detail", pk=pk)

    return render(request, "transactions/escrow_release.html", {"transaction": tx})


# ─── Compromis de vente ─────────────────────────────────
@login_required
def initiate_compromis_view(request, pk):
    """Initier la vente — génère un compromis pré-rempli."""
    tx = get_object_or_404(Transaction, pk=pk)
    if tx.seller != request.user and not request.user.is_admin_role:
        messages.error(request, "Seul le vendeur ou un admin peut initier la vente.")
        return redirect("transactions:detail", pk=pk)

    if request.method == "POST":
        from .approval_service import request_approval

        request_approval(tx, "compromis", request.user)

        messages.success(
            request,
            "Demande de compromis envoyée à l'acheteur pour validation. "
            "Vous serez notifié dès approbation."
        )
        return redirect("transactions:detail", pk=pk)

    return render(request, "transactions/compromis.html", {"transaction": tx})


@login_required
def compromis_pdf_view(request, pk):
    """Génère le PDF du compromis de vente pré-rempli."""
    import io
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.colors import HexColor

    tx = get_object_or_404(Transaction, pk=pk)

    # Seuls les parties ou un admin peuvent accéder
    if tx.buyer != request.user and tx.seller != request.user and not request.user.is_admin_role:
        messages.error(request, "Non autorisé.")
        return redirect("transactions:detail", pk=pk)

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # En-tête
    p.setFont("Helvetica-Bold", 18)
    p.setFillColor(HexColor("#16a34a"))
    p.drawCentredString(width / 2, height - 60, "COMPROMIS DE VENTE")

    p.setFont("Helvetica", 10)
    p.setFillColor(HexColor("#6b7280"))
    p.drawCentredString(width / 2, height - 78, "EYE-FONCIER — Plateforme WebSIG de Transaction Foncière")

    p.setStrokeColor(HexColor("#22c55e"))
    p.setLineWidth(2)
    p.line(40, height - 90, width - 40, height - 90)

    y = height - 120

    # Référence
    p.setFont("Helvetica-Bold", 11)
    p.setFillColor(HexColor("#0f172a"))
    p.drawString(40, y, f"Référence Transaction : {tx.reference}")
    p.drawString(width / 2, y, f"Date : {timezone.now().strftime('%d/%m/%Y')}")
    y -= 30

    # Vendeur
    p.setFont("Helvetica-Bold", 12)
    p.setFillColor(HexColor("#1e40af"))
    p.drawString(40, y, "LE VENDEUR")
    y -= 18
    p.setFont("Helvetica", 10)
    p.setFillColor(HexColor("#1e293b"))
    seller_infos = [
        f"Nom : {tx.seller.get_full_name()}",
        f"Email : {tx.seller.email}",
        f"Téléphone : {tx.seller.phone or '—'}",
    ]
    for info in seller_infos:
        p.drawString(60, y, info)
        y -= 16
    y -= 15

    # Acheteur
    p.setFont("Helvetica-Bold", 12)
    p.setFillColor(HexColor("#1e40af"))
    p.drawString(40, y, "L'ACHETEUR")
    y -= 18
    p.setFont("Helvetica", 10)
    p.setFillColor(HexColor("#1e293b"))
    buyer_infos = [
        f"Nom : {tx.buyer.get_full_name()}",
        f"Email : {tx.buyer.email}",
        f"Téléphone : {tx.buyer.phone or '—'}",
    ]
    for info in buyer_infos:
        p.drawString(60, y, info)
        y -= 16
    y -= 15

    # Bien objet de la vente
    p.setFont("Helvetica-Bold", 12)
    p.setFillColor(HexColor("#1e40af"))
    p.drawString(40, y, "BIEN OBJET DE LA VENTE")
    y -= 18
    p.setFont("Helvetica", 10)
    p.setFillColor(HexColor("#1e293b"))
    parcelle = tx.parcelle
    bien_infos = [
        f"Lot N° : {parcelle.lot_number}",
        f"Titre : {parcelle.title}",
        f"Adresse : {parcelle.address or '—'}",
        f"Zone : {parcelle.zone or '—'}",
        "Surface : {:,.2f} m²".format(float(parcelle.surface_m2)) if parcelle.surface_m2 else "Surface : — m²",
        f"Type : {parcelle.get_land_type_display()}",
    ]
    for info in bien_infos:
        p.drawString(60, y, info)
        y -= 16
    y -= 15

    # Conditions financières
    p.setFont("Helvetica-Bold", 12)
    p.setFillColor(HexColor("#1e40af"))
    p.drawString(40, y, "CONDITIONS FINANCIÈRES")
    y -= 18
    p.setFont("Helvetica", 10)
    p.setFillColor(HexColor("#1e293b"))
    fin_infos = [
        "Prix de vente convenu : {:,.0f} FCFA".format(float(tx.amount)) if tx.amount else "Prix de vente convenu : — FCFA",
        f"Mode de paiement : {tx.get_payment_method_display() or '—'}",
        f"Séquestre : {'Oui — ' + str(tx.escrow_amount or 0) + ' FCFA' if tx.escrow_funded else 'Non'}",
    ]
    for info in fin_infos:
        p.drawString(60, y, info)
        y -= 16
    y -= 30

    # Signatures
    p.setFont("Helvetica-Bold", 10)
    p.setFillColor(HexColor("#0f172a"))
    p.drawString(40, y, "Le Vendeur")
    p.drawString(width / 2 + 40, y, "L'Acheteur")
    y -= 15
    p.setFont("Helvetica", 9)
    p.drawString(40, y, f"{tx.seller.get_full_name()}")
    p.drawString(width / 2 + 40, y, f"{tx.buyer.get_full_name()}")
    y -= 10
    p.setStrokeColor(HexColor("#e2e8f0"))
    p.line(40, y, 250, y)
    p.line(width / 2 + 40, y, width - 40, y)
    y -= 12
    p.setFont("Helvetica", 8)
    p.setFillColor(HexColor("#6b7280"))
    p.drawString(40, y, "Signature :")
    p.drawString(width / 2 + 40, y, "Signature :")

    # Pied de page
    p.setFont("Helvetica", 7)
    p.setFillColor(HexColor("#94a3b8"))
    p.drawCentredString(width / 2, 40,
                        f"Document généré par EYE-FONCIER le {timezone.now().strftime('%d/%m/%Y à %H:%M')} — "
                        f"Réf. {tx.reference}")
    p.drawCentredString(width / 2, 28,
                        "Ce document n'a de valeur juridique qu'après signature des deux parties.")

    p.showPage()
    p.save()

    buffer.seek(0)
    response = HttpResponse(buffer, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="compromis_{tx.reference}.pdf"'
    return response


# ─── Bon de Visite ──────────────────────────────────────
@acheteur_required
def request_visit_view(request, parcelle_pk):
    """Générer un bon de visite pour une parcelle.

    PREREQUIS : Cotation de 10 % payée et validée.
    La visite est un droit acquis par le paiement de la cotation.
    """
    parcelle = get_object_or_404(Parcelle, pk=parcelle_pk)

    # ── GARDE COTATION : visite autorisée seulement avec cotation validée ──
    from .cotation_service import check_cotation_access
    cotation = check_cotation_access(request.user, parcelle)
    if not cotation or not cotation.is_valid:
        messages.warning(
            request,
            "Vous devez payer la cotation (10 % du prix) pour pouvoir "
            "visiter cette parcelle."
        )
        return redirect("transactions:cotation_create", parcelle_pk=parcelle_pk)

    if request.method == "POST":
        visit_date_str = request.POST.get("visit_date", "")
        visit_notes = request.POST.get("visit_notes", "")

        if not visit_date_str:
            messages.error(request, "Veuillez indiquer une date de visite.")
            return redirect("transactions:request_visit", parcelle_pk=parcelle_pk)

        from django.utils.dateparse import parse_datetime
        visit_date = parse_datetime(visit_date_str + "T09:00:00") or timezone.now()

        bon = BonDeVisite.objects.create(
            parcelle=parcelle,
            visitor=request.user,
            visit_date=visit_date,
            visit_notes=visit_notes,
        )

        AccessLog.objects.create(
            user=request.user,
            action=AccessLog.ActionType.VIEW_PARCELLE,
            resource_type="BonDeVisite",
            resource_id=str(bon.pk),
            details={
                "parcelle": str(parcelle.pk),
                "date": visit_date_str,
                "cotation": str(cotation.pk),
            },
        )

        messages.success(
            request,
            f"Bon de visite généré ! Référence : {bon.reference}. "
            "Le vendeur sera notifié de votre visite."
        )
        return redirect("transactions:visit_detail", pk=bon.pk)

    return render(request, "transactions/request_visit.html", {
        "parcelle": parcelle,
        "cotation": cotation,
    })


@login_required
def visit_detail_view(request, pk):
    """Détail d'un bon de visite (+ feedback après visite)."""
    bon = get_object_or_404(BonDeVisite, pk=pk)
    if bon.visitor != request.user and bon.parcelle.owner != request.user and not request.user.is_admin_role:
        messages.error(request, "Non autorisé.")
        return redirect("transactions:list")

    if request.method == "POST" and bon.visitor == request.user:
        # Soumettre le feedback post-visite
        bon.feedback = request.POST.get("feedback", "")
        rating = request.POST.get("rating")
        if rating and rating.isdigit():
            bon.feedback_rating = min(5, max(1, int(rating)))
        bon.status = BonDeVisite.Status.USED
        bon.save()
        messages.success(request, "Merci pour votre retour !")
        return redirect("transactions:visit_detail", pk=pk)

    return render(request, "transactions/visit_detail.html", {"bon": bon})


class TransactionDetailView(LoginRequiredMixin, DetailView):
    model = Transaction
    template_name = "transactions/transaction_detail.html"
    context_object_name = "transaction"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        tx = self.object
        ctx["can_update"] = (tx.seller == user or user.is_staff or user.is_admin_role)
        ctx["is_buyer"] = (tx.buyer == user)
        ctx["is_seller"] = (tx.seller == user)
        ctx["is_admin"] = (user.is_admin_role or user.is_superuser)
        # Timeline d'événements
        from .transaction_service import get_transaction_timeline
        ctx["events"] = get_transaction_timeline(tx)
        ctx["can_cancel"] = tx.status not in ("completed", "cancelled")
        ctx["can_dispute"] = tx.status not in ("cancelled", "disputed")
        # Approbations en attente
        ctx["pending_approvals"] = tx.approvals.filter(
            status=TransactionApproval.Status.PENDING,
        ).select_related("requested_by")
        return ctx


class TransactionListView(LoginRequiredMixin, ListView):
    model = Transaction
    template_name = "transactions/transaction_list.html"
    context_object_name = "transactions"
    paginate_by = 20

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.is_admin_role:
            return Transaction.objects.all().select_related("parcelle", "buyer", "seller")
        return Transaction.objects.filter(
            Q(buyer=user) | Q(seller=user)
        ).select_related("parcelle", "buyer", "seller")


@login_required
def transaction_update_view(request, pk):
    """Mise à jour d'une transaction."""
    tx = get_object_or_404(Transaction, pk=pk)
    if tx.seller != request.user and not request.user.is_admin_role:
        messages.error(request, "Non autorisé.")
        return redirect("transactions:detail", pk=pk)

    if request.method == "POST":
        form = TransactionUpdateForm(request.POST, instance=tx)
        if form.is_valid():
            new_status = form.cleaned_data.get("status")
            old_status = tx.status

            if new_status and new_status != old_status:
                from .transaction_service import transition_status

                try:
                    transition_status(tx, new_status, request.user, "Mise à jour manuelle admin")
                except ValueError as e:
                    messages.error(request, str(e))
                    return redirect("transactions:update", pk=pk)
            else:
                form.save()

            messages.success(request, "Transaction mise à jour.")
            return redirect("transactions:detail", pk=pk)
    else:
        form = TransactionUpdateForm(instance=tx)

    return render(request, "transactions/transaction_update.html", {
        "form": form, "transaction": tx,
    })


# ═══════════════════════════════════════════════════════════
# PAIEMENT EN LIGNE — CinetPay
# ═══════════════════════════════════════════════════════════

@login_required
def payment_initiate_view(request):
    """Initie un paiement via CinetPay.
    Paramètres POST :
        payment_type: 'promotion' | 'escrow' | 'certification' | 'visit'
        amount: montant FCFA
        reference_id: UUID de l'objet lié
        description: description libre
    """
    from .payment_service import initiate_payment, PaymentError, PAYMENT_METHODS

    if request.method != "POST":
        return redirect("accounts:dashboard")

    payment_type = request.POST.get("payment_type", "")
    amount = request.POST.get("amount", 0)
    reference_id = request.POST.get("reference_id", "")
    description = request.POST.get("description", "Paiement EYE-Foncier")

    try:
        amount = int(float(amount))
    except (ValueError, TypeError):
        messages.error(request, "Montant invalide.")
        return redirect("accounts:dashboard")

    user = request.user
    base_url = request.build_absolute_uri("/")

    try:
        result = initiate_payment(
            amount=amount,
            description=description,
            customer_name=user.get_full_name(),
            customer_email=user.email,
            customer_phone=getattr(user, "phone", ""),
            payment_type=payment_type,
            metadata={
                "user_id": str(user.pk),
                "payment_type": payment_type,
                "reference_id": reference_id,
            },
            return_url=base_url.rstrip("/") + "/transactions/paiement/retour/",
            notify_url=base_url.rstrip("/") + "/transactions/paiement/webhook/",
        )

        # Sauvegarder la référence du paiement en session
        request.session["pending_payment"] = {
            "transaction_id": result["transaction_id"],
            "amount": amount,
            "payment_type": payment_type,
            "reference_id": reference_id,
            "mode": result.get("mode", ""),
        }

        if result.get("mode") == "simulation":
            return redirect("transactions:payment_simulation", tx_id=result["transaction_id"])

        return redirect(result["payment_url"])

    except PaymentError as e:
        messages.error(request, "Erreur paiement : {}".format(str(e)))
        return redirect("accounts:dashboard")


@login_required
def payment_return_view(request):
    """Page de retour après paiement CinetPay."""
    from .payment_service import verify_payment

    pending = request.session.get("pending_payment", {})
    transaction_id = pending.get("transaction_id") or request.GET.get("transaction_id", "")

    if not transaction_id:
        messages.warning(request, "Aucun paiement en attente.")
        return redirect("accounts:dashboard")

    result = verify_payment(transaction_id)

    if result["status"] == "success":
        _process_payment_success(request, pending, result)
        messages.success(
            request,
            "Paiement de {:,.0f} FCFA confirmé ! Référence : {}".format(
                float(pending.get("amount", 0)), transaction_id,
            ),
        )
        request.session.pop("pending_payment", None)
    elif result["status"] == "pending":
        messages.info(request, "Votre paiement est en cours de traitement. Vous serez notifié dès confirmation.")
    else:
        messages.error(request, "Le paiement a échoué ou a été annulé. Veuillez réessayer.")

    return render(request, "transactions/payment_return.html", {
        "result": result,
        "pending": pending,
        "transaction_id": transaction_id,
    })


@login_required
def payment_simulation_view(request, tx_id):
    """Page de simulation de paiement (mode démo / test)."""
    from .payment_service import PAYMENT_METHODS

    pending = request.session.get("pending_payment", {})

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "confirm":
            _process_payment_success(request, pending, {
                "status": "success",
                "payment_method": request.POST.get("method", "mobile_money"),
                "operator": "SIMULATION",
            })
            messages.success(
                request,
                "Paiement simulé de {:,.0f} FCFA confirmé !".format(float(pending.get("amount", 0))),
            )
            request.session.pop("pending_payment", None)
            return redirect("accounts:dashboard")
        else:
            messages.warning(request, "Paiement annulé.")
            request.session.pop("pending_payment", None)
            return redirect("accounts:dashboard")

    return render(request, "transactions/payment_simulation.html", {
        "tx_id": tx_id,
        "pending": pending,
        "payment_methods": PAYMENT_METHODS,
    })


from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse


@csrf_exempt
def payment_webhook_view(request):
    """Webhook CinetPay — notification de paiement."""
    from .payment_service import verify_payment, validate_webhook_signature

    if request.method != "POST":
        return JsonResponse({"status": "error"}, status=405)

    try:
        data = json.loads(request.body) if request.body else request.POST.dict()
    except (json.JSONDecodeError, Exception):
        data = request.POST.dict()

    transaction_id = data.get("cpm_trans_id", "")
    if not transaction_id:
        return JsonResponse({"status": "error", "message": "No transaction_id"}, status=400)

    # Vérifier la signature
    signature = request.headers.get("X-CinetPay-Signature", "")
    if not validate_webhook_signature(data, signature):
        logger.warning("Webhook signature invalide pour %s", transaction_id)

    result = verify_payment(transaction_id)
    logger.info("Webhook payment %s: %s", transaction_id, result["status"])

    return JsonResponse({"status": "ok"})


def _process_payment_success(request, pending, result):
    """Traite un paiement réussi selon son type."""
    payment_type = pending.get("payment_type", "")
    reference_id = pending.get("reference_id", "")

    if payment_type == "promotion" and reference_id:
        try:
            from parcelles.models import PromotionCampaign
            campaign = PromotionCampaign.objects.get(pk=reference_id)
            campaign.status = "active"
            campaign.payment_reference = pending.get("transaction_id", "")
            campaign.start_date = timezone.now()
            from datetime import timedelta
            campaign.end_date = timezone.now() + timedelta(weeks=campaign.duration_weeks)
            campaign.save()
            logger.info("Promotion %s activée après paiement", reference_id)
        except Exception as e:
            logger.error("Erreur activation promotion: %s", e)

    elif payment_type == "escrow" and reference_id:
        try:
            tx = Transaction.objects.get(pk=reference_id)
            tx.escrow_funded = True
            tx.escrow_funded_at = timezone.now()
            tx.payment_method = "escrow"
            tx.save()
            logger.info("Séquestre %s financé", reference_id)
        except Exception as e:
            logger.error("Erreur financement séquestre: %s", e)

    elif payment_type == "certification" and reference_id:
        try:
            from accounts.models import CertificationRequest
            cert = CertificationRequest.objects.get(pk=reference_id)
            cert.status = "scheduled"
            cert.save()
            logger.info("Certification %s payée", reference_id)
        except Exception as e:
            logger.error("Erreur paiement certification: %s", e)


# ──────────────────────────────────────────────
# Scoring Financier & Simulateur
# ──────────────────────────────────────────────


@login_required
def financial_score_view(request):
    """Affichage et mise à jour du score financier."""
    from .scoring_service import compute_financial_score

    score_obj, _ = FinancialScore.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = FinancialProfileForm(request.POST, request.FILES, instance=score_obj)
        if form.is_valid():
            form.save()
            # Recalculer le score
            score_obj = compute_financial_score(request.user)
            messages.success(
                request,
                f"Score financier recalculé : {score_obj.overall_score:.0f}/100 (Grade {score_obj.grade})",
            )
            return redirect("transactions:financial_score")
    else:
        form = FinancialProfileForm(instance=score_obj)

    return render(request, "transactions/financial_score.html", {
        "form": form,
        "score": score_obj,
    })


@login_required
def simulator_view(request):
    """Simulateur d'achat-vente interactif."""
    from .scoring_service import simulate_purchase

    result = None
    parcelle = None
    parcelle_pk = request.GET.get("parcelle")

    if parcelle_pk:
        try:
            parcelle = Parcelle.objects.get(pk=parcelle_pk)
        except Parcelle.DoesNotExist:
            pass

    if request.method == "POST":
        form = SimulatorForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            result = simulate_purchase(
                property_price=data["property_price"],
                down_payment=data["down_payment"],
                duration_months=int(data["duration_months"]),
                interest_rate=data["interest_rate"],
            )

            # Sauvegarder la simulation
            sim = SimulationResult.objects.create(
                user=request.user,
                parcelle=parcelle,
                property_price=data["property_price"],
                down_payment=data["down_payment"],
                loan_amount=result["loan_amount"],
                duration_months=int(data["duration_months"]),
                interest_rate=data["interest_rate"],
                monthly_payment=result["monthly_payment"],
                total_cost=result["total_cost"],
                total_interest=result["total_interest"],
                amortization_table=result["amortization_table"],
            )

            # Vérifier la faisabilité
            try:
                score = request.user.financial_score
                if score.monthly_capacity:
                    sim.is_feasible = result["monthly_payment"] <= float(score.monthly_capacity)
                    if not sim.is_feasible:
                        sim.feasibility_notes = (
                            f"La mensualité ({result['monthly_payment']:,.0f} FCFA) "
                            f"dépasse votre capacité mensuelle ({score.monthly_capacity:,.0f} FCFA)."
                        )
                    sim.save()
            except FinancialScore.DoesNotExist:
                pass

            result["simulation_id"] = str(sim.pk)
            result["is_feasible"] = sim.is_feasible
            result["feasibility_notes"] = sim.feasibility_notes
    else:
        initial = {}
        if parcelle and parcelle.price:
            initial["property_price"] = parcelle.price
        form = SimulatorForm(initial=initial)

    return render(request, "transactions/simulator.html", {
        "form": form,
        "result": result,
        "result_json": json.dumps(result) if result else "null",
        "parcelle": parcelle,
    })


@login_required
def simulation_detail_view(request, pk):
    """Détail d'une simulation avec tableau d'amortissement."""
    simulation = get_object_or_404(SimulationResult, pk=pk, user=request.user)
    return render(request, "transactions/simulation_detail.html", {
        "simulation": simulation,
    })


@login_required
def cancel_transaction_view(request, pk):
    """Annuler une transaction."""
    tx = get_object_or_404(Transaction, pk=pk)

    if tx.buyer != request.user and tx.seller != request.user and not request.user.is_admin_role:
        messages.error(request, "Non autorisé.")
        return redirect("transactions:detail", pk=pk)

    if tx.status in ("completed", "cancelled"):
        messages.warning(request, "Cette transaction ne peut pas être annulée.")
        return redirect("transactions:detail", pk=pk)

    if request.method == "POST":
        from .transaction_service import cancel_transaction

        reason = request.POST.get("reason", "")
        try:
            cancel_transaction(tx, request.user, reason)
            messages.success(request, "Transaction annulée.")
        except ValueError as e:
            messages.error(request, str(e))
        return redirect("transactions:detail", pk=pk)

    return render(request, "transactions/cancel.html", {"transaction": tx})


@login_required
def dispute_transaction_view(request, pk):
    """Ouvrir un litige sur une transaction."""
    tx = get_object_or_404(Transaction, pk=pk)

    if tx.buyer != request.user and tx.seller != request.user:
        messages.error(request, "Seuls l'acheteur ou le vendeur peuvent ouvrir un litige.")
        return redirect("transactions:detail", pk=pk)

    if tx.status in ("cancelled", "disputed"):
        messages.warning(request, "Impossible d'ouvrir un litige sur cette transaction.")
        return redirect("transactions:detail", pk=pk)

    if request.method == "POST":
        from .transaction_service import initiate_dispute

        reason = request.POST.get("reason", "")
        if not reason:
            messages.error(request, "Veuillez décrire la raison du litige.")
            return render(request, "transactions/dispute.html", {"transaction": tx})

        try:
            initiate_dispute(tx, request.user, reason)
            messages.success(request, "Litige ouvert. L'équipe EYE-Foncier a été notifiée.")
        except ValueError as e:
            messages.error(request, str(e))
        return redirect("transactions:detail", pk=pk)

    return render(request, "transactions/dispute.html", {"transaction": tx})


@admin_required
def transaction_stats_view(request):
    """Tableau de bord statistique des transactions (admin)."""

    qs = Transaction.objects.all()

    stats = {
        "total": qs.count(),
        "by_status": list(qs.values("status").annotate(count=Count("id")).order_by("-count")),
        "total_amount": qs.filter(status="completed").aggregate(total=Sum("amount"))["total"] or 0,
        "escrow_amount": qs.filter(escrow_funded=True, escrow_released=False).aggregate(
            total=Sum("escrow_amount")
        )["total"] or 0,
        "disputes": qs.filter(status="disputed").count(),
        "completed": qs.filter(status="completed").count(),
        "cancelled": qs.filter(status="cancelled").count(),
        "recent": qs.select_related("parcelle", "buyer", "seller")[:10],
    }

    return render(request, "transactions/stats.html", {"stats": stats})


# ──────────────────────────────────────────────
# Approbation bipartite
# ──────────────────────────────────────────────


@login_required
def approve_operation_view(request, approval_pk):
    """Approuver une opération en attente."""
    approval = get_object_or_404(TransactionApproval, pk=approval_pk)
    tx = approval.transaction

    from .approval_service import _get_counterparty, OPERATION_LABELS

    counterparty = _get_counterparty(tx, approval.operation_type)
    if request.user != counterparty:
        messages.error(request, "Vous n'êtes pas autorisé à approuver cette opération.")
        return redirect("transactions:detail", pk=tx.pk)

    if approval.status != TransactionApproval.Status.PENDING:
        messages.info(request, "Cette demande a déjà été traitée.")
        return redirect("transactions:detail", pk=tx.pk)

    if request.method == "POST":
        from .approval_service import approve_operation

        try:
            approve_operation(approval, request.user)
            label = OPERATION_LABELS.get(approval.operation_type, "")
            messages.success(request, f"Opération approuvée : {label}")
        except ValueError as e:
            messages.error(request, str(e))
        return redirect("transactions:detail", pk=tx.pk)

    return render(request, "transactions/approve_operation.html", {
        "approval": approval,
        "transaction": tx,
        "label": OPERATION_LABELS.get(approval.operation_type, ""),
    })


@login_required
def reject_operation_view(request, approval_pk):
    """Refuser une opération en attente."""
    approval = get_object_or_404(TransactionApproval, pk=approval_pk)
    tx = approval.transaction

    from .approval_service import _get_counterparty, OPERATION_LABELS

    counterparty = _get_counterparty(tx, approval.operation_type)
    if request.user != counterparty:
        messages.error(request, "Vous n'êtes pas autorisé à traiter cette demande.")
        return redirect("transactions:detail", pk=tx.pk)

    if approval.status != TransactionApproval.Status.PENDING:
        messages.info(request, "Cette demande a déjà été traitée.")
        return redirect("transactions:detail", pk=tx.pk)

    if request.method == "POST":
        from .approval_service import reject_operation

        reason = request.POST.get("reason", "")
        try:
            reject_operation(approval, request.user, reason)
            messages.success(request, "Demande refusée.")
        except ValueError as e:
            messages.error(request, str(e))
        return redirect("transactions:detail", pk=tx.pk)

    return render(request, "transactions/reject_operation.html", {
        "approval": approval,
        "transaction": tx,
        "label": OPERATION_LABELS.get(approval.operation_type, ""),
    })


@login_required
def quick_approve_api(request, approval_pk):
    """Endpoint AJAX pour approbation/refus rapide depuis le dashboard."""
    if request.method != "POST":
        return JsonResponse({"error": "POST requis"}, status=405)

    from .approval_service import approve_operation, reject_operation

    approval = get_object_or_404(TransactionApproval, pk=approval_pk)
    action = request.POST.get("action", "")
    reason = request.POST.get("reason", "")

    try:
        if action == "approve":
            approve_operation(approval, request.user)
            return JsonResponse({"success": True, "message": "Opération approuvée."})
        elif action == "reject":
            reject_operation(approval, request.user, reason)
            return JsonResponse({"success": True, "message": "Demande refusée."})
        else:
            return JsonResponse({"error": "Action invalide."}, status=400)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except Exception as e:
        logger.error("Erreur quick_approve_api: %s", e, exc_info=True)
        return JsonResponse({"error": "Erreur interne, veuillez réessayer."}, status=500)


# ─── Signature électronique ──────────────────────────────
@login_required
def contract_sign_view(request, pk):
    """Signature électronique du compromis de vente."""
    tx = get_object_or_404(Transaction, pk=pk)
    user = request.user

    # Vérifier que l'utilisateur est partie prenante
    if user not in (tx.buyer, tx.seller) and not user.is_staff:
        messages.error(request, "Vous n'êtes pas autorisé à signer ce contrat.")
        return redirect("transactions:detail", pk=pk)

    # Déterminer le rôle
    if user == tx.buyer:
        signer_role = "buyer"
    elif user == tx.seller:
        signer_role = "seller"
    else:
        messages.error(request, "Seuls l'acheteur et le vendeur peuvent signer.")
        return redirect("transactions:detail", pk=pk)

    # Vérifier si déjà signé
    existing_sig = ContractSignature.objects.filter(
        transaction=tx, role=signer_role
    ).first()
    if existing_sig:
        messages.info(request, "Vous avez déjà signé ce contrat.")
        return redirect("transactions:contract_verify", pk=pk)

    if request.method == "POST":
        signature_data = request.POST.get("signature_data", "")
        if not signature_data or len(signature_data) < 100:
            messages.error(request, "Signature invalide. Veuillez dessiner votre signature.")
            return redirect("transactions:contract_sign", pk=pk)

        # Récupérer les infos du device
        ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR", "")
        device = request.META.get("HTTP_USER_AGENT", "")[:500]

        ContractSignature.objects.create(
            transaction=tx,
            signer=user,
            role=signer_role,
            signature_data=signature_data,
            ip_address=ip or None,
            device_info=device,
        )

        # Mettre à jour les flags de signature sur la transaction
        if signer_role == "buyer":
            tx.compromis_signed_buyer = True
        else:
            tx.compromis_signed_seller = True
        tx.save(update_fields=["compromis_signed_buyer", "compromis_signed_seller"])

        messages.success(request, "Contrat signé avec succès !")

        # Si les deux parties ont signé, envoyer notification
        if tx.compromis_signed_buyer and tx.compromis_signed_seller:
            try:
                from notifications.services import send_notification
                for recipient in [tx.buyer, tx.seller]:
                    send_notification(
                        recipient=recipient,
                        notification_type="transaction_status",
                        title="Compromis de vente signé",
                        message=(
                            f"Le compromis de vente pour la parcelle {tx.parcelle.lot_number} "
                            f"(Ref: {tx.reference}) a été signé par les deux parties."
                        ),
                        data={
                            "transaction_id": str(tx.pk),
                            "reference": tx.reference,
                            "parcelle_lot": tx.parcelle.lot_number,
                            "action_url": f"/transactions/{tx.pk}/",
                            "email_template": "notifications/email/transaction_status.html",
                        },
                    )
            except Exception:
                pass

        return redirect("transactions:contract_verify", pk=pk)

    # GET : afficher le formulaire de signature
    all_signatures = ContractSignature.objects.filter(transaction=tx)
    return render(request, "transactions/contract_sign.html", {
        "transaction": tx,
        "signer_role": signer_role,
        "existing_signatures": all_signatures,
    })


@login_required
def contract_verify_view(request, pk):
    """Vérification des signatures d'un contrat."""
    tx = get_object_or_404(Transaction, pk=pk)

    # Vérifier que l'utilisateur est partie prenante ou admin
    if request.user not in (tx.buyer, tx.seller) and not request.user.is_staff:
        messages.error(request, "Accès non autorisé.")
        return redirect("transactions:detail", pk=pk)

    signatures = ContractSignature.objects.filter(transaction=tx).select_related("signer")
    buyer_sig = signatures.filter(role="buyer").first()
    seller_sig = signatures.filter(role="seller").first()
    fully_signed = buyer_sig is not None and seller_sig is not None

    return render(request, "transactions/contract_verify.html", {
        "transaction": tx,
        "buyer_signature": buyer_sig,
        "seller_signature": seller_sig,
        "fully_signed": fully_signed,
    })


# ═══════════════════════════════════════════════════════
# FACTURES
# ═══════════════════════════════════════════════════════

@login_required
def invoice_list_view(request):
    """Historique des factures de l'utilisateur (ou toutes pour admin)."""
    from .models import Invoice

    user = request.user
    if user.is_admin_role or user.is_superuser:
        invoices = Invoice.objects.all().select_related("client", "parcelle")
    else:
        invoices = Invoice.objects.filter(client=user).select_related("parcelle")

    # Filtres
    inv_type = request.GET.get("type")
    if inv_type:
        invoices = invoices.filter(invoice_type=inv_type)
    inv_status = request.GET.get("status")
    if inv_status:
        invoices = invoices.filter(status=inv_status)

    total_paid = invoices.filter(status="paid").aggregate(s=Sum("total"))["s"] or 0

    return render(request, "transactions/invoice_list.html", {
        "invoices": invoices.order_by("-created_at")[:50],
        "total_paid": total_paid,
        "invoice_types": Invoice.InvoiceType.choices,
    })


@login_required
def invoice_detail_view(request, pk):
    """Détail d'une facture."""
    from .models import Invoice

    invoice = get_object_or_404(Invoice, pk=pk)
    user = request.user
    if invoice.client != user and not (user.is_admin_role or user.is_superuser):
        messages.error(request, "Vous n'êtes pas autorisé à voir cette facture.")
        return redirect("transactions:invoice_list")

    return render(request, "transactions/invoice_detail.html", {
        "invoice": invoice,
    })


@login_required
def invoice_download_pdf_view(request, pk):
    """Télécharge le PDF d'une facture."""
    from .models import Invoice

    invoice = get_object_or_404(Invoice, pk=pk)
    user = request.user
    if invoice.client != user and not (user.is_admin_role or user.is_superuser):
        messages.error(request, "Non autorisé.")
        return redirect("transactions:invoice_list")

    # Regénérer le PDF si manquant
    if not invoice.pdf_file:
        try:
            from .invoice_service import regenerate_pdf
            regenerate_pdf(invoice)
        except Exception:
            messages.error(request, "Impossible de générer le PDF.")
            return redirect("transactions:invoice_detail", pk=pk)

    if invoice.pdf_file:
        response = HttpResponse(invoice.pdf_file.read(), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{invoice.invoice_number}.pdf"'
        return response

    messages.error(request, "Le PDF n'a pas pu être généré.")
    return redirect("transactions:invoice_detail", pk=pk)
