from django.urls import path
from .views import AppNotificationAPI, LiveCrowdStatusAPI, QuickAlertsAPI, UpdateLocationAPI, ZoneDetailAPI

app_name = 'crowd'


urlpatterns = [  
      path('live-status/', LiveCrowdStatusAPI.as_view(), name='live-crowd-status'),
      path('quick-alerts/', QuickAlertsAPI.as_view(), name='quick-alerts'),
      path("zones/<str:zone_code>/details/", ZoneDetailAPI.as_view(), name='zone-details'),
      path("update-location/", UpdateLocationAPI.as_view(), name="update-location"),
      path("notifications/", AppNotificationAPI.as_view(), name="app-notifications"),
      
      
      ]

