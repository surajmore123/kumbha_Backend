from django.urls import path

from apps.family import views

_M = "circles/<uuid:family_id>/members/<uuid:member_id>"

urlpatterns = [
    path("circles/", views.CircleListAPI.as_view()),
    path("circles/<uuid:family_id>/", views.CircleDetailAPI.as_view()),
    path("circles/<uuid:family_id>/leave/", views.CircleLeaveAPI.as_view()),
    path("circles/<uuid:family_id>/organizer/", views.OrganizerOfferAPI.as_view()),
    path("circles/<uuid:family_id>/organizer/accept/", views.OrganizerAcceptAPI.as_view()),
    path("circles/<uuid:family_id>/members/", views.MemberListAPI.as_view()),
    path(f"{_M}/", views.MemberDetailAPI.as_view()),
    path(f"{_M}/photo/", views.MemberPhotoAPI.as_view()),
    path(f"{_M}/guardians/", views.GuardianListAPI.as_view()),
    path(f"{_M}/guardians/<uuid:guardian_id>/", views.GuardianDetailAPI.as_view()),
    path(f"{_M}/contacts/", views.ContactListAPI.as_view()),
    path("circles/<uuid:family_id>/contacts/", views.ContactListAPI.as_view()),
    path("circles/<uuid:family_id>/contacts/reorder/", views.ContactReorderAPI.as_view()),
    path("circles/<uuid:family_id>/contacts/<uuid:contact_id>/", views.ContactDetailAPI.as_view()),
    path("circles/<uuid:family_id>/invitations/", views.InvitationListAPI.as_view()),
    path("circles/<uuid:family_id>/invitations/<uuid:invitation_id>/revoke/", views.InvitationRevokeAPI.as_view()),
    path("invitations/mine/", views.MyInvitationsAPI.as_view()),
    path("invitations/lookup/", views.InvitationLookupAPI.as_view()),
    path("invitations/accept/", views.InvitationAcceptAPI.as_view()),
    path("invitations/decline/", views.InvitationDeclineAPI.as_view()),
]
