"""
The existing JWT, plus a way to end it early. Tokens last 7 days, so without
this a removed account's session would carry on until it expired.
"""

from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import AccessToken

from apps.authentication.models import User


class KumbhAccessToken(AccessToken):
    def verify(self):
        super().verify()
        floor = (
            User.objects.filter(pk=self.payload.get(api_settings.USER_ID_CLAIM))
            .values_list("tokens_valid_after", flat=True).first()
        )
        if floor is None:
            return
        issued = self.payload.get("iat") or self.payload["exp"] - api_settings.ACCESS_TOKEN_LIFETIME.total_seconds()
        if int(issued) < int(floor.timestamp()):
            raise TokenError("This session has been ended.")
