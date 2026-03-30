from django.urls import path
from . import views

app_name = "content"

urlpatterns = [
    # Articles / Blog
    path("articles/", views.article_list_view, name="articles"),
    path("articles/<slug:slug>/", views.article_detail_view, name="article_detail"),

    # Annonces
    path("annonces/", views.announcements_view, name="announcements"),

    # Documentation
    path("documentation/", views.documentation_view, name="documentation"),
    path("documentation/<slug:slug>/", views.doc_detail_view, name="doc_detail"),
]
