from django.urls import path

from apps.reunification import views

_C = "cases/<uuid:case_id>"
_P = "points/<uuid:point_id>"
_F = "circles/<uuid:family_id>"

urlpatterns = [
    path("overview/", views.OverviewAPI.as_view()),
    path("points/", views.PointListAPI.as_view()),
    path(f"{_P}/", views.FamilyPointDetailAPI.as_view()),
    path(f"{_P}/suggest/", views.FamilyPointSuggestAPI.as_view()),
    path(f"{_F}/points/", views.FamilyPointListAPI.as_view()),
    path(f"{_F}/notify/", views.NotifyFamilyAPI.as_view()),
    path(f"{_C}/", views.CaseDetailAPI.as_view()),
    path(f"{_C}/guidance/", views.CaseGuidanceAPI.as_view()),
    path(f"{_C}/meeting-point/", views.CaseMeetingPointAPI.as_view()),
    path(f"{_C}/coordination/", views.CaseCoordinationAPI.as_view()),
    path("route/", views.RouteAPI.as_view()),
]
