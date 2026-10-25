from django.urls import path

from . import views

app_name = "roster"

urlpatterns = [
    path("roster/upload/", views.upload, name="upload"),
]
