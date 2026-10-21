"""Views de colaboradores: invitar y gestionar a quien trabaja en la empresa."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.team.serializers import InviteResultSerializer, InviteSerializer
from apps.team.services import invite_collaborators


class InvitationsView(APIView):
    """POST /api/collaborators/invitations/ — invitar a uno o varios correos.

    Responde 201 si salió al menos una invitación; si todos los correos ya
    estaban, 200 con el porqué de cada uno.
    """

    permission_classes = [IsAuthenticated]
    throttle_scope = "invitations"

    def post(self, request: Request) -> Response:
        serializer = InviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = invite_collaborators(
            account=request.user, emails=serializer.validated_data["emails"]
        )
        return Response(
            InviteResultSerializer(result).data,
            status=status.HTTP_201_CREATED if result.invited else status.HTTP_200_OK,
        )
