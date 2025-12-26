from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from .models import Temple
from .serializers import NearbyTempleSerializer
from rest_framework.permissions import IsAuthenticated
from .utility import haversine  

class NearbyTemplesAPI(APIView):
    authentication_classes =[JWTAuthentication]
    permission_classes =[IsAuthenticated]
    def get(self, request):
        try:
            user_lat = float(request.query_params.get("lat"))
            user_lng = float(request.query_params.get("lng"))
            radius_km = float(request.query_params.get("radius", 5))
        except (TypeError, ValueError):
            return Response(
                {"error": "Invalid or missing latitude/longitude"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        temples = Temple.objects.filter(is_active=True, del_flag=0)

        nearby = []
        for temple in temples:
            distance = haversine(
                user_lat,
                user_lng,
                float(temple.latitude),
                float(temple.longitude),
            )

            if distance <= radius_km:
                temple.distance_km = round(distance, 2)
                nearby.append(temple)

        nearby.sort(key=lambda t: t.distance_km)

        serializer = NearbyTempleSerializer(nearby, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
