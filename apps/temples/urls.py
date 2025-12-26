from django.urls import path
from .views import NearbyTemplesAPI

app_name = 'temples'


urlpatterns = [
     path('nearby-temples/', NearbyTemplesAPI.as_view(), name='nearby-temples'),

]