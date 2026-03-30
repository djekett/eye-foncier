"""
Service de Scoring Financier — EYE-FONCIER
Évalue la capacité d'achat d'un acquéreur selon 4 critères pondérés.
"""
import logging
from decimal import Decimal

from django.utils import timezone

from .models import FinancialScore, Transaction

logger = logging.getLogger(__name__)

# Pondérations des composantes
WEIGHT_KYC = 0.25
WEIGHT_REVENUE = 0.30
WEIGHT_HISTORY = 0.25
WEIGHT_MOBILE_MONEY = 0.20

# Multiplicateurs de capacité par grade
GRADE_MULTIPLIERS = {
    "A": Decimal("42"),  # 3.5 ans de revenus
    "B": Decimal("36"),  # 3 ans
    "C": Decimal("30"),  # 2.5 ans
    "D": Decimal("18"),  # 1.5 ans
    "E": Decimal("12"),  # 1 an
}


def compute_financial_score(user):
    """
    Calcule le score financier global d'un utilisateur.

    Returns:
        FinancialScore — instance mise à jour
    """
    score_obj, _ = FinancialScore.objects.get_or_create(user=user)

    # ── 1. Score KYC (0-100) ──
    score_kyc = _compute_kyc_score(user)

    # ── 2. Score Revenus (0-100) ──
    score_revenue = _compute_revenue_score(score_obj)

    # ── 3. Score Historique (0-100) ──
    score_history = _compute_history_score(user)

    # ── 4. Score Mobile Money (0-100) ──
    score_mm = _compute_mobile_money_score(user, score_obj)

    # ── Score global pondéré ──
    overall = (
        WEIGHT_KYC * score_kyc
        + WEIGHT_REVENUE * score_revenue
        + WEIGHT_HISTORY * score_history
        + WEIGHT_MOBILE_MONEY * score_mm
    )

    # ── Grade ──
    grade = _score_to_grade(overall)

    # ── Capacité d'achat ──
    monthly_capacity = None
    max_capacity = None
    if score_obj.revenue_declared and score_obj.revenue_declared > 0:
        # Capacité mensuelle = 35% des revenus (ratio d'endettement standard)
        monthly_capacity = score_obj.revenue_declared * Decimal("0.35")
        multiplier = GRADE_MULTIPLIERS.get(grade, Decimal("12"))
        max_capacity = score_obj.revenue_declared * multiplier

    # ── Sauvegarde ──
    score_obj.score_kyc = score_kyc
    score_obj.score_revenue = score_revenue
    score_obj.score_history = score_history
    score_obj.score_mobile_money = score_mm
    score_obj.overall_score = round(overall, 1)
    score_obj.grade = grade
    score_obj.monthly_capacity = monthly_capacity
    score_obj.max_purchase_capacity = max_capacity
    score_obj.breakdown = {
        "kyc": {"score": round(score_kyc, 1), "weight": WEIGHT_KYC},
        "revenue": {"score": round(score_revenue, 1), "weight": WEIGHT_REVENUE},
        "history": {"score": round(score_history, 1), "weight": WEIGHT_HISTORY},
        "mobile_money": {"score": round(score_mm, 1), "weight": WEIGHT_MOBILE_MONEY},
        "computed_at": timezone.now().isoformat(),
    }
    score_obj.save()

    logger.info(
        "Score financier calculé pour %s : %.1f (%s)", user, overall, grade
    )
    return score_obj


def simulate_purchase(property_price, down_payment, duration_months, interest_rate):
    """
    Simule un achat-vente avec calcul d'amortissement.

    Args:
        property_price: Decimal — prix du bien en FCFA
        down_payment: Decimal — apport initial en FCFA
        duration_months: int — durée en mois
        interest_rate: Decimal — taux d'intérêt annuel en %

    Returns:
        dict — résultat de la simulation
    """
    loan_amount = property_price - down_payment

    if loan_amount <= 0:
        return {
            "loan_amount": 0,
            "monthly_payment": 0,
            "total_cost": property_price,
            "total_interest": 0,
            "amortization_table": [],
        }

    # Taux mensuel
    monthly_rate = float(interest_rate) / 100 / 12

    if monthly_rate == 0:
        monthly_payment = float(loan_amount) / duration_months
    else:
        # Formule d'amortissement standard
        # M = P * [r(1+r)^n] / [(1+r)^n - 1]
        factor = (1 + monthly_rate) ** duration_months
        monthly_payment = float(loan_amount) * (monthly_rate * factor) / (factor - 1)

    # Tableau d'amortissement
    table = []
    remaining = float(loan_amount)
    total_interest = 0

    for month in range(1, duration_months + 1):
        interest = remaining * monthly_rate
        principal = monthly_payment - interest
        remaining = max(0, remaining - principal)
        total_interest += interest

        table.append({
            "month": month,
            "payment": round(monthly_payment),
            "principal": round(principal),
            "interest": round(interest),
            "remaining": round(remaining),
        })

    total_cost = float(down_payment) + (monthly_payment * duration_months)

    return {
        "loan_amount": round(float(loan_amount)),
        "monthly_payment": round(monthly_payment),
        "total_cost": round(total_cost),
        "total_interest": round(total_interest),
        "amortization_table": table,
    }


def check_buyer_eligibility(user, parcelle):
    """
    Vérifie l'éligibilité d'un acheteur pour une parcelle.

    Returns:
        dict — {eligible, score, reason, recommended_down_payment}
    """
    score = compute_financial_score(user)

    result = {
        "eligible": True,
        "score": score,
        "grade": score.grade,
        "overall_score": score.overall_score,
        "reason": "",
        "recommended_down_payment": None,
    }

    price = parcelle.price
    if not price or price <= 0:
        result["reason"] = "Prix de la parcelle non défini."
        return result

    if not score.max_purchase_capacity:
        result["eligible"] = False
        result["reason"] = (
            "Revenus non déclarés. Veuillez compléter votre profil financier."
        )
        return result

    if price <= score.max_purchase_capacity:
        result["reason"] = "Vous êtes éligible pour cette parcelle."
    else:
        result["eligible"] = False
        deficit = price - score.max_purchase_capacity
        result["reason"] = (
            f"Le prix dépasse votre capacité d'achat de {deficit:,.0f} FCFA. "
            f"Un apport initial plus élevé pourrait compenser."
        )
        # Apport recommandé = différence
        result["recommended_down_payment"] = deficit

    return result


# ──────────────────────────────────────────────
# Fonctions internes de scoring
# ──────────────────────────────────────────────


def _compute_kyc_score(user):
    """Score basé sur la vérification d'identité."""
    score = 0
    profile = getattr(user, "profile", None)
    if not profile:
        return 0

    # Statut KYC
    kyc_status = profile.kyc_status
    if kyc_status == "verified":
        score += 50
    elif kyc_status == "submitted":
        score += 25
    elif kyc_status == "pending":
        score += 5

    # Compte vérifié
    if user.is_verified:
        score += 15

    # Téléphone renseigné
    if user.phone:
        score += 10

    # Ancienneté du compte
    days_since_creation = (timezone.now() - user.created_at).days
    if days_since_creation > 180:
        score += 15
    elif days_since_creation > 90:
        score += 10
    elif days_since_creation > 30:
        score += 5

    # Profil complet
    if profile.address and profile.city:
        score += 10

    return min(score, 100)


def _compute_revenue_score(score_obj):
    """Score basé sur les revenus déclarés."""
    score = 0

    if not score_obj.revenue_declared or score_obj.revenue_declared <= 0:
        return 0

    revenue = float(score_obj.revenue_declared)

    # Paliers de revenus (FCFA/mois)
    if revenue >= 1_000_000:
        score += 40
    elif revenue >= 500_000:
        score += 30
    elif revenue >= 300_000:
        score += 20
    elif revenue >= 150_000:
        score += 10
    else:
        score += 5

    # Justificatif uploadé
    if score_obj.revenue_proof:
        score += 20

    # Type d'emploi
    employment_bonuses = {
        "fonctionnaire": 20,
        "salarie": 15,
        "entrepreneur": 10,
        "independant": 8,
        "informel": 5,
    }
    score += employment_bonuses.get(score_obj.employment_type, 0)

    # Employeur renseigné
    if score_obj.employer_name:
        score += 10

    return min(score, 100)


def _compute_history_score(user):
    """Score basé sur l'historique des transactions."""
    score = 0

    completed = Transaction.objects.filter(
        buyer=user, status=Transaction.Status.COMPLETED
    ).count()
    cancelled = Transaction.objects.filter(
        buyer=user, status=Transaction.Status.CANCELLED
    ).count()
    disputed = Transaction.objects.filter(
        buyer=user, status=Transaction.Status.DISPUTED
    ).count()

    # Transactions complétées
    score += min(completed * 15, 60)

    # Pas d'annulations/litiges
    if completed > 0 and cancelled == 0 and disputed == 0:
        score += 25
    elif disputed > 0:
        score -= 15

    # Bonus fidélité
    total = completed + cancelled + disputed
    if total > 0 and completed / total >= 0.8:
        score += 15

    return max(min(score, 100), 0)


def _compute_mobile_money_score(user, score_obj):
    """Score basé sur la vérification Mobile Money."""
    score = 0

    # Compte MM vérifié
    if score_obj.mobile_money_verified:
        score += 50

    # Paiements réussis sur la plateforme (via CinetPay)
    successful_payments = Transaction.objects.filter(
        buyer=user,
        payment_method=Transaction.PaymentMethod.MOBILE_MONEY,
        status__in=[
            Transaction.Status.COMPLETED,
            Transaction.Status.ESCROW_FUNDED,
            Transaction.Status.PAID,
        ],
    ).count()
    score += min(successful_payments * 10, 50)

    return min(score, 100)


def _score_to_grade(score):
    """Convertit un score en grade."""
    if score >= 80:
        return "A"
    elif score >= 60:
        return "B"
    elif score >= 40:
        return "C"
    elif score >= 20:
        return "D"
    return "E"
