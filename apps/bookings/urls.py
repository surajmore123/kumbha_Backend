from django.urls import path

from apps.bookings import views

urlpatterns = [
    path("stays/", views.StayListAPI.as_view()),
    path("stays/filters/", views.StayFiltersAPI.as_view()),
    path("stays/<str:listing_id>/", views.StayDetailAPI.as_view()),
    path("transport/", views.TransportListAPI.as_view()),
    path("transport/search/", views.TransportSearchAPI.as_view()),
    path("transport/<slug:slug>/", views.TransportDetailAPI.as_view()),
    path("saved/", views.SavedBookingListAPI.as_view()),
    path("saved/<uuid:booking_id>/", views.SavedBookingDetailAPI.as_view()),
]
