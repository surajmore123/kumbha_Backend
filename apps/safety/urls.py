from django.urls import path

from apps.safety import views

_M = "circles/<uuid:family_id>/members/<uuid:member_id>/qr"

urlpatterns = [
    path(f"{_M}/", views.MemberQrAPI.as_view()),
    path(f"{_M}/revoke/", views.MemberQrRevokeAPI.as_view()),
    path(f"{_M}/regenerate/", views.MemberQrRegenerateAPI.as_view()),
    path("circles/<uuid:family_id>/alerts/", views.FamilyAlertListAPI.as_view()),
    path("circles/<uuid:family_id>/alerts/<uuid:alert_id>/acknowledge/", views.FamilyAlertAckAPI.as_view()),
    path("circles/<uuid:family_id>/alerts/<uuid:alert_id>/resolve/", views.FamilyAlertResolveAPI.as_view()),
    path("helper/me/", views.HelperStatusAPI.as_view()),
    path("helper/alerts/<uuid:alert_id>/", views.HelperAlertAPI.as_view()),
    path("scan/resolve/", views.ScanResolveAPI.as_view()),
    path("scan/<uuid:scan_id>/confirm/", views.ScanConfirmAPI.as_view()),
]
