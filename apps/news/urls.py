from django.urls import path

from apps.news import views

urlpatterns = [
    path("", views.ArticleListAPI.as_view()),
    path("home/", views.HomeAPI.as_view()),
    path("<slug:slug>/", views.ArticleDetailAPI.as_view()),
]
