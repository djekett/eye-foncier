"""
Administration des comptes — EYE-FONCIER.
Corrigé : readonly auto-fields, ProfileInline compatible Jazzmin collapsible.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db.utils import IntegrityError
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import User, Profile, AccessLog, CertificationRequest


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name = "Profil"
    verbose_name_plural = "Profil"
    fk_name = "user"
    extra = 0  # Signal crée le Profile → pas de formulaire vide en mode ajout
    min_num = 0
    max_num = 1
    # Tous les champs éditables + readonly pour les auto
    fields = (
        "avatar", "bio", "address", "city", "country",
        "id_document", "kyc_status", "trust_score", "total_sales",
    )


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = [ProfileInline]

    def save_related(self, request, form, formsets, change):
        """Gestion du conflit signal/inline pour les profils.

        Lors de la création d'un user, le signal post_save crée
        automatiquement un Profile. Si l'inline tente d'en créer un
        second, on catch l'IntegrityError et on met à jour l'existant.
        """
        try:
            super().save_related(request, form, formsets, change)
        except IntegrityError:
            # Profile déjà créé par le signal → on récupère et met à jour
            from django.db import connection
            connection.cursor()  # Reset de la transaction avortée
            user = form.instance
            profile, _ = Profile.objects.get_or_create(user=user)
            for formset in formsets:
                if formset.model == Profile:
                    for inline_form in formset.forms:
                        cd = getattr(inline_form, "cleaned_data", {})
                        if cd and not cd.get("DELETE", False):
                            for field_name, value in cd.items():
                                if field_name not in ("id", "user", "DELETE") and hasattr(profile, field_name):
                                    if value is not None and value != "":
                                        setattr(profile, field_name, value)
                            profile.save()
                            break

    list_display = [
        "email", "get_full_name", "role_color_badge", "is_verified",
        "is_active", "is_staff", "date_joined",
    ]
    list_filter = ["role", "is_verified", "is_active", "is_staff", "is_superuser"]
    search_fields = ["email", "username", "first_name", "last_name", "phone"]
    ordering = ["-date_joined"]
    list_per_page = 25

    # ── Auto-fields dans readonly pour qu'ils s'affichent ──
    readonly_fields = ["date_joined", "last_login", "created_at", "updated_at"]

    # ── Fieldsets pour édition d'un user existant ──
    fieldsets = (
        (None, {"fields": ("email", "username", "password")}),
        (_("Informations personnelles"), {
            "fields": ("first_name", "last_name", "phone"),
        }),
        (_("Rôle & Vérification"), {
            "fields": ("role", "is_verified"),
        }),
        (_("Permissions"), {
            "classes": ("collapse",),
            "fields": (
                "is_active", "is_staff", "is_superuser",
                "groups", "user_permissions",
            ),
        }),
        (_("Dates"), {
            "fields": ("last_login", "date_joined", "created_at", "updated_at"),
        }),
    )

    # ── Fieldsets pour ajout d'un nouveau user ──
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "email", "username", "first_name", "last_name",
                "role", "password1", "password2",
            ),
        }),
    )

    @admin.display(description="Rôle", ordering="role")
    def role_color_badge(self, obj):
        colors = {
            "admin": "#ef4444", "geometre": "#3b82f6",
            "vendeur": "#f59e0b", "acheteur": "#22c55e", "visiteur": "#6b7280",
        }
        color = colors.get(obj.role, "#6b7280")
        label = obj.get_role_display()
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;'
            'border-radius:12px;font-size:11px;font-weight:600;">{}</span>',
            color, label,
        )


@admin.register(AccessLog)
class AccessLogAdmin(admin.ModelAdmin):
    list_display = [
        "timestamp", "user", "action", "resource_type",
        "resource_id", "ip_address",
    ]
    list_filter = ["action", "resource_type"]
    search_fields = ["user__email", "resource_id", "ip_address"]
    date_hierarchy = "timestamp"
    readonly_fields = [
        "id", "user", "action", "resource_type", "resource_id",
        "ip_address", "user_agent", "details", "timestamp",
    ]
    list_per_page = 50

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(CertificationRequest)
class CertificationRequestAdmin(admin.ModelAdmin):
    list_display = [
        "user", "cert_type", "status_color_badge",
        "preferred_date", "created_at",
    ]
    list_filter = ["cert_type", "status"]
    search_fields = ["user__email", "user__first_name", "user__last_name"]
    readonly_fields = ["id", "created_at", "updated_at"]
    date_hierarchy = "created_at"
    list_per_page = 25
    actions = ["approve_certifications", "reject_certifications"]

    @admin.display(description="Statut")
    def status_color_badge(self, obj):
        colors = {
            "pending": "#f59e0b", "scheduled": "#3b82f6",
            "in_review": "#8b5cf6", "approved": "#22c55e", "rejected": "#ef4444",
        }
        color = colors.get(obj.status, "#6b7280")
        label = obj.get_status_display()
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;'
            'border-radius:12px;font-size:11px;font-weight:600;">{}</span>',
            color, label,
        )

    @admin.action(description="Approuver les certifications sélectionnées")
    def approve_certifications(self, request, queryset):
        updated = queryset.update(status="approved", reviewed_by=request.user)
        self.message_user(request, "{} certification(s) approuvée(s).".format(updated))

    @admin.action(description="Rejeter les certifications sélectionnées")
    def reject_certifications(self, request, queryset):
        updated = queryset.update(status="rejected", reviewed_by=request.user)
        self.message_user(request, "{} certification(s) rejetée(s).".format(updated))
