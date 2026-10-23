"""Reenviar o cancelar una invitación (iteracion-14 #6, US-139).

Una invitación pendiente o vencida se reenvía con un enlace nuevo, que vale 7
días, y el anterior deja de servir; una pendiente se cancela y sale de la
tabla. Una que ya se aceptó no se toca: la persona ya es colaborador.
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.team.models import Invitation
from apps.team.services import hash_token
from apps.team.tests.factories import InvitationFactory, MembershipFactory

LISTA = "/api/collaborators/"


def reenviar(pk) -> str:
    return f"/api/collaborators/invitations/{pk}/resend/"


def cancelar(pk) -> str:
    return f"/api/collaborators/invitations/{pk}/cancel/"


def como(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def admin(db):
    return UserFactory()


@pytest.fixture
def equipo(admin):
    return {
        "pendiente": InvitationFactory(account=admin, email="mar@despacho.mx"),
        "vencida": InvitationFactory(
            account=admin,
            email="pepe@obra.mx",
            expires_at=timezone.now() - timedelta(days=1),
        ),
    }


@pytest.fixture
def correo(settings, mocker):
    settings.RESEND_API_KEY = "re_test"
    return mocker.patch("apps.team.emails.mail.send_email", return_value=True)


@pytest.mark.django_db
class TestReenviar:
    """US-139 Flujo principal - Reenviar."""

    @pytest.mark.parametrize("cual", ["pendiente", "vencida"])
    def test_a_new_link_for_seven_days_and_the_old_one_dies(
        self, admin, equipo, correo, cual
    ) -> None:
        invitacion = equipo[cual]
        huella_vieja = invitacion.token_hash

        response = como(admin).post(reenviar(invitacion.id))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "pending"
        invitacion.refresh_from_db()
        assert invitacion.token_hash != huella_vieja
        assert invitacion.expires_at > timezone.now() + timedelta(days=6)
        correo.assert_called_once()
        html = correo.call_args.kwargs["html"]
        token = html.split("/invitacion/")[1].split('"')[0]
        assert hash_token(token) == invitacion.token_hash

    def test_the_answer_says_the_email_went_out(self, admin, equipo, correo) -> None:
        """Bug iteracion-16 - Se dice si el correo salió."""
        response = como(admin).post(reenviar(equipo["pendiente"].id))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["email_sent"] is True

    def test_if_the_email_does_not_go_out_the_old_link_still_works(
        self, admin, correo
    ) -> None:
        """Bug iteracion-16 - Si el correo no sale, el enlace anterior sigue."""
        invitacion = InvitationFactory(
            account=admin, email="mar@despacho.mx", token="enlace-de-mar"
        )
        vence = invitacion.expires_at
        correo.return_value = False

        response = como(admin).post(reenviar(invitacion.id))

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert response.data["code"] == "email_not_sent"
        assert "enlace anterior sigue" in str(response.data["detail"])
        invitacion.refresh_from_db()
        assert invitacion.token_hash == hash_token("enlace-de-mar")
        assert invitacion.expires_at == vence
        # Quien ya tenía el correo de antes sigue entrando con su enlace.
        detalle = APIClient().get("/api/invitations/enlace-de-mar/")
        assert detalle.status_code == status.HTTP_200_OK
        assert detalle.data["status"] == "pending"

    def test_an_accepted_invitation_is_not_resent(self, admin, correo) -> None:
        aceptada = InvitationFactory(account=admin, status="accepted")

        response = como(admin).post(reenviar(aceptada.id))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "ya es colaborador" in str(response.data["detail"]).lower()
        correo.assert_not_called()


@pytest.mark.django_db
class TestCancelar:
    """US-139 Flujo principal - Cancelar."""

    def test_its_link_stops_working_and_it_leaves_the_table(
        self, admin, equipo
    ) -> None:
        invitacion = equipo["pendiente"]

        response = como(admin).post(cancelar(invitacion.id))
        tabla = como(admin).get(LISTA)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        invitacion.refresh_from_db()
        assert invitacion.status == Invitation.Status.CANCELLED
        filas = tabla.data["results"]
        assert "mar@despacho.mx" not in {fila["email"] for fila in filas}

    def test_an_accepted_invitation_cannot_be_cancelled(self, admin) -> None:
        aceptada = InvitationFactory(account=admin, status="accepted")

        response = como(admin).post(cancelar(aceptada.id))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        aceptada.refresh_from_db()
        assert aceptada.status == Invitation.Status.ACCEPTED

    def test_someone_else_s_invitation_does_not_exist(self, admin) -> None:
        ajena = InvitationFactory()

        response = como(admin).post(cancelar(ajena.id))

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_a_collaborator_cannot_resend_or_cancel(self, admin, equipo) -> None:
        colaborador = MembershipFactory(account=admin).user

        response = como(colaborador).post(cancelar(equipo["pendiente"].id))

        assert response.status_code == status.HTTP_403_FORBIDDEN
