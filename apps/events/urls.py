from django.urls import path
from .views import FeaturedEventApi,UpcomingEventAPI,EventReminderToggleAPI

app_name = 'temples'


urlpatterns = [
     path('featured/', FeaturedEventApi.as_view(), name='featured-event'),
     path('upcoming/', UpcomingEventAPI.as_view(), name='upcoming-events'),
     path('<uuid:event_id>/reminder-toggle/', EventReminderToggleAPI.as_view(), name='event-reminder-toggle'),
    #  path('nearby-temples/<temple_id>/',TempleDetailAPI.as_view(), name='nearby-temples-details'),
    #  path('navigate/<temple_id>/',TempleNavigationAPI.as_view(),name='nearby-temples-navigate')

]