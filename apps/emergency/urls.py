from django.urls import path

from apps.emergency import views

_S = "sos/<uuid:sos_id>"
_O = "ops/sos/<uuid:sos_id>"

urlpatterns = [
    path("me/", views.MeAPI.as_view()),
    path("sos/", views.SosListAPI.as_view()),
    path(f"{_S}/", views.SosDetailAPI.as_view()),
    path(f"{_S}/cancel/", views.SosCancelAPI.as_view()),
    path(f"{_S}/info/", views.SosInfoAPI.as_view()),
    path(f"{_S}/location/", views.SosLocationAPI.as_view()),
    path(f"{_S}/acknowledge-family/", views.SosFamilyAckAPI.as_view()),
    path(f"{_S}/contact/", views.SosContactAPI.as_view()),
    path("ops/sos/", views.OpsListAPI.as_view()),
    path(f"{_O}/", views.OpsDetailAPI.as_view()),
    path(f"{_O}/acknowledge/", views.OpsAcknowledgeAPI.as_view()),
    path(f"{_O}/coordinate/", views.OpsCoordinateAPI.as_view()),
    path(f"{_O}/update/", views.OpsUpdateAPI.as_view()),
    path(f"{_O}/assign/", views.OpsAssignAPI.as_view()),
    path(f"{_O}/escalate/", views.OpsEscalateAPI.as_view()),
    path(f"{_O}/resolve/", views.OpsResolveAPI.as_view()),
    path(f"{_O}/close/", views.OpsCloseAPI.as_view()),
]
