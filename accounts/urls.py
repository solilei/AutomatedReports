from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("pending/", views.pending, name="pending"),
    path("password/set/", views.password_set, name="password_set"),
]
