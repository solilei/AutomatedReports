from django.urls import path

from . import views

app_name = "scoring"

urlpatterns = [
    path("subjects/", views.subject_list, name="subject_list"),
    path("subjects/new/", views.subject_create, name="subject_create"),
    path("subjects/<int:pk>/edit/", views.subject_edit, name="subject_edit"),
    path("subjects/<int:pk>/toggle/", views.subject_toggle, name="subject_toggle"),
    path("groups/<str:number>/score/", views.score_go, name="score_go"),
    path("groups/<str:number>/score/<int:subject_id>/", views.score_grid, name="score_grid"),
]
