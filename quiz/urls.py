from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import LocalizedLoginForm

urlpatterns = [
    path("", views.home, name="home"),
    path("lang/", views.set_language, name="set_language"),
    path("signup/", views.signup, name="signup"),
    path("login/", auth_views.LoginView.as_view(authentication_form=LocalizedLoginForm), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("test/start/", views.start_test, name="start_mixed"),
    path("test/start/<int:topic_id>/", views.start_test, name="start_topic"),
    path("test/<int:attempt_id>/", views.take_test, name="take_test"),
    path("test/<int:attempt_id>/result/", views.result, name="result"),
    path("stats/", views.stats, name="stats"),
]
