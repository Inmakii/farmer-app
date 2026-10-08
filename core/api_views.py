from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


class ThrottledTokenObtainPairView(TokenObtainPairView):
    """Token issuing with a request limit (see DEFAULT_THROTTLE_RATES)."""

    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "auth_token"


class ThrottledTokenRefreshView(TokenRefreshView):
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "auth_refresh"


class CurrentUserView(APIView):
    """Return basic data for the user authenticated with a JWT access token."""

    permission_classes = (IsAuthenticated,)

    def get(self, request):
        return Response(
            {
                "id": request.user.pk,
                "username": request.user.get_username(),
                "email": request.user.email,
            }
        )
