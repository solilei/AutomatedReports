from django.urls import path

from . import views

app_name = "scoring"

urlpatterns = [
    path("programmes/", views.programme_list, name="programme_list"),
    path("programmes/new/", views.programme_create, name="programme_create"),
    path("programmes/<int:pk>/", views.programme_detail, name="programme_detail"),
    path("programmes/<int:pk>/edit/", views.programme_edit, name="programme_edit"),
    path("programmes/<int:pk>/toggle/", views.programme_toggle, name="programme_toggle"),
    path("programmes/<int:programme_pk>/subjects/new/", views.subject_create, name="subject_create"),
    path("subjects/", views.subject_list, name="subject_list"),
    path("subjects/<int:pk>/edit/", views.subject_edit, name="subject_edit"),
    path("subjects/<int:pk>/toggle/", views.subject_toggle, name="subject_toggle"),
    path("missing-scores/", views.missing_scores, name="missing_scores"),
    path("my-score-sets/", views.my_score_sets, name="my_score_sets"),
    path("groups/<str:number>/score-sets/", views.group_score_sets, name="group_score_sets"),
    path("score-sets/<int:pk>/", views.score_set_detail, name="score_set_detail"),
    path("groups/<str:number>/results/", views.results, name="results"),
    path("groups/<str:number>/export/", views.export, name="export"),
    path("groups/<str:number>/score/", views.score_go, name="score_go"),
    path("groups/<str:number>/score/<int:subject_id>/", views.score_grid, name="score_grid"),
]
