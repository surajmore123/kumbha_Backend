from django.urls import path

from apps.operations import views

_C = "cases/<uuid:case_id>"

urlpatterns = [
    path("auth/setup/", views.SetupAPI.as_view()),
    path("auth/login/", views.PasswordLoginAPI.as_view()),
    path("me/", views.MeAPI.as_view()),
    path("me/availability/", views.AvailabilityAPI.as_view()),
    path("overview/", views.OverviewAPI.as_view()),
    path("zones/", views.ZonesAPI.as_view()),
    path("cases/", views.MyCasesAPI.as_view()),
    path(f"{_C}/", views.CaseDetailAPI.as_view()),
    path(f"{_C}/progress/", views.CaseProgressAPI.as_view()),
    path(f"{_C}/observation/", views.CaseObservationAPI.as_view()),
    path(f"{_C}/escalate/", views.CaseEscalateAPI.as_view()),
    path(f"{_C}/assign/", views.CaseAssignAPI.as_view()),
    path(f"{_C}/unassign/", views.CaseUnassignAPI.as_view()),
    path(f"{_C}/assignments/", views.CaseHistoryAPI.as_view()),
    path("team/", views.TeamAPI.as_view()),
    path("escalations/", views.EscalationsAPI.as_view()),
]
