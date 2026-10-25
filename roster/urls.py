from django.urls import path

from . import views

app_name = "roster"

urlpatterns = [
    path("groups/", views.group_list, name="group_list"),
    path("groups/go/", views.group_go, name="group_go"),
    path("groups/<str:number>/", views.group_detail, name="group_detail"),
    path("roster/upload/", views.upload, name="upload"),
    path("roster/upload/<int:pk>/columns/", views.upload_columns, name="upload_columns"),
    path("roster/upload/<int:pk>/preview/", views.upload_preview, name="upload_preview"),
]
