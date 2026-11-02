from django.urls import path

from apps.journeys import views

app_name = "journeys"

urlpatterns = [
    path("", views.JourneyListCreateAPI.as_view(), name="list"),
    path("guide/", views.JourneyGuideAPI.as_view(), name="guide"),
    path("<uuid:journey_id>/", views.JourneyDetailAPI.as_view(), name="detail"),
    path("<uuid:journey_id>/generate/", views.JourneyGenerateAPI.as_view(), name="generate"),
    path("<uuid:journey_id>/duplicate/", views.JourneyDuplicateAPI.as_view(), name="duplicate"),
    path("<uuid:journey_id>/export/", views.JourneyExportAPI.as_view(), name="export"),
    path("<uuid:journey_id>/items/", views.JourneyItemsAPI.as_view(), name="items"),
    path("<uuid:journey_id>/items/<int:item_id>/", views.JourneyItemDetailAPI.as_view(), name="item"),
    path(
        "<uuid:journey_id>/days/<int:day_number>/reorder/",
        views.JourneyDayReorderAPI.as_view(),
        name="reorder",
    ),
    path("<uuid:journey_id>/checklist/", views.JourneyChecklistAPI.as_view(), name="checklist"),
    path(
        "<uuid:journey_id>/checklist/<int:item_id>/",
        views.JourneyChecklistDetailAPI.as_view(),
        name="checklist-item",
    ),
    path("<uuid:journey_id>/references/", views.JourneyReferencesAPI.as_view(), name="references"),
    path(
        "<uuid:journey_id>/references/<int:reference_id>/",
        views.JourneyReferenceDetailAPI.as_view(),
        name="reference",
    ),
]
