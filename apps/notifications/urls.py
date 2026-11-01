from django.urls import path

from apps.notifications import views

urlpatterns = [
    path("", views.NotificationListAPI.as_view()),
    path("summary/", views.NotificationSummaryAPI.as_view()),
    path("read-all/", views.NotificationReadAllAPI.as_view()),
    path("<uuid:notification_id>/read/", views.NotificationReadAPI.as_view()),
]
