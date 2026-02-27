from django.contrib import admin
from django.urls import path, include


urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/', include('apps.authentication.urls')),
    path('chat/', include('apps.aiChat.urls')),
    path('temples/', include('apps.temples.urls')),
    path('events/', include('apps.events.urls')),
    path('crowd/', include('apps.crowd.urls')),
    
]