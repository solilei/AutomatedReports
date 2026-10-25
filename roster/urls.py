from django.urls import path

from . import views

app_name = "roster"

urlpatterns = [
    path("groups/", views.group_list, name="group_list"),
    path("groups/go/", views.group_go, name="group_go"),
    path("groups/<str:number>/", views.group_detail, name="group_detail"),
    path("groups/<str:number>/lock/", views.group_lock, name="group_lock"),
    path("groups/<str:number>/unlock/", views.group_unlock, name="group_unlock"),
    path("groups/<str:number>/archive/", views.group_archive, name="group_archive"),
    path("groups/<str:number>/unarchive/", views.group_unarchive, name="group_unarchive"),
    path("groups/<str:number>/delete/", views.group_delete, name="group_delete"),
    path("roster/upload/", views.upload, name="upload"),
    path("roster/upload/<int:pk>/columns/", views.upload_columns, name="upload_columns"),
    path("roster/upload/<int:pk>/preview/", views.upload_preview, name="upload_preview"),
]
