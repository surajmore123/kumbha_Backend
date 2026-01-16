from django.urls import path
from .views import NearbyTemplesAPI,TempleDetailAPI,TempleNavigationAPI

app_name = 'temples'


urlpatterns = [
     path('nearby-temples/', NearbyTemplesAPI.as_view(), name='nearby-temples'),
     path('nearby-temples/<temple_id>/',TempleDetailAPI.as_view(), name='nearby-temples-details'),
     path('navigate/<temple_id>/',TempleNavigationAPI.as_view(),name='nearby-temples-navigate')

]