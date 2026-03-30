"""Vues de gestion des comptes utilisateurs — EYE-FONCIER."""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib import messages
from django.views.generic import DetailView, ListView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import Http404, JsonResponse
from django.utils import timezone

from .models import (
    User, Profile, AccessLog, CertificationRequest,
    Partner, PartnerReferral, ReferralProgram, AmbassadorProfile,
)
from .forms import (
    CustomUserCreationForm,
    CustomLoginForm,
    ProfileUpdateForm,
    UserUpdateForm,
)
from .decorators import admin_required


# ─── Inscription ────────────────────────────────────────
def register_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")
    ref_code = request.GET.get("ref", "")
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend="accounts.backends.EmailBackend")
            messages.success(request, f"Bienvenue {user.first_name} ! Compte créé avec succès.")
            AccessLog.objects.create(
                user=user, action=AccessLog.ActionType.LOGIN,
                ip_address=_get_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
                details={"method": "register"},
            )
            # Parrainage : si code référent valide
            ref_post = request.POST.get("ref_code", ref_code)
            if ref_post:
                _handle_referral(user, ref_post)
            return redirect("accounts:dashboard")
    else:
        form = CustomUserCreationForm()
    return render(request, "accounts/register.html", {"form": form, "ref_code": ref_code})


# ─── Connexion ──────────────────────────────────────────
class CustomLoginView(LoginView):
    form_class = CustomLoginForm
    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        AccessLog.objects.create(
            user=self.request.user, action=AccessLog.ActionType.LOGIN,
            ip_address=_get_ip(self.request),
            user_agent=self.request.META.get("HTTP_USER_AGENT", ""),
        )
        messages.success(self.request, f"Bon retour, {self.request.user.first_name} !")
        return response


class CustomLogoutView(LogoutView):
    next_page = "websig:home"


# ─── Profil (mon propre profil) ─────────────────────────
@login_required
def profile_view(request):
    # Garantir que le Profile existe (auto-create si signal raté)
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        user_form = UserUpdateForm(request.POST, instance=request.user)
        profile_form = ProfileUpdateForm(request.POST, request.FILES, instance=profile)
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, "Profil mis à jour avec succès.")
            return redirect("accounts:profile")
    else:
        user_form = UserUpdateForm(instance=request.user)
        profile_form = ProfileUpdateForm(instance=profile)

    # Certification en cours ?
    certification = CertificationRequest.objects.filter(user=request.user).order_by("-created_at").first()
    return render(request, "accounts/profile.html", {
        "user_form": user_form,
        "profile_form": profile_form,
        "certification": certification,
    })


# ─── Profil public (tous les rôles, pas seulement vendeur) ─────
class SellerProfileView(DetailView):
    """Profil public d'un utilisateur.

    BUG FIX : l'ancienne version filtrait role=VENDEUR, ce qui provoquait
    un 404 pour les superusers et les géomètres. Maintenant tous les
    utilisateurs ont un profil public accessible.
    """
    model = User
    template_name = "accounts/seller_profile.html"
    context_object_name = "seller"

    def get_queryset(self):
        # Tous les utilisateurs actifs (plus de filtre par rôle)
        return User.objects.filter(is_active=True)

    def get_object(self, queryset=None):
        """Surcharge pour garantir que le profil existe."""
        obj = super().get_object(queryset)
        # Auto-créer le Profile s'il n'existe pas
        Profile.objects.get_or_create(user=obj)
        return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        seller = self.object
        user = self.request.user

        # Parcelles du vendeur
        parcelles_qs = seller.parcelles.filter(is_validated=True)
        ctx["parcelles"] = parcelles_qs
        ctx["parcelles_count"] = parcelles_qs.count()

        # Montrer les infos privées uniquement aux connectés
        ctx["show_private"] = user.is_authenticated

        # Certification
        cert = CertificationRequest.objects.filter(
            user=seller, status="approved"
        ).first()
        ctx["is_certified"] = cert is not None

        return ctx


# ─── Tableau de bord ────────────────────────────────────
@login_required
def dashboard_view(request):
    user = request.user
    from parcelles.models import Parcelle
    from transactions.models import Transaction

    if user.is_vendeur or getattr(user, "is_promoteur", False):
        from django.db.models import Sum, Count
        parcelles_qs = user.parcelles.all()
        transactions_qs = user.sales.all()
        completed_sales = transactions_qs.filter(status="completed")
        total_revenue = completed_sales.aggregate(s=Sum("amount"))["s"] or 0
        total_views = parcelles_qs.aggregate(s=Sum("views_count"))["s"] or 0
        stats = {
            "parcelles_count": parcelles_qs.count(),
            "reservations_count": transactions_qs.filter(status="reserved").count(),
            "documents_count": sum(p.documents.count() for p in parcelles_qs[:50]),
            "transactions_count": transactions_qs.count(),
            # KPIs vendeur
            "total_revenue": total_revenue,
            "total_views": total_views,
            "parcelles_disponible": parcelles_qs.filter(status="disponible").count(),
            "parcelles_reserve": parcelles_qs.filter(status="reserve").count(),
            "parcelles_vendu": parcelles_qs.filter(status="vendu").count(),
            "pending_validation": parcelles_qs.filter(is_validated=False).count(),
            "completed_sales": completed_sales.count(),
        }
        recent_parcelles = parcelles_qs.order_by("-created_at")[:5]
        recent_transactions = transactions_qs.order_by("-created_at")[:5]
    elif user.is_acheteur:
        transactions_qs = user.purchases.all()
        stats = {
            "parcelles_count": 0,
            "reservations_count": transactions_qs.filter(status="reserved").count(),
            "documents_count": 0,
            "transactions_count": transactions_qs.count(),
        }
        recent_parcelles = Parcelle.objects.filter(is_validated=True, status="disponible")[:5]
        recent_transactions = transactions_qs[:5]
    elif user.is_admin_role or user.is_geometre or user.is_superuser:
        from django.db.models import Sum, Count, Avg, Q as DQ
        from datetime import timedelta

        all_parcelles = Parcelle.objects.all()
        all_transactions = Transaction.objects.all()
        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)

        # KPIs globaux admin
        completed_tx = all_transactions.filter(status="completed")
        total_revenue = completed_tx.aggregate(s=Sum("amount"))["s"] or 0
        revenue_30d = completed_tx.filter(
            updated_at__gte=thirty_days_ago
        ).aggregate(s=Sum("amount"))["s"] or 0

        # Taux de conversion : réservations → completed
        total_reserved = all_transactions.filter(
            status__in=["reserved", "escrow_funded", "docs_validated", "paid", "completed"]
        ).count()
        total_completed = completed_tx.count()
        conversion_rate = round(
            (total_completed / total_reserved * 100) if total_reserved > 0 else 0, 1
        )

        # Utilisateurs
        total_users = User.objects.count()
        users_30d = User.objects.filter(date_joined__gte=thirty_days_ago).count()
        users_by_role = dict(
            User.objects.values_list("role").annotate(c=Count("id")).values_list("role", "c")
        )

        # Parcelles par statut
        parcelles_by_status = dict(
            all_parcelles.values_list("status").annotate(c=Count("id")).values_list("status", "c")
        )
        parcelles_pending_validation = all_parcelles.filter(is_validated=False).count()

        stats = {
            "parcelles_count": all_parcelles.count(),
            "reservations_count": all_transactions.filter(status="reserved").count(),
            "documents_count": 0,
            "transactions_count": all_transactions.count(),
            # KPIs avancés (admin uniquement)
            "total_revenue": total_revenue,
            "revenue_30d": revenue_30d,
            "conversion_rate": conversion_rate,
            "total_users": total_users,
            "users_30d": users_30d,
            "users_by_role": users_by_role,
            "parcelles_disponible": parcelles_by_status.get("disponible", 0),
            "parcelles_reserve": parcelles_by_status.get("reserve", 0),
            "parcelles_vendu": parcelles_by_status.get("vendu", 0),
            "parcelles_pending_validation": parcelles_pending_validation,
            "tx_pending": all_transactions.filter(
                status__in=["pending", "reserved", "escrow_funded"]
            ).count(),
            "tx_completed": total_completed,
            "tx_cancelled": all_transactions.filter(status="cancelled").count(),
        }
        recent_parcelles = all_parcelles.order_by("-created_at")[:5]
        recent_transactions = all_transactions.order_by("-created_at")[:5]
    else:
        stats = {"parcelles_count": 0, "reservations_count": 0, "documents_count": 0, "transactions_count": 0}
        recent_parcelles = Parcelle.objects.filter(is_validated=True, status="disponible")[:5]
        recent_transactions = Transaction.objects.none()

    recent_logs = AccessLog.objects.filter(user=user).order_by("-timestamp")[:10]
    if user.is_admin_role or user.is_superuser:
        recent_logs = AccessLog.objects.all().order_by("-timestamp")[:20]

    # Certification
    certification = CertificationRequest.objects.filter(user=user).order_by("-created_at").first()

    # ── Approbations en attente ──
    from transactions.models import TransactionApproval

    if user.is_vendeur or getattr(user, "is_promoteur", False):
        pending_for_me = TransactionApproval.objects.filter(
            status="pending",
            transaction__seller=user,
            operation_type__in=["reserve", "escrow_fund", "docs_confirm"],
        ).select_related("transaction", "transaction__parcelle", "requested_by").order_by("-created_at")
    elif user.is_acheteur:
        pending_for_me = TransactionApproval.objects.filter(
            status="pending",
            transaction__buyer=user,
            operation_type="compromis",
        ).select_related("transaction", "transaction__parcelle", "requested_by").order_by("-created_at")
    else:
        pending_for_me = TransactionApproval.objects.none()

    pending_by_me = TransactionApproval.objects.filter(
        status="pending",
        requested_by=user,
    ).select_related("transaction", "transaction__parcelle").order_by("-created_at")

    context = {
        "user": user, "stats": stats,
        "recent_parcelles": recent_parcelles,
        "recent_transactions": recent_transactions,
        "recent_logs": recent_logs,
        "certification": certification,
        "pending_for_me": pending_for_me,
        "pending_by_me": pending_by_me,
        "pending_approvals_count": pending_for_me.count(),
    }

    # ── Cotations (acheteur) ──
    if user.is_acheteur:
        from transactions.cotation_models import Cotation
        cotations_qs = Cotation.objects.filter(payer=user).order_by("-created_at")
        context["my_cotations"] = cotations_qs[:5]
        context["active_cotations"] = cotations_qs.filter(status=Cotation.Status.VALIDATED)
        stats["cotations_count"] = cotations_qs.filter(
            status__in=[Cotation.Status.VALIDATED, Cotation.Status.PAID]
        ).count()

    # ── Boutique (vendeur / promoteur) ──
    if user.is_vendeur or getattr(user, "is_promoteur", False):
        boutique = getattr(user, "boutique", None)
        context["boutique"] = boutique
        context["has_boutique"] = boutique is not None and boutique.is_active

    # ── Vérifications (admin / géomètre) ──
    if user.is_admin_role or user.is_geometre or user.is_superuser:
        from transactions.cotation_models import VerificationRequest
        if user.is_admin_role or user.is_superuser:
            verifs_qs = VerificationRequest.objects.exclude(
                status__in=["completed", "cancelled"],
            ).select_related("parcelle", "buyer", "seller", "verifier")
        else:
            verifs_qs = VerificationRequest.objects.filter(
                verifier=user,
            ).exclude(
                status__in=["completed", "cancelled"],
            ).select_related("parcelle", "buyer", "seller")
        stats["verifications_pending"] = verifs_qs.count()
        context["pending_verifications"] = verifs_qs[:10]

        # Stats cotations globales (admin)
        if user.is_admin_role or user.is_superuser:
            from transactions.cotation_models import Cotation
            stats["cotations_total"] = Cotation.objects.filter(
                status=Cotation.Status.VALIDATED,
            ).count()

    return render(request, "accounts/dashboard.html", context)


# ─── Certification ──────────────────────────────────────
@login_required
def certification_request_view(request):
    """Demande de certification — Badge de confiance."""
    existing = CertificationRequest.objects.filter(
        user=request.user, status__in=["pending", "scheduled"]
    ).first()

    if request.method == "POST":
        if existing:
            messages.info(request, "Vous avez déjà une demande de certification en cours.")
            return redirect("accounts:certification")

        cert_type = request.POST.get("cert_type", "standard")
        message = request.POST.get("message", "")
        preferred_date = request.POST.get("preferred_date", "")

        cert = CertificationRequest.objects.create(
            user=request.user,
            cert_type=cert_type,
            message=message,
            preferred_date=preferred_date or "",
        )
        messages.success(
            request,
            "Demande de certification soumise ! Notre équipe vous contactera "
            "sous 48h pour planifier la visio-vérification."
        )
        return redirect("accounts:certification")

    return render(request, "accounts/certification.html", {
        "existing": existing,
        "cert_types": CertificationRequest.CertType.choices,
    })


@login_required
def certification_chat_api(request):
    """API pour l'assistant EYE-FONCIER (chatbot polyvalent)."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    import json
    try:
        data = json.loads(request.body)
    except Exception:
        data = {}
    user_msg = data.get("message", "").strip()
    if not user_msg:
        return JsonResponse({"reply": "Veuillez poser votre question."})

    user = request.user
    lower = user_msg.lower()

    # ── 1. Salutations ──
    if any(w in lower for w in ["bonjour", "salut", "hello", "bonsoir", "hey", "coucou", "yo"]):
        reply = (
            f'Bonjour {user.first_name} ! <i class="bi bi-hand-wave"></i>\n\n'
            "Je suis l'assistant EYE-FONCIER. Comment puis-je vous aider ?\n\n"
            '<i class="bi bi-house-door"></i> Parcelles & terrains\n'
            '<i class="bi bi-bar-chart-line"></i> Transactions & paiements\n'
            '<i class="bi bi-patch-check"></i> Certification de compte\n'
            '<i class="bi bi-graph-up-arrow"></i> Score financier\n'
            '<i class="bi bi-map"></i> Carte interactive\n'
            '<i class="bi bi-file-earmark-text"></i> Documents & contrats\n\n'
            "Tapez un sujet ou posez votre question !"
        )

    # ── 2. Parcelles / Terrains ──
    elif any(w in lower for w in ["parcelle", "terrain", "lot", "cherch", "acheter", "vendre", "bien"]):
        from parcelles.models import Parcelle
        total = Parcelle.objects.filter(is_validated=True).count()
        dispo = Parcelle.objects.filter(is_validated=True, status="disponible").count()
        reply = (
            f'<i class="bi bi-house-door"></i> Actuellement sur EYE-FONCIER :\n\n'
            f"• {total} parcelle(s) disponibles au total\n"
            f"• {dispo} terrain(s) disponibles a l'achat\n\n"
            '<i class="bi bi-arrow-right-circle"></i> Voir toutes les parcelles : /parcelles/\n'
            '<i class="bi bi-map"></i> Explorer sur la carte : /carte/\n\n'
            "Utilisez les filtres (type, prix, surface) pour affiner votre recherche."
        )

    # ── 3. Transactions ──
    elif any(w in lower for w in ["transaction", "achat", "reserv", "escrow", "statut"]):
        from django.db.models import Q
        from transactions.models import Transaction
        txns = Transaction.objects.filter(
            Q(buyer=user) | Q(seller=user)
        )
        total = txns.count()
        actives = txns.exclude(status__in=["completed", "cancelled"]).count()
        if total > 0:
            reply = (
                f'<i class="bi bi-bar-chart-line"></i> Vos transactions :\n\n'
                f"• {total} transaction(s) au total\n"
                f"• {actives} en cours\n\n"
                '<i class="bi bi-arrow-right-circle"></i> Voir le detail : /transactions/\n\n'
                "Pour toute question sur une transaction, indiquez son numero."
            )
        else:
            reply = (
                '<i class="bi bi-bar-chart-line"></i> Vous n\'avez pas encore de transaction.\n\n'
                "Pour acheter un terrain :\n"
                "1. Trouvez une parcelle sur /parcelles/\n"
                "2. Demandez un bon de visite\n"
                "3. Reservez le terrain\n"
                "4. Finalisez le paiement securise\n\n"
                '<i class="bi bi-arrow-right-circle"></i> Explorer les parcelles : /parcelles/'
            )

    # ── 4. Score financier ──
    elif any(w in lower for w in ["score", "eligib", "financ", "capacit", "grade"]):
        from transactions.models import FinancialScore
        score = FinancialScore.objects.filter(user=user).order_by("-created_at").first()
        if score:
            reply = (
                f'<i class="bi bi-graph-up-arrow"></i> Votre score financier :\n\n'
                f"• Grade : {score.grade}\n"
                f"• Score global : {score.total_score}/100\n"
                f"• Capacite d'achat max : {score.max_purchase_capacity:,.0f} FCFA\n\n"
                '<i class="bi bi-arrow-right-circle"></i> Mettre a jour : /transactions/score-financier/'
            )
        else:
            reply = (
                '<i class="bi bi-graph-up-arrow"></i> Vous n\'avez pas encore de score financier.\n\n'
                "Le score financier evalue votre capacite d'achat.\n"
                "Il prend en compte votre KYC, revenus et historique.\n\n"
                '<i class="bi bi-arrow-right-circle"></i> Calculer mon score : /transactions/score-financier/'
            )

    # ── 5. Certification ──
    elif any(w in lower for w in ["certifi", "badge", "confiance", "verif"]):
        cert = CertificationRequest.objects.filter(user=user).order_by("-created_at").first()
        if cert:
            status_map = {
                "pending": "En attente",
                "scheduled": "Planifiee",
                "in_review": "En examen",
                "approved": 'Approuvee <i class="bi bi-check-circle-fill text-success"></i>',
                "rejected": 'Refusee <i class="bi bi-x-circle-fill text-danger"></i>',
            }
            reply = (
                f'<i class="bi bi-patch-check"></i> Votre certification :\n\n'
                f"• Type : {cert.get_cert_type_display()}\n"
                f"• Statut : {status_map.get(cert.status, cert.status)}\n\n"
                "Pour obtenir le Badge de Confiance :\n"
                "1. Standard — Upload de pieces (Gratuit)\n"
                "2. Visio — Appel video 15min (5 000 F)\n"
                "3. Premium — Visite terrain (25 000 F)\n\n"
                '<i class="bi bi-arrow-right-circle"></i> Gerer ma certification : /compte/certification/'
            )
        else:
            reply = (
                '<i class="bi bi-patch-check"></i> Obtenez votre Badge de Confiance !\n\n'
                "3 options disponibles :\n"
                "1. Standard — Upload CNI + titre foncier (Gratuit)\n"
                "2. Visio-Verification — Appel video 15min (5 000 F)\n"
                "3. Premium — Visite terrain par geometre (25 000 F)\n\n"
                '<i class="bi bi-arrow-right-circle"></i> Demander : /compte/certification/'
            )

    # ── 6. Tarifs ──
    elif any(w in lower for w in ["prix", "cout", "tarif", "combien", "paiement", "frais"]):
        reply = (
            '<i class="bi bi-currency-exchange"></i> Tarifs EYE-FONCIER :\n\n'
            '<i class="bi bi-file-earmark-text"></i> Certification :\n'
            "• Standard : Gratuit\n"
            "• Visio : 5 000 FCFA\n"
            "• Premium : 25 000 FCFA\n\n"
            '<i class="bi bi-megaphone"></i> Promotion de parcelle :\n'
            "• Standard : 5 000 F/semaine\n"
            "• Premium : 15 000 F/semaine\n"
            "• Boost : 25 000 F/semaine\n\n"
            '<i class="bi bi-lock"></i> Caution vendeur : 50 000 F (remboursable)'
        )

    # ── 7. Visites ──
    elif any(w in lower for w in ["visite", "bon", "voir terrain", "rdv terrain"]):
        from transactions.models import BonDeVisite
        visites = BonDeVisite.objects.filter(buyer=user).count()
        reply = (
            f'<i class="bi bi-ticket-perforated"></i> Bons de visite :\n\n'
            f"• Vous avez {visites} bon(s) de visite\n\n"
            "Comment ca marche :\n"
            "1. Choisissez une parcelle disponible\n"
            "2. Demandez un bon de visite gratuit\n"
            "3. Le vendeur confirme le creneau\n"
            "4. Visitez le terrain avec le bon\n\n"
            '<i class="bi bi-arrow-right-circle"></i> Trouver un terrain : /parcelles/'
        )

    # ── 8. Carte interactive ──
    elif any(w in lower for w in ["carte", "map", "localisation", "sig", "geograph"]):
        reply = (
            '<i class="bi bi-map"></i> Carte interactive EYE-FONCIER\n\n'
            "Explorez tous les terrains sur la carte :\n"
            "• Vue satellite et cadastrale\n"
            "• Filtres par zone et type\n"
            "• Mesure de distances\n"
            "• Parcelles a proximite\n\n"
            '<i class="bi bi-arrow-right-circle"></i> Ouvrir la carte : /carte/'
        )

    # ── 9. Documents ──
    elif any(w in lower for w in ["document", "titre", "contrat", "compromis", "acte"]):
        reply = (
            '<i class="bi bi-file-earmark-text"></i> Documents sur EYE-FONCIER :\n\n'
            "Types de documents disponibles :\n"
            "• Titre foncier (certificat officiel)\n"
            "• Plan cadastral (technique)\n"
            "• Compromis de vente (accord)\n"
            "• Attestation de propriete\n\n"
            "Les documents sont securises et accessibles\n"
            "depuis la fiche de chaque parcelle.\n\n"
            '<i class="bi bi-exclamation-triangle"></i> Certains documents sont reserves aux acheteurs verifies.'
        )

    # ── 10. Notifications ──
    elif any(w in lower for w in ["notification", "alerte", "message", "notif"]):
        from notifications.models import Notification
        unread = Notification.objects.filter(
            user=user, is_read=False, channel="inapp"
        ).count()
        reply = (
            f'<i class="bi bi-bell"></i> Notifications :\n\n'
            f"• {unread} notification(s) non lue(s)\n\n"
            "Types d'alertes :\n"
            "• Nouvelles parcelles correspondant a vos criteres\n"
            "• Mises a jour de transactions\n"
            "• Confirmations de paiement\n"
            "• Resultats de matching\n\n"
            '<i class="bi bi-arrow-right-circle"></i> Voir mes notifications : /notifications/'
        )

    # ── 11. Promotions ──
    elif any(w in lower for w in ["promouvoir", "promotion", "boost", "visibilite", "pub"]):
        reply = (
            '<i class="bi bi-megaphone"></i> Promotion de parcelles :\n\n'
            "3 plans disponibles :\n"
            '<i class="bi bi-3-circle"></i> Standard — 5 000 F/sem : visibilite standard\n'
            '<i class="bi bi-2-circle"></i> Premium — 15 000 F/sem : badge \'Recommande\'\n'
            '<i class="bi bi-1-circle"></i> Boost — 25 000 F/sem : top resultats + push\n\n'
            "Le Smart Matching cible automatiquement\n"
            "les acheteurs correspondant a votre terrain.\n\n"
            '<i class="bi bi-arrow-right-circle"></i> Promouvoir : depuis la fiche de votre parcelle'
        )

    # ── 12. Profil / KYC ──
    elif any(w in lower for w in ["profil", "kyc", "identite", "piece", "compte", "photo"]):
        profile = user.profile if hasattr(user, "profile") else None
        kyc_status = profile.kyc_status if profile else "pending"
        kyc_map = {
            "pending": "Non soumis",
            "submitted": "En cours de verification",
            "verified": 'Verifie <i class="bi bi-check-circle-fill text-success"></i>',
            "rejected": 'Refuse <i class="bi bi-x-circle-fill text-danger"></i>',
        }
        avatar_icon = '<i class="bi bi-check-circle-fill text-success"></i>' if (profile and profile.avatar) else '<i class="bi bi-x-circle-fill text-danger"></i>'
        reply = (
            f'<i class="bi bi-person-circle"></i> Votre profil :\n\n'
            f"• Nom : {user.get_full_name()}\n"
            f"• Role : {user.get_role_display()}\n"
            f"• KYC : {kyc_map.get(kyc_status, kyc_status)}\n"
            f"• Avatar : {'Defini ' + avatar_icon if (profile and profile.avatar) else 'Non defini ' + avatar_icon}\n\n"
            '<i class="bi bi-arrow-right-circle"></i> Modifier mon profil : /compte/profil/\n'
            '<i class="bi bi-arrow-right-circle"></i> Certification : /compte/certification/'
        )

    # ── 13. RDV ──
    elif any(w in lower for w in ["rdv", "rendez", "date", "quand", "disponib", "horaire"]):
        reply = (
            '<i class="bi bi-calendar-event"></i> Creneaux de visio-verification :\n\n'
            "Lundi - Vendredi : 9h - 17h\n"
            "Samedi : 9h - 12h\n\n"
            "Indiquez votre date preferee dans le\n"
            "formulaire de certification.\n\n"
            '<i class="bi bi-arrow-right-circle"></i> Demander un RDV : /compte/certification/'
        )

    # ── 14. Contact humain ──
    elif any(w in lower for w in ["humain", "agent", "operateur", "aide", "parler", "contact", "telephone"]):
        reply = (
            '<i class="bi bi-headset"></i> Contactez notre equipe !\n\n'
            '<i class="bi bi-envelope"></i> eyeafrica07@gmail.com\n'
            '<i class="bi bi-telephone"></i> +225 07 09 42 25 51\n'
            '<i class="bi bi-geo-alt"></i> Yamoussoukro, Cote d\'Ivoire\n\n'
            "Horaires : Lun-Ven 9h-17h, Sam 9h-12h\n"
            "Temps de reponse moyen : 2h en jour ouvre."
        )

    # ── 15. Merci / Remerciement ──
    elif any(w in lower for w in ["merci", "super", "genial", "parfait", "excellent", "top"]):
        reply = (
            f'Avec plaisir {user.first_name} ! <i class="bi bi-emoji-smile"></i>\n\n'
            "N'hesitez pas si vous avez d'autres questions.\n"
            "Je suis la pour vous aider !"
        )

    # ── Fallback ──
    else:
        reply = (
            f'Merci {user.first_name} ! Je suis l\'assistant EYE-FONCIER. <i class="bi bi-robot"></i>\n\n'
            "Je peux vous aider sur :\n"
            '<i class="bi bi-house-door"></i> **Parcelles** — recherche, filtres, details\n'
            '<i class="bi bi-bar-chart-line"></i> **Transactions** — statut, paiements\n'
            '<i class="bi bi-patch-check"></i> **Certification** — badge de confiance\n'
            '<i class="bi bi-graph-up-arrow"></i> **Score financier** — eligibilite\n'
            '<i class="bi bi-file-earmark-text"></i> **Documents** — titres, contrats\n'
            '<i class="bi bi-megaphone"></i> **Promotion** — visibilite de vos terrains\n'
            '<i class="bi bi-map"></i> **Carte** — localisation des terrains\n'
            '<i class="bi bi-bell"></i> **Notifications** — alertes\n\n'
            "Tapez un de ces sujets pour en savoir plus !"
        )

    return JsonResponse({"reply": reply})


# ─── Admin : Logs ──────────────────────────────────────
class AccessLogListView(LoginRequiredMixin, ListView):
    """Journal d'activite — tous les utilisateurs voient leurs propres logs,
    les admins/staff voient tous les logs."""
    model = AccessLog
    template_name = "accounts/access_logs.html"
    context_object_name = "logs"
    paginate_by = 50

    def get_queryset(self):
        user = self.request.user
        if user.is_admin_role or user.is_staff or user.is_superuser:
            qs = AccessLog.objects.all()
        else:
            qs = AccessLog.objects.filter(user=user)

        # Filtrage par action (optionnel)
        action = self.request.GET.get("action")
        if action:
            qs = qs.filter(action=action)

        # Filtrage par date (optionnel)
        date_from = self.request.GET.get("date_from")
        date_to = self.request.GET.get("date_to")
        if date_from:
            qs = qs.filter(timestamp__date__gte=date_from)
        if date_to:
            qs = qs.filter(timestamp__date__lte=date_to)

        return qs.select_related("user").order_by("-timestamp")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["is_admin_view"] = self.request.user.is_admin_role or self.request.user.is_staff or self.request.user.is_superuser
        ctx["action_choices"] = AccessLog.ActionType.choices
        ctx["selected_action"] = self.request.GET.get("action", "")
        return ctx


# ═══════════════════════════════════════════════════════
# Phase 6 : Espace Partenaires
# ═══════════════════════════════════════════════════════

def partner_list_view(request):
    """Liste des partenaires institutionnels."""
    partner_type = request.GET.get("type", "")
    qs = Partner.objects.filter(is_active=True)
    if partner_type:
        qs = qs.filter(partner_type=partner_type)
    return render(request, "accounts/partner_list.html", {
        "partners": qs,
        "partner_types": Partner.PartnerType.choices,
        "selected_type": partner_type,
    })


def partner_detail_view(request, pk):
    """Détail d'un partenaire + formulaire de demande de contact."""
    partner = get_object_or_404(Partner, pk=pk, is_active=True)
    return render(request, "accounts/partner_detail.html", {"partner": partner})


@login_required
def partner_referral_view(request, pk):
    """Soumettre une demande de mise en relation avec un partenaire."""
    partner = get_object_or_404(Partner, pk=pk, is_active=True)
    if request.method == "POST":
        referral_type = request.POST.get("referral_type", "")
        notes = request.POST.get("notes", "")
        PartnerReferral.objects.create(
            partner=partner,
            user=request.user,
            referral_type=referral_type,
            notes=notes,
        )
        # Notification au partenaire
        try:
            from notifications.services import send_notification
            send_notification(
                recipient=request.user,
                notification_type="transaction_status",
                title=f"Demande envoyée — {partner.name}",
                message=f"Votre demande de {referral_type or 'contact'} a été envoyée à {partner.name}. "
                        f"Un conseiller vous contactera sous 48h.",
                data={"partner_name": partner.name},
            )
        except Exception:
            pass
        messages.success(request, f"Votre demande a été envoyée à {partner.name}.")
        return redirect("accounts:partner_detail", pk=partner.pk)
    return render(request, "accounts/partner_referral.html", {"partner": partner})


# ═══════════════════════════════════════════════════════
# Phase 7 : Parrainage & Programme d'affiliation
# ═══════════════════════════════════════════════════════

@login_required
def referral_dashboard_view(request):
    """Dashboard parrainage : code, lien de partage, stats."""
    # Générer un code de parrainage si inexistant
    referral_code = f"EYF-{request.user.username[:6].upper()}-{str(request.user.pk)[:4].upper()}"

    referrals = ReferralProgram.objects.filter(referrer=request.user).select_related("referred")
    stats = {
        "total_invited": referrals.count(),
        "registered": referrals.filter(status="registered").count() + referrals.filter(status="converted").count(),
        "converted": referrals.filter(status="converted").count(),
        "total_earnings": sum(r.reward_amount for r in referrals if r.reward_claimed),
    }
    return render(request, "accounts/referral_dashboard.html", {
        "referral_code": referral_code,
        "referrals": referrals,
        "stats": stats,
    })


@login_required
def ambassador_apply_view(request):
    """Candidature au programme ambassadeur."""
    existing = AmbassadorProfile.objects.filter(user=request.user).first()
    if existing:
        return redirect("accounts:ambassador_dashboard")

    if request.method == "POST":
        import secrets
        code = f"AMB-{secrets.token_hex(4).upper()}"
        AmbassadorProfile.objects.create(
            user=request.user,
            ambassador_code=code,
        )
        messages.success(request, "Votre candidature ambassadeur a été acceptée ! Bienvenue dans le programme.")
        return redirect("accounts:ambassador_dashboard")

    return render(request, "accounts/ambassador_apply.html")


@login_required
def ambassador_dashboard_view(request):
    """Dashboard ambassadeur avec stats et commissions."""
    ambassador = get_object_or_404(AmbassadorProfile, user=request.user)
    return render(request, "accounts/ambassador_dashboard.html", {
        "ambassador": ambassador,
    })


# ═══════════════════════════════════════════════════════
# Phase 10 : Modération Admin
# ═══════════════════════════════════════════════════════

@admin_required
def admin_moderation_view(request):
    """Dashboard de modération admin : KYC + Certifications."""
    kyc_pending = Profile.objects.filter(kyc_status="submitted").select_related("user")
    cert_pending = CertificationRequest.objects.filter(
        status__in=["pending", "scheduled", "in_review"]
    ).select_related("user").order_by("-created_at")
    return render(request, "accounts/admin_moderation.html", {
        "kyc_pending": kyc_pending,
        "cert_pending": cert_pending,
        "kyc_count": kyc_pending.count(),
        "cert_count": cert_pending.count(),
    })


@admin_required
def admin_kyc_review_view(request, pk):
    """Examen d'une demande KYC."""
    profile = get_object_or_404(Profile, pk=pk)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "approve":
            profile.kyc_status = "verified"
            profile.user.is_verified = True
            profile.user.save(update_fields=["is_verified"])
            profile.save(update_fields=["kyc_status"])
            messages.success(request, f"KYC de {profile.user.get_full_name()} approuvé.")
        elif action == "reject":
            profile.kyc_status = "rejected"
            profile.save(update_fields=["kyc_status"])
            messages.warning(request, f"KYC de {profile.user.get_full_name()} rejeté.")
        # Notification
        try:
            from notifications.services import send_notification
            result = "approuvé" if action == "approve" else "rejeté"
            send_notification(
                recipient=profile.user,
                notification_type="transaction_status",
                title=f"Vérification KYC {result}",
                message=f"Votre vérification d'identité a été {result}.",
                data={"result": action},
            )
        except Exception:
            pass
        return redirect("accounts:admin_moderation")
    return render(request, "accounts/admin_kyc_review.html", {"profile": profile})


@admin_required
def admin_certification_review_view(request, pk):
    """Examen d'une demande de certification."""
    cert = get_object_or_404(CertificationRequest, pk=pk)
    if request.method == "POST":
        action = request.POST.get("action")
        notes = request.POST.get("admin_notes", "")
        cert.admin_notes = notes
        cert.reviewed_by = request.user
        if action == "approve":
            cert.status = "approved"
            # Mettre à jour le trust_score du vendeur
            profile = getattr(cert.user, "profile", None)
            if profile:
                profile.trust_score = min(profile.trust_score + 2, 10)
                profile.save(update_fields=["trust_score"])
            messages.success(request, f"Certification de {cert.user.get_full_name()} approuvée.")
        elif action == "schedule":
            cert.status = "scheduled"
            scheduled_date = request.POST.get("scheduled_at", "")
            if scheduled_date:
                from django.utils.dateparse import parse_datetime
                cert.scheduled_at = parse_datetime(scheduled_date)
            messages.info(request, f"RDV programmé pour {cert.user.get_full_name()}.")
        elif action == "reject":
            cert.status = "rejected"
            messages.warning(request, f"Certification de {cert.user.get_full_name()} rejetée.")
        cert.save()
        # Notification
        try:
            from notifications.services import send_notification
            status_label = {"approved": "approuvée", "scheduled": "programmée", "rejected": "rejetée"}.get(cert.status, cert.status)
            send_notification(
                recipient=cert.user,
                notification_type="transaction_status",
                title=f"Certification {status_label}",
                message=f"Votre demande de certification ({cert.get_cert_type_display()}) a été {status_label}."
                        + (f" Notes : {notes}" if notes else ""),
                data={"cert_type": cert.cert_type, "status": cert.status},
            )
        except Exception:
            pass
        return redirect("accounts:admin_moderation")
    return render(request, "accounts/admin_certification_review.html", {"cert": cert})


# ─── Utilitaires ───────────────────────────────────────
def _handle_referral(new_user, ref_code):
    """Traite un code de parrainage à l'inscription."""
    try:
        # Chercher un ambassadeur ou un utilisateur avec ce code
        ambassador = AmbassadorProfile.objects.filter(
            ambassador_code=ref_code, is_active=True
        ).select_related("user").first()
        if ambassador:
            referrer = ambassador.user
            ambassador.total_referrals += 1
            ambassador.save(update_fields=["total_referrals"])
        else:
            # Code parrain classique (format EYF-XXX-XXX)
            parts = ref_code.split("-")
            if len(parts) >= 2:
                username_part = parts[1].lower()
                referrer = User.objects.filter(username__istartswith=username_part).first()
            else:
                return
            if not referrer:
                return

        # Créer la relation de parrainage
        if not ReferralProgram.objects.filter(referred=new_user).exists():
            ReferralProgram.objects.create(
                referrer=referrer,
                referred=new_user,
                referral_code=ref_code,
                status="registered",
            )
            # Notifier le parrain
            try:
                from notifications.services import send_notification
                send_notification(
                    recipient=referrer,
                    notification_type="transaction_status",
                    title="Nouveau filleul inscrit !",
                    message=f"{new_user.get_full_name() or new_user.email} s'est inscrit grâce à votre lien de parrainage.",
                    data={"referred_email": new_user.email},
                )
            except Exception:
                pass
    except Exception:
        pass


def _get_ip(request):
    x = request.META.get("HTTP_X_FORWARDED_FOR")
    return x.split(",")[0].strip() if x else request.META.get("REMOTE_ADDR")