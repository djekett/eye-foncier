"""
Vues Cotation — EYE-FONCIER
Flux achat : consultation → cotation (10 %) → droits débloqués → achat définitif.
Flux boutique : vendeur/promoteur → cotation boutique → boutique active.
"""
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone

from .cotation_models import Cotation, Boutique, VerificationRequest
from .cotation_service import (
    create_achat_cotation,
    create_boutique_cotation,
    initiate_cotation_payment,
    confirm_cotation_payment,
    check_cotation_access,
    has_valid_cotation,
    advance_verification,
)
from parcelles.models import Parcelle

logger = logging.getLogger("cotation")


# ═══════════════════════════════════════════════════════════
# COTATION D'ACHAT
# ═══════════════════════════════════════════════════════════

@login_required
def cotation_create_view(request, parcelle_pk):
    """
    Page de paiement de la cotation (10 % du prix).
    Étape obligatoire avant visite et accès aux documents.
    """
    parcelle = get_object_or_404(Parcelle, pk=parcelle_pk)
    user = request.user

    # Vérifications
    if not user.is_acheteur:
        messages.error(request, "Seuls les acheteurs peuvent payer une cotation.")
        return redirect("parcelles:detail", pk=parcelle_pk)

    if parcelle.status != Parcelle.Status.DISPONIBLE:
        messages.warning(request, "Cette parcelle n'est plus disponible.")
        return redirect("parcelles:detail", pk=parcelle_pk)

    # Cotation déjà active ?
    existing = check_cotation_access(user, parcelle)
    if existing and existing.is_valid:
        messages.info(
            request,
            f"Vous avez déjà une cotation active pour cette parcelle "
            f"(Ref: {existing.reference})."
        )
        return redirect("transactions:cotation_detail", pk=existing.pk)

    # Calcul du montant
    cotation_amount = Cotation.compute_cotation_amount(parcelle.price)

    if request.method == "POST":
        payment_method = request.POST.get("payment_method", "mobile_money")

        try:
            cotation = create_achat_cotation(user, parcelle)
            result = initiate_cotation_payment(cotation, payment_method)

            # Si mode simulation, confirmer directement
            if result.get("mode") == "simulation":
                confirm_cotation_payment(cotation)
                messages.success(
                    request,
                    f"Cotation de {cotation_amount:,.0f} FCFA payée avec succès ! "
                    f"Ref: {cotation.reference}. "
                    f"Vous pouvez maintenant visiter la parcelle et consulter "
                    f"les documents filigranés."
                )
                return redirect("transactions:cotation_detail", pk=cotation.pk)

            # Mode réel : rediriger vers CinetPay
            return redirect(result["payment_url"])

        except ValueError as e:
            messages.error(request, str(e))
            return redirect("parcelles:detail", pk=parcelle_pk)

    from .payment_service import PAYMENT_METHODS

    return render(request, "transactions/cotation_create.html", {
        "parcelle": parcelle,
        "cotation_amount": cotation_amount,
        "remaining_amount": parcelle.price - cotation_amount,
        "payment_methods": PAYMENT_METHODS,
    })


@login_required
def cotation_detail_view(request, pk):
    """Détail d'une cotation avec statut et droits associés."""
    cotation = get_object_or_404(Cotation, pk=pk)

    if cotation.payer != request.user and not request.user.is_admin_role:
        messages.error(request, "Accès non autorisé.")
        return redirect("parcelles:list")

    # Récupérer la vérification associée
    verification = None
    if hasattr(cotation, "verification"):
        verification = cotation.verification

    context = {
        "cotation": cotation,
        "verification": verification,
        "can_visit": cotation.is_valid,
        "can_view_docs": cotation.is_valid,
        "can_reserve": cotation.is_valid,
    }

    return render(request, "transactions/cotation_detail.html", context)


@login_required
def cotation_callback_view(request):
    """
    Callback CinetPay après paiement de la cotation.
    Vérifie le paiement et redirige vers le détail.
    """
    transaction_id = request.GET.get("transaction_id", "")

    if not transaction_id:
        messages.error(request, "Référence de paiement manquante.")
        return redirect("parcelles:list")

    try:
        cotation = Cotation.objects.get(payment_reference=transaction_id)
    except Cotation.DoesNotExist:
        messages.error(request, "Cotation introuvable.")
        return redirect("parcelles:list")

    # Vérifier le paiement
    from .payment_service import verify_payment

    payment_data = verify_payment(transaction_id)

    if payment_data.get("status") == "success":
        if cotation.status == Cotation.Status.PENDING:
            confirm_cotation_payment(cotation, payment_data)
            messages.success(
                request,
                f"Cotation payée avec succès ! Ref: {cotation.reference}"
            )
    elif payment_data.get("status") == "pending":
        messages.info(
            request,
            "Votre paiement est en cours de traitement. "
            "Vous serez notifié dès confirmation."
        )
    else:
        messages.error(
            request,
            "Le paiement a échoué. Veuillez réessayer."
        )

    return redirect("transactions:cotation_detail", pk=cotation.pk)


@login_required
def cotation_webhook_view(request):
    """Webhook CinetPay pour confirmation de paiement (serveur-à-serveur)."""
    if request.method != "POST":
        return JsonResponse({"error": "POST requis"}, status=405)

    import json
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON invalide"}, status=400)

    transaction_id = data.get("cpm_trans_id", "")
    if not transaction_id:
        return JsonResponse({"error": "Transaction ID manquant"}, status=400)

    try:
        cotation = Cotation.objects.get(payment_reference=transaction_id)
    except Cotation.DoesNotExist:
        return JsonResponse({"error": "Cotation introuvable"}, status=404)

    from .payment_service import verify_payment

    payment_data = verify_payment(transaction_id)

    if payment_data.get("status") == "success":
        if cotation.status == Cotation.Status.PENDING:
            confirm_cotation_payment(cotation, payment_data)
            logger.info("Cotation %s confirmée par webhook", cotation.reference)

    return JsonResponse({"status": "ok"})


# ═══════════════════════════════════════════════════════════
# COTATION BOUTIQUE
# ═══════════════════════════════════════════════════════════

@login_required
def boutique_cotation_view(request):
    """Paiement de la cotation boutique pour vendeurs/promoteurs."""
    user = request.user

    if user.role not in ["vendeur", "promoteur"]:
        messages.error(
            request,
            "Seuls les vendeurs et promoteurs peuvent créer une boutique."
        )
        return redirect("accounts:dashboard")

    # Déjà une boutique active ?
    if hasattr(user, "boutique") and user.boutique.is_active:
        return redirect("transactions:boutique_dashboard")

    if request.method == "POST":
        boutique_name = request.POST.get("boutique_name", "").strip()
        payment_method = request.POST.get("payment_method", "mobile_money")

        if not boutique_name:
            messages.error(request, "Le nom de la boutique est requis.")
            return redirect("transactions:boutique_cotation")

        try:
            cotation = create_boutique_cotation(user, boutique_name)
            result = initiate_cotation_payment(cotation, payment_method)

            if result.get("mode") == "simulation":
                confirm_cotation_payment(cotation)
                messages.success(
                    request,
                    f"Boutique « {boutique_name} » créée avec succès ! "
                    f"Vous pouvez maintenant publier vos parcelles."
                )
                return redirect("transactions:boutique_dashboard")

            return redirect(result["payment_url"])

        except ValueError as e:
            messages.error(request, str(e))

    from .payment_service import PAYMENT_METHODS

    return render(request, "transactions/boutique_cotation.html", {
        "cotation_price": Cotation.BOUTIQUE_COTATION_PRICE,
        "payment_methods": PAYMENT_METHODS,
    })


@login_required
def boutique_dashboard_view(request):
    """Dashboard de la boutique du vendeur/promoteur."""
    user = request.user

    boutique = getattr(user, "boutique", None)
    if not boutique or not boutique.is_active:
        messages.info(
            request,
            "Vous devez d'abord créer votre boutique en payant la cotation."
        )
        return redirect("transactions:boutique_cotation")

    parcelles = Parcelle.objects.filter(owner=user).select_related(
        "zone"
    ).prefetch_related("medias").order_by("-created_at")

    parcelles_non_validees = parcelles.filter(is_validated=False).count()
    parcelles_en_attente = parcelles.filter(
        status="disponible", is_validated=True
    ).count()

    # Avis recus sur la boutique
    from .cotation_models import Review
    recent_reviews = Review.objects.filter(
        boutique=boutique, is_visible=True,
    ).select_related("author").order_by("-created_at")[:5]

    return render(request, "transactions/boutique_dashboard.html", {
        "boutique": boutique,
        "parcelles": parcelles,
        "parcelles_non_validees": parcelles_non_validees,
        "parcelles_en_attente": parcelles_en_attente,
        "recent_reviews": recent_reviews,
    })


# ═══════════════════════════════════════════════════════════
# VÉRIFICATION — VUES ADMIN / VÉRIFICATEUR
# ═══════════════════════════════════════════════════════════

@login_required
def verification_list_view(request):
    """Liste des vérifications (admin/vérificateur)."""
    user = request.user

    if not (user.is_admin_role or user.is_geometre):
        messages.error(request, "Accès réservé aux vérificateurs.")
        return redirect("accounts:dashboard")

    verifications = VerificationRequest.objects.select_related(
        "buyer", "seller", "parcelle", "verifier",
    )

    # Les géomètres voient seulement leurs assignations
    if user.is_geometre and not user.is_admin_role:
        verifications = verifications.filter(verifier=user)

    status_filter = request.GET.get("status", "")
    if status_filter:
        verifications = verifications.filter(status=status_filter)

    return render(request, "transactions/verification_list.html", {
        "verifications": verifications,
        "status_choices": VerificationRequest.Status.choices,
        "current_status": status_filter,
    })


@login_required
def verification_detail_view(request, pk):
    """Détail d'une vérification avec actions."""
    verification = get_object_or_404(
        VerificationRequest.objects.select_related(
            "buyer", "seller", "parcelle", "verifier", "cotation",
        ),
        pk=pk,
    )
    user = request.user

    # Accès : admin, vérificateur assigné, acheteur ou vendeur concerné
    authorized = any([
        user.is_admin_role,
        user == verification.verifier,
        user == verification.buyer,
        user == verification.seller,
    ])
    if not authorized:
        messages.error(request, "Accès non autorisé.")
        return redirect("accounts:dashboard")

    # Préparer la liste des géomètres pour l'assignation (admin)
    geometres = []
    if user.is_admin_role and not verification.verifier:
        from django.contrib.auth import get_user_model
        UserModel = get_user_model()
        geometres = UserModel.objects.filter(
            role="geometre", is_active=True
        ).order_by("first_name", "last_name")

    return render(request, "transactions/verification_detail.html", {
        "verification": verification,
        "can_manage": user.is_admin_role or user == verification.verifier,
        "geometres": geometres,
    })


@login_required
def verification_advance_view(request, pk):
    """Faire avancer le workflow de vérification."""
    verification = get_object_or_404(VerificationRequest, pk=pk)
    user = request.user

    if not (user.is_admin_role or user == verification.verifier):
        messages.error(request, "Seul le vérificateur assigné peut avancer.")
        return redirect("transactions:verification_detail", pk=pk)

    if request.method == "POST":
        new_status = request.POST.get("new_status", "")
        notes = request.POST.get("notes", "")

        try:
            advance_verification(verification, new_status, user, notes)
            messages.success(
                request,
                f"Vérification avancée : {verification.get_status_display()}"
            )
        except ValueError as e:
            messages.error(request, str(e))

    return redirect("transactions:verification_detail", pk=pk)


@login_required
def verification_assign_view(request, pk):
    """Assigner un vérificateur (admin seulement)."""
    if not request.user.is_admin_role:
        messages.error(request, "Action réservée aux administrateurs.")
        return redirect("transactions:verification_list")

    verification = get_object_or_404(VerificationRequest, pk=pk)

    if request.method == "POST":
        from django.contrib.auth import get_user_model
        User = get_user_model()

        verifier_id = request.POST.get("verifier_id", "")
        try:
            verifier = User.objects.get(pk=verifier_id)
            verification.verifier = verifier
            verification.status = VerificationRequest.Status.ASSIGNED
            verification.save(update_fields=["verifier", "status"])

            # Notifier le géomètre assigné
            try:
                from notifications.services import send_notification
                send_notification(
                    recipient=verifier,
                    notification_type="system",
                    title="Nouvelle vérification assignée",
                    message=(
                        f"Une vérification pour la parcelle « {verification.parcelle.title} » "
                        f"(Lot {verification.parcelle.lot_number}) vous a été assignée. "
                        f"Acheteur : {verification.buyer.get_full_name()}."
                    ),
                    data={
                        "verification_id": str(verification.pk),
                        "parcelle_id": str(verification.parcelle_id),
                    },
                )
            except Exception:
                pass

            messages.success(
                request,
                f"Vérification assignée à {verifier.get_full_name()}"
            )
        except User.DoesNotExist:
            messages.error(request, "Vérificateur introuvable.")

    return redirect("transactions:verification_detail", pk=pk)


# ═══════════════════════════════════════════════════════════
# BOUTIQUE PUBLIQUE & AVIS
# ═══════════════════════════════════════════════════════════

def boutique_public_view(request, slug):
    """Page publique d'une boutique avec avis et notation."""
    boutique = get_object_or_404(Boutique, slug=slug, status=Boutique.Status.ACTIVE)
    from .cotation_models import Review
    from django.db.models import Avg, Count, Q as DQ

    reviews = Review.objects.filter(
        boutique=boutique, is_visible=True,
    ).select_related("author").order_by("-created_at")

    review_stats = reviews.aggregate(
        avg_score=Avg("score"),
        total=Count("id"),
        stars_5=Count("id", filter=DQ(score=5)),
        stars_4=Count("id", filter=DQ(score=4)),
        stars_3=Count("id", filter=DQ(score=3)),
        stars_2=Count("id", filter=DQ(score=2)),
        stars_1=Count("id", filter=DQ(score=1)),
    )

    # Parcelles de la boutique
    parcelles = Parcelle.objects.filter(
        owner=boutique.owner, is_validated=True,
    ).select_related("zone").prefetch_related("medias").order_by("-created_at")

    # L'utilisateur a-t-il deja donne un avis ?
    user_review = None
    can_review = False
    if request.user.is_authenticated and request.user != boutique.owner:
        user_review = Review.objects.filter(
            author=request.user, boutique=boutique,
        ).first()
        can_review = user_review is None

    # Certification du vendeur
    from accounts.models import CertificationRequest
    seller_certified = CertificationRequest.objects.filter(
        user=boutique.owner, status="approved"
    ).exists()

    context = {
        "boutique": boutique,
        "parcelles": parcelles,
        "reviews": reviews[:20],
        "review_stats": review_stats,
        "user_review": user_review,
        "can_review": can_review,
        "seller_certified": seller_certified,
    }
    return render(request, "transactions/boutique_public.html", context)


@login_required
def boutique_review_view(request, slug):
    """Soumettre un avis sur une boutique."""
    boutique = get_object_or_404(Boutique, slug=slug, status=Boutique.Status.ACTIVE)
    from .cotation_models import Review

    if request.user == boutique.owner:
        messages.warning(request, "Vous ne pouvez pas noter votre propre boutique.")
        return redirect("transactions:boutique_public", slug=slug)

    # Anti-spam: un seul avis par boutique
    existing = Review.objects.filter(author=request.user, boutique=boutique).first()
    if existing:
        messages.info(request, "Vous avez deja donne un avis sur cette boutique.")
        return redirect("transactions:boutique_public", slug=slug)

    if request.method == "POST":
        try:
            score = int(request.POST.get("score", 0))
            if score < 1 or score > 5:
                raise ValueError("Score invalide")
        except (ValueError, TypeError):
            messages.error(request, "Note invalide (1 a 5 etoiles requises).")
            return redirect("transactions:boutique_public", slug=slug)

        comment = request.POST.get("comment", "").strip()[:1000]

        # Verifier si l'auteur a effectue une transaction avec le vendeur
        from .models import Transaction
        is_verified = Transaction.objects.filter(
            buyer=request.user, seller=boutique.owner,
            status="completed",
        ).exists()

        Review.objects.create(
            author=request.user,
            target_type=Review.TargetType.BOUTIQUE,
            boutique=boutique,
            score=score,
            comment=comment,
            is_verified=is_verified,
        )

        messages.success(request, f"Merci pour votre avis ({score}/5 etoiles) !")
        return redirect("transactions:boutique_public", slug=slug)

    return redirect("transactions:boutique_public", slug=slug)


# ═══════════════════════════════════════════════════════════
# BOUTIQUE PERSONNALISATION
# ═══════════════════════════════════════════════════════════

@login_required
def boutique_edit_view(request):
    """Formulaire de personnalisation de la boutique du vendeur."""
    user = request.user
    boutique = getattr(user, "boutique", None)
    if not boutique or not boutique.is_active:
        messages.info(request, "Vous devez d'abord creer votre boutique.")
        return redirect("transactions:boutique_cotation")

    if request.method == "POST":
        # Infos de base
        boutique.name = request.POST.get("name", boutique.name).strip()[:200]
        boutique.description = request.POST.get("description", "").strip()[:2000]
        boutique.specialty = request.POST.get("specialty", "").strip()[:200]

        # Contact
        boutique.phone = request.POST.get("phone", "").strip()[:20]
        boutique.whatsapp = request.POST.get("whatsapp", "").strip()[:20]
        boutique.whatsapp_message = request.POST.get("whatsapp_message", "").strip()[:300]
        boutique.email = request.POST.get("email", "").strip()[:254]
        boutique.address = request.POST.get("address", "").strip()[:300]
        boutique.city = request.POST.get("city", "").strip()[:100]
        boutique.commune = request.POST.get("commune", "").strip()[:100]

        # Liens
        boutique.website = request.POST.get("website", "").strip()[:200]
        boutique.facebook = request.POST.get("facebook", "").strip()[:200]
        boutique.instagram = request.POST.get("instagram", "").strip()[:100]

        # Theme
        theme = request.POST.get("theme_color", "").strip()
        if theme and len(theme) == 7 and theme.startswith("#"):
            boutique.theme_color = theme

        # Fichiers
        if "logo" in request.FILES:
            boutique.logo = request.FILES["logo"]
        if "banner" in request.FILES:
            boutique.banner = request.FILES["banner"]

        boutique.save()
        messages.success(request, "Boutique mise a jour avec succes !")
        return redirect("transactions:boutique_dashboard")

    return render(request, "transactions/boutique_edit.html", {
        "boutique": boutique,
    })


# ═══════════════════════════════════════════════════════════
# MARKETPLACE — LISTE DE TOUTES LES BOUTIQUES
# ═══════════════════════════════════════════════════════════

def boutiques_list_view(request):
    """Page marketplace : liste de toutes les boutiques actives."""
    from django.db.models import Q as DQ

    qs = Boutique.objects.filter(status=Boutique.Status.ACTIVE).select_related("owner")

    # Recherche
    search = request.GET.get("q", "").strip()
    if search:
        qs = qs.filter(
            DQ(name__icontains=search) |
            DQ(city__icontains=search) |
            DQ(commune__icontains=search) |
            DQ(specialty__icontains=search) |
            DQ(owner__first_name__icontains=search) |
            DQ(owner__last_name__icontains=search)
        )

    # Filtre par ville
    city_filter = request.GET.get("city", "")
    if city_filter:
        qs = qs.filter(city__iexact=city_filter)

    # Filtre par note minimale
    rating_filter = request.GET.get("rating", "")
    if rating_filter:
        try:
            qs = qs.filter(rating__gte=float(rating_filter))
        except (ValueError, TypeError):
            pass

    # Tri
    sort = request.GET.get("sort", "popular")
    if sort == "rating":
        qs = qs.order_by("-rating", "-total_ventes")
    elif sort == "recent":
        qs = qs.order_by("-created_at")
    elif sort == "name":
        qs = qs.order_by("name")
    else:  # popular
        qs = qs.order_by("-total_ventes", "-rating", "-total_parcelles")

    boutiques = list(qs)

    # Stats globales
    from accounts.models import CertificationRequest
    total_boutiques = len(boutiques)
    certified_owners = set(
        CertificationRequest.objects.filter(
            status="approved"
        ).values_list("user_id", flat=True)
    )
    verified_count = sum(1 for b in boutiques if b.owner_id in certified_owners)
    top_rated = [b for b in boutiques if b.rating and b.rating >= 4]

    # Villes disponibles pour le filtre
    cities = sorted(
        Boutique.objects.filter(
            status=Boutique.Status.ACTIVE
        ).exclude(city="").values_list("city", flat=True).distinct()
    )

    # Marquer les boutiques certifiees
    for b in boutiques:
        b.is_certified = b.owner_id in certified_owners

    context = {
        "boutiques": boutiques,
        "total_boutiques": total_boutiques,
        "verified_count": verified_count,
        "top_rated_count": len(top_rated),
        "cities": cities,
        "current_search": search,
        "current_city": city_filter,
        "current_rating": rating_filter,
        "current_sort": sort,
    }
    return render(request, "transactions/boutiques_list.html", context)
