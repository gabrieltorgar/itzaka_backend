"""Top-level API views (health check)."""

from django.conf import settings
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """GET /api/health/: liveness and the deployed release.

    Public on purpose: it answers only the app's own release number and reads
    no model and no secret; the default anon throttle applies.
    """

    authentication_classes = []  # a dead access cookie never turns the probe into 401
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        """The version git-deploy-ops post_deploy_check.py --api-version compares."""
        return Response({"status": "ok", "version": settings.APP_VERSION})
