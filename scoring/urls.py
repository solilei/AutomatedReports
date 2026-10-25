from django.urls import path

from . import views

app_name = "scoring"

urlpatterns = [
    path("subjects/", views.subject_list, name="subject_list"),
    path("subjects/new/", views.subject_create, name="subject_create"),
    path("subjects/<int:pk>/edit/", views.subject_edit, name="subject_edit"),
    path("subjects/<int:pk>/toggle/", views.subject_toggle, name="subject_toggle"),
    path("my-score-sets/", views.my_score_sets, name="my_score_sets"),
    path("groups/<str:number>/score-sets/", views.group_score_sets, name="group_score_sets"),
    path("score-sets/<int:pk>/", views.score_set_detail, name="score_set_detail"),
    path("groups/<str:number>/results/", views.results, name="results"),
    path("groups/<str:number>/score/", views.score_go, name="score_go"),
    path("groups/<str:number>/score/<int:subject_id>/", views.score_grid, name="score_grid"),
]
