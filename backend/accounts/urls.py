from django.urls import path
from .views import login_view, logout_view, security_view

urlpatterns = [
    path("login/", login_view, name="accounts-login"),
    path("logout/", logout_view, name="accounts-logout"),
    path("security/", security_view, name="accounts-security"),
]