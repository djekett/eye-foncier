"""Vues du contenu — EYE-FONCIER.
Articles, annonces, documentation.
"""
from django.shortcuts import render, get_object_or_404
from django.db.models import Q
from django.utils import timezone

from .models import Article, Announcement, Documentation, Category


def article_list_view(request):
    """Liste des articles publiés."""
    articles = Article.objects.filter(status="published").select_related("author", "category")

    # Filtrage par catégorie
    category_slug = request.GET.get("category")
    category = None
    if category_slug:
        category = Category.objects.filter(slug=category_slug).first()
        if category:
            articles = articles.filter(category=category)

    # Filtrage par tag
    tag = request.GET.get("tag", "").strip()
    if tag:
        articles = articles.filter(tags__icontains=tag)

    # Recherche
    q = request.GET.get("q", "").strip()
    if q:
        articles = articles.filter(
            Q(title__icontains=q) | Q(content__icontains=q) | Q(excerpt__icontains=q)
        )

    featured = articles.filter(is_featured=True)[:3]
    categories = Category.objects.all()

    context = {
        "articles": articles[:30],
        "featured": featured,
        "categories": categories,
        "current_category": category,
        "current_tag": tag,
        "search_query": q,
    }
    return render(request, "content/article_list.html", context)


def article_detail_view(request, slug):
    """Détail d'un article."""
    article = get_object_or_404(Article, slug=slug, status="published")

    # Incrémenter les vues
    Article.objects.filter(pk=article.pk).update(views_count=article.views_count + 1)

    # Articles liés
    related = Article.objects.filter(
        status="published", category=article.category,
    ).exclude(pk=article.pk)[:4]

    context = {
        "article": article,
        "related_articles": related,
    }
    return render(request, "content/article_detail.html", context)


def announcements_view(request):
    """Liste des annonces actives."""
    now = timezone.now()
    announcements = Announcement.objects.filter(
        is_active=True,
    ).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    )

    context = {"announcements": announcements}
    return render(request, "content/announcements.html", context)


def documentation_view(request):
    """Page d'accueil documentation."""
    docs = Documentation.objects.filter(
        is_published=True, parent__isnull=True,
    )
    context = {"docs": docs}
    return render(request, "content/documentation.html", context)


def doc_detail_view(request, slug):
    """Détail d'une page de documentation."""
    doc = get_object_or_404(Documentation, slug=slug, is_published=True)
    children = doc.children.filter(is_published=True)

    # Navigation : toutes les pages de même type
    siblings = Documentation.objects.filter(
        is_published=True, doc_type=doc.doc_type, parent=doc.parent,
    ).exclude(pk=doc.pk)

    context = {
        "doc": doc,
        "children": children,
        "siblings": siblings,
    }
    return render(request, "content/doc_detail.html", context)
