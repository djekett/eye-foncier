"""Modèles de contenu — EYE-FONCIER.
Articles de blog, annonces officielles, documentation.
"""
import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _


class Category(models.Model):
    """Catégorie de contenu."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("nom"), max_length=100)
    slug = models.SlugField(unique=True, max_length=120)
    icon = models.CharField(
        _("icône Bootstrap"), max_length=50, default="bi-folder",
        help_text="Classe CSS Bootstrap Icons (ex: bi-house, bi-map)",
    )
    order = models.PositiveIntegerField(_("ordre"), default=0)

    class Meta:
        verbose_name = _("Catégorie")
        verbose_name_plural = _("Catégories")
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Article(models.Model):
    """Article de blog / guide."""

    class Status(models.TextChoices):
        DRAFT = "draft", _("Brouillon")
        PUBLISHED = "published", _("Publié")
        ARCHIVED = "archived", _("Archivé")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(_("titre"), max_length=300)
    slug = models.SlugField(unique=True, max_length=350)
    excerpt = models.TextField(_("extrait"), max_length=500, blank=True)
    content = models.TextField(_("contenu"))
    cover_image = models.ImageField(
        _("image de couverture"),
        upload_to="content/articles/%Y/%m/", blank=True,
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name="articles",
    )
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="articles",
    )
    tags = models.CharField(
        _("tags"), max_length=500, blank=True,
        help_text="Tags séparés par des virgules",
    )

    status = models.CharField(
        _("statut"), max_length=15,
        choices=Status.choices, default=Status.DRAFT,
    )
    is_featured = models.BooleanField(_("mis en avant"), default=False)
    views_count = models.PositiveIntegerField(_("vues"), default=0)

    published_at = models.DateTimeField(_("date de publication"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Article")
        verbose_name_plural = _("Articles")
        ordering = ["-published_at", "-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:350]
        if self.status == "published" and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    @property
    def tag_list(self):
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(",") if t.strip()]

    @property
    def reading_time(self):
        words = len(self.content.split())
        return max(1, round(words / 200))


class Announcement(models.Model):
    """Annonce officielle EYE-FONCIER."""

    class Priority(models.TextChoices):
        INFO = "info", _("Information")
        IMPORTANT = "important", _("Important")
        URGENT = "urgent", _("Urgent")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(_("titre"), max_length=300)
    content = models.TextField(_("contenu"))
    priority = models.CharField(
        _("priorité"), max_length=15,
        choices=Priority.choices, default=Priority.INFO,
    )
    is_active = models.BooleanField(_("active"), default=True)
    is_pinned = models.BooleanField(_("épinglée"), default=False)

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name="announcements",
    )
    expires_at = models.DateTimeField(_("expire le"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Annonce")
        verbose_name_plural = _("Annonces")
        ordering = ["-is_pinned", "-created_at"]

    def __str__(self):
        return self.title

    @property
    def is_expired(self):
        if not self.expires_at:
            return False
        return timezone.now() > self.expires_at


class Documentation(models.Model):
    """Page de documentation / guide utilisateur."""

    class DocType(models.TextChoices):
        GUIDE = "guide", _("Guide utilisateur")
        FAQ = "faq", _("FAQ")
        LEGAL = "legal", _("Mentions légales")
        PROCEDURE = "procedure", _("Procédure")
        API_DOC = "api", _("Documentation API")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(_("titre"), max_length=300)
    slug = models.SlugField(unique=True, max_length=350)
    content = models.TextField(_("contenu"))
    doc_type = models.CharField(
        _("type"), max_length=15,
        choices=DocType.choices, default=DocType.GUIDE,
    )
    icon = models.CharField(
        _("icône"), max_length=50, default="bi-book",
    )
    order = models.PositiveIntegerField(_("ordre"), default=0)
    is_published = models.BooleanField(_("publié"), default=True)
    parent = models.ForeignKey(
        "self", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="children",
        verbose_name=_("page parente"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Documentation")
        verbose_name_plural = _("Documentation")
        ordering = ["order", "title"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:350]
        super().save(*args, **kwargs)
