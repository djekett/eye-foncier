"""Administration documents — EYE-FONCIER.
Audit complet : format_html sécurisé.
"""
from django.contrib import admin
from django.utils.html import format_html
from .models import ParcelleDocument, DocumentAccessLog


@admin.register(ParcelleDocument)
class ParcelleDocumentAdmin(admin.ModelAdmin):
    list_display = [
        "title", "parcelle", "doc_type", "confidentiality_badge",
        "is_verified", "uploaded_by", "created_at",
    ]
    list_filter = ["doc_type", "confidentiality", "is_verified"]
    search_fields = ["title", "parcelle__lot_number", "uploaded_by__email"]
    readonly_fields = ["id", "file_hash", "created_at", "updated_at"]
    date_hierarchy = "created_at"
    list_per_page = 25
    actions = ["verify_documents"]

    @admin.display(description="Confidentialité")
    def confidentiality_badge(self, obj):
        colors = {"public": "#22c55e", "buyer_only": "#f59e0b", "private": "#ef4444"}
        color = colors.get(obj.confidentiality, "#6b7280")
        label = obj.get_confidentiality_display()
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;'
            'border-radius:12px;font-size:11px;font-weight:600;">{}</span>',
            color, label,
        )

    @admin.action(description="Marquer comme vérifié")
    def verify_documents(self, request, queryset):
        updated = queryset.update(is_verified=True)
        self.message_user(request, "{} document(s) vérifié(s).".format(updated))


@admin.register(DocumentAccessLog)
class DocumentAccessLogAdmin(admin.ModelAdmin):
    list_display = ["timestamp", "document", "user", "action", "ip_address"]
    list_filter = ["action"]
    search_fields = ["user__email", "document__title"]
    date_hierarchy = "timestamp"
    readonly_fields = ["id", "document", "user", "ip_address", "action", "timestamp"]
    list_per_page = 50

    def has_add_permission(self, request):
        return False
