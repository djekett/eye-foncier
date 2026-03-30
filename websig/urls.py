from django.urls import path
from . import views

app_name = "websig"

urlpatterns = [
    path("", views.home_view, name="home"),
    path("carte/", views.map_view, name="map"),
]
