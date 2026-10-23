"""Los errores de la API, en palabras de la aplicación."""

from django.db import IntegrityError
from rest_framework import status

from common.exceptions import CONFLICT_MESSAGE, exception_handler


class TestConflicto:
    """Bug iteracion-16 - Dos peticiones simultáneas no terminan en un 500.

    Cuando dos peticiones chocan con una restricción única de la base, la
    segunda pierde: se le dice qué pasó y que lo intente de nuevo.
    """

    def test_a_unique_conflict_is_a_409(self) -> None:
        response = exception_handler(IntegrityError("duplicate key"), {})

        assert response is not None
        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.data == {"detail": CONFLICT_MESSAGE, "code": "conflict"}

    def test_the_database_message_never_reaches_the_client(self) -> None:
        response = exception_handler(
            IntegrityError(
                'duplicate key value violates "team_invitation_one_pending"'
            ),
            {},
        )

        assert "team_invitation" not in str(response.data)
