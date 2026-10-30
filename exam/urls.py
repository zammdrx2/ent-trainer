from django.urls import path

from . import views

urlpatterns = [
    path("", views.exam_home, name="exam_home"),
    path("start/<int:variant_id>/", views.exam_start, name="exam_start"),
    path("<int:attempt_id>/", views.exam_take, name="exam_take"),
    path("<int:attempt_id>/save/", views.exam_save, name="exam_save"),
    path("<int:attempt_id>/finish/", views.exam_finish, name="exam_finish"),
    path("<int:attempt_id>/result/", views.exam_result, name="exam_result"),
]
