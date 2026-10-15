from django.contrib import admin
from django.urls import path, include


urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/', include('apps.authentication.urls')),
    path('chat/', include('apps.aiChat.urls')),
    path('temples/', include('apps.temples.urls')),
    path('events/', include('apps.events.urls')),
    path('crowd/', include('apps.crowd.urls')),
    path('journal/', include('apps.journal.urls')),
    # Website (kumbhapath.in) API
    path('v1/', include('apps.website.urls')),
    
]