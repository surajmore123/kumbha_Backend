from django.contrib import admin
from django.urls import path, include

from apps.operations.health import LiveAPI, OperationsHealthAPI, ReadyAPI


urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/', include('apps.authentication.urls')),
    path('chat/', include('apps.aiChat.urls')),
    path('temples/', include('apps.temples.urls')),
    path('events/', include('apps.events.urls')),
    path('crowd/', include('apps.crowd.urls')),
    path('journal/', include('apps.journal.urls')),
    path('journeys/', include('apps.journeys.urls')),
    path('akhadas/', include('apps.akhadas.urls')),
    path('news/', include('apps.news.urls')),
    path('learn/', include('apps.learn.urls')),
    path('bookings/', include('apps.bookings.urls')),
    path('family/', include('apps.family.urls')),
    path('safety/', include('apps.safety.urls')),
    path('lostfound/', include('apps.lostfound.urls')),
    path('location/', include('apps.familylocation.urls')),
    path('reunification/', include('apps.reunification.urls')),
    path('notifications/', include('apps.notifications.urls')),
    path('emergency/', include('apps.emergency.urls')),
    path('operations/', include('apps.operations.urls')),
    path('health/', LiveAPI.as_view()),
    path('health/ready/', ReadyAPI.as_view()),
    path('health/operations/', OperationsHealthAPI.as_view()),
    # Website (kumbhapath.in) API
    path('v1/', include('apps.website.urls')),
    
]