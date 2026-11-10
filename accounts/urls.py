from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("microsoft/login/", views.microsoft_login, name="microsoft_login"),
    path("microsoft/callback/", views.microsoft_callback, name="microsoft_callback"),
    path("mfa/setup/", views.mfa_setup, name="mfa_setup"),
    path("mfa/verify/", views.mfa_verify, name="mfa_verify"),
    path("pending/", views.pending, name="pending"),
    path("password/set/", views.password_set, name="password_set"),
    path("manage/", views.user_list, name="user_list"),
    path("manage/new/", views.user_create, name="user_create"),
    path("manage/<int:pk>/approve/", views.user_approve, name="user_approve"),
    path("manage/<int:pk>/subjects/", views.user_subjects, name="user_subjects"),
    path("manage/<int:pk>/deactivate/", views.user_deactivate, name="user_deactivate"),
    path("manage/<int:pk>/reactivate/", views.user_reactivate, name="user_reactivate"),
    path("manage/<int:pk>/reset/", views.user_reset, name="user_reset"),
]
