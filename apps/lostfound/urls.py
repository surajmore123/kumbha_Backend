from django.urls import path

from apps.lostfound import views

_C = "cases/<uuid:case_id>"
_O = "ops/cases/<uuid:case_id>"
_M = "ops/matches/<uuid:match_id>"

urlpatterns = [
    path("me/", views.CapabilitiesAPI.as_view()),
    path("cases/", views.CaseListAPI.as_view()),
    path("found/", views.FoundReportAPI.as_view()),
    path(f"{_C}/", views.CaseDetailAPI.as_view()),
    path(f"{_C}/info/", views.CaseInfoAPI.as_view()),
    path(f"{_C}/correction/", views.CaseCorrectionAPI.as_view()),
    path(f"{_C}/cancel/", views.CaseCancelAPI.as_view()),
    path(f"{_C}/confirm-reunion/", views.CaseConfirmReunionAPI.as_view()),
    path(f"{_C}/sightings/", views.CaseSightingListAPI.as_view()),
    path(f"{_C}/attachments/", views.AttachmentListAPI.as_view()),
    path("attachments/<uuid:attachment_id>/", views.AttachmentDetailAPI.as_view()),
    path("ops/cases/", views.OpsCaseListAPI.as_view()),
    path(f"{_O}/", views.OpsCaseDetailAPI.as_view()),
    path(f"{_O}/status/", views.OpsStatusAPI.as_view()),
    path(f"{_O}/assign/", views.OpsAssignAPI.as_view()),
    path(f"{_O}/notes/", views.OpsNoteAPI.as_view()),
    path(f"{_O}/contact/", views.OpsContactAPI.as_view()),
    path(f"{_O}/find-matches/", views.OpsFindMatchesAPI.as_view()),
    path(f"{_O}/ai/", views.OpsCaseAIAPI.as_view()),
    path(f"{_O}/ai/translate/", views.OpsTranslateAPI.as_view()),
    path(f"{_O}/ai/extract/", views.OpsExtractAPI.as_view()),
    path(f"{_O}/ai/extract/review/", views.OpsExtractionReviewAPI.as_view()),
    path("ops/translations/<uuid:translation_id>/review/", views.OpsTranslationReviewAPI.as_view()),
    path(f"{_O}/verify/", views.OpsVerifyAPI.as_view()),
    path(f"{_O}/reunite/", views.OpsReuniteAPI.as_view()),
    path("ops/sightings/<uuid:sighting_id>/review/", views.OpsSightingReviewAPI.as_view()),
    path("ops/matches/", views.OpsMatchListAPI.as_view()),
    path(f"{_M}/approve/", views.OpsMatchApproveAPI.as_view()),
    path(f"{_M}/dismiss/", views.OpsMatchDismissAPI.as_view()),
    path(f"{_M}/confirm/", views.OpsMatchConfirmAPI.as_view()),
]
