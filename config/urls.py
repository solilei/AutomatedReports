from django.urls import include, path

from roster.views import home

urlpatterns = [
    path("", home, name="home"),
    path("accounts/", include("accounts.urls")),
]
