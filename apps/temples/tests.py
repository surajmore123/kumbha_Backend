from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.authentication.models import User
from apps.temples.models import Temple, TempleAnalyticsView
from apps.temples.utility import _coordinate


class TempleDetailLocationTests(TestCase):
    """The detail screen works with or without the user's location."""

    def setUp(self):
        self.user = User.objects.create_user(phone_number="9000000101")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.temple = Temple.objects.create(
            name="Trimbakeshwar Jyotirling Mandir",
            latitude=Decimal("19.932400"),
            longitude=Decimal("73.530800"),
            city="Nashik",
        )
        self.url = f"/api/temples/nearby-temples/{self.temple.temple_id}/"

    def test_empty_location_from_chat_does_not_fail(self):
        # Exactly what the app sends when it has no location: "lat=&lng=".
        response = self.client.get(
            self.url, {"temple_id": str(self.temple.temple_id), "lat": "", "lng": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["name"], self.temple.name)
        event = TempleAnalyticsView.objects.get()
        self.assertEqual(event.event_type, "DETAIL_OPEN")
        self.assertIsNone(event.user_latitude)
        self.assertIsNone(event.user_longitude)

    def test_location_is_recorded_when_given(self):
        response = self.client.get(self.url, {"lat": "19.9975123456", "lng": "73.791"})
        self.assertEqual(response.status_code, 200)
        event = TempleAnalyticsView.objects.get()
        self.assertEqual(event.user_latitude, Decimal("19.997512"))
        self.assertEqual(event.user_longitude, Decimal("73.791000"))

    def test_invalid_or_partial_location_is_ignored(self):
        for params in ({"lat": "abc", "lng": "73.7"}, {"lat": "95", "lng": "73.7"}, {"lat": "19.9"}):
            with self.subTest(params=params):
                self.assertEqual(self.client.get(self.url, params).status_code, 200)
        self.assertFalse(
            TempleAnalyticsView.objects.exclude(user_latitude__isnull=True).exists()
        )

    def test_navigation_with_empty_location(self):
        response = self.client.post(
            f"/api/temples/navigate/{self.temple.temple_id}/",
            {"user_latitude": "", "user_longitude": ""},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

    def test_coordinate_parsing(self):
        self.assertIsNone(_coordinate("", 90))
        self.assertIsNone(_coordinate(None, 90))
        self.assertIsNone(_coordinate("NaN", 90))
        self.assertIsNone(_coordinate("-181", 180))
        self.assertEqual(_coordinate(" 19.5 ", 90), Decimal("19.500000"))
