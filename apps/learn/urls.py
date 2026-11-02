from django.urls import path

from apps.learn import views

urlpatterns = [
    path("home/", views.HomeAPI.as_view()),
    path("articles/", views.ArticleListAPI.as_view()),
    path("articles/<slug:slug>/", views.ArticleDetailAPI.as_view()),
    path("glossary/", views.GlossaryListAPI.as_view()),
    path("glossary/<slug:slug>/", views.GlossaryDetailAPI.as_view()),
]
