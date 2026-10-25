from django.urls import path

from . import views

app_name = "roster"

urlpatterns = [
    path("roster/upload/", views.upload, name="upload"),
    path("roster/upload/<int:pk>/columns/", views.upload_columns, name="upload_columns"),
    path("roster/upload/<int:pk>/preview/", views.upload_preview, name="upload_preview"),
]
