"""Administration du contenu — EYE-FONCIER."""
from django.contrib import admin
from django.utils.html import format_html
from .models import Category, Article, Announcement, Documentation


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "icon", "article_count", "order"]
    prepopulated_fields = {"slug": ("name",)}
    list_editable = ["order"]

    @admin.display(description="Articles")
    def article_count(self, obj):
        return obj.articles.count()


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = [
        "title", "author", "category", "status_badge",
        "is_featured", "views_count", "published_at",
    ]
    list_filter = ["status", "category", "is_featured"]
    search_fields = ["title", "content", "tags"]
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ["views_count", "created_at", "updated_at"]
    list_editable = ["is_featured"]
    date_hierarchy = "created_at"
    list_per_page = 25
    actions = ["publish_articles", "archive_articles"]

    fieldsets = (
        (None, {"fields": ("title", "slug", "excerpt", "content", "cover_image")}),
        ("Catégorisation", {"fields": ("author", "category", "tags")}),
        ("Publication", {"fields": ("status", "is_featured", "published_at")}),
        ("Stats", {"classes": ("collapse",), "fields": ("views_count", "created_at", "updated_at")}),
    )

    @admin.display(description="Statut")
    def status_badge(self, obj):
        colors = {"draft": "#6b7280", "published": "#22c55e", "archived": "#f59e0b"}
        color = colors.get(obj.status, "#6b7280")
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;'
            'border-radius:12px;font-size:11px">{}</span>',
            color, obj.get_status_display(),
        )

    @admin.action(description="Publier les articles sélectionnés")
    def publish_articles(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(status="published", published_at=timezone.now())
        self.message_user(request, "{} article(s) publié(s).".format(updated))

    @admin.action(description="Archiver les articles sélectionnés")
    def archive_articles(self, request, queryset):
        updated = queryset.update(status="archived")
        self.message_user(request, "{} article(s) archivé(s).".format(updated))


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ["title", "priority_badge", "is_active", "is_pinned", "author", "created_at"]
    list_filter = ["priority", "is_active", "is_pinned"]
    search_fields = ["title", "content"]
    list_editable = ["is_active", "is_pinned"]
    readonly_fields = ["created_at", "updated_at"]
    list_per_page = 25

    @admin.display(description="Priorité")
    def priority_badge(self, obj):
        colors = {"info": "#3b82f6", "important": "#f59e0b", "urgent": "#ef4444"}
        color = colors.get(obj.priority, "#6b7280")
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;'
            'border-radius:12px;font-size:11px">{}</span>',
            color, obj.get_priority_display(),
        )


@admin.register(Documentation)
class DocumentationAdmin(admin.ModelAdmin):
    list_display = ["title", "doc_type", "icon", "parent", "order", "is_published"]
    list_filter = ["doc_type", "is_published"]
    search_fields = ["title", "content"]
    prepopulated_fields = {"slug": ("title",)}
    list_editable = ["order", "is_published"]
    list_per_page = 25
