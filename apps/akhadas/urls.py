from django.urls import path

from apps.akhadas import views

urlpatterns = [
    path("", views.AkhadaListAPI.as_view()),
    path("filters/", views.FiltersAPI.as_view()),
    path("saints/", views.SaintListAPI.as_view()),
    path("saints/<slug:slug>/", views.SaintDetailAPI.as_view()),
    path("articles/", views.ArticleListAPI.as_view()),
    path("articles/<slug:slug>/", views.ArticleDetailAPI.as_view()),
    path("activities/", views.ActivityListAPI.as_view()),
    path("<slug:slug>/", views.AkhadaDetailAPI.as_view()),
]
