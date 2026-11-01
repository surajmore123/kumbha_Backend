from django.urls import path

from apps.familylocation import views

_S = "sessions/<uuid:session_id>"
_C = "circles/<uuid:family_id>"

urlpatterns = [
    path(f"{_C}/eligible/", views.EligibleAPI.as_view()),
    path(f"{_C}/sessions/", views.SessionListAPI.as_view()),
    path(f"{_C}/feed/", views.FeedAPI.as_view()),
    path(f"{_S}/", views.SessionDetailAPI.as_view()),
    path(f"{_S}/pause/", views.SessionPauseAPI.as_view()),
    path(f"{_S}/resume/", views.SessionResumeAPI.as_view()),
    path(f"{_S}/stop/", views.SessionStopAPI.as_view()),
    path(f"{_S}/recipients/", views.SessionRecipientsAPI.as_view()),
    path(f"{_S}/duration/", views.SessionDurationAPI.as_view()),
    path(f"{_S}/update/", views.LocationUpdateAPI.as_view()),
    path("cases/<uuid:case_id>/", views.CaseLocationAPI.as_view()),
]
