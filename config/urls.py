from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("ent/", include("exam.urls")),
    path("", include("quiz.urls")),
]
