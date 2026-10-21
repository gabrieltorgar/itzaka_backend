"""Lo que sólo el administrador decide (iteracion-14 #4, US-140 · US-71 · US-102).

También US-118 (el contacto de la organización).

Un colaborador hace todo, salvo cambiar la organización —nombre, color,
logotipo, contacto— y gestionar colaboradores. Quien administra una empresa y
colabora en otra, en la otra es colaborador.
"""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.services import get_my_organization
from apps.accounts.tests.factories import UserFactory
from apps.team.models import Invitation
from apps.team.tests.factories import MembershipFactory

ORG = "/api/auth/organization/"
INVITAR = "/api/collaborators/invitations/"
SOLO_ADMIN = "Sólo el administrador de la empresa puede hacer esto."


def como(user, empresa_id=None) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    if empresa_id is not None:
        client.credentials(HTTP_X_EMPRESA=str(empresa_id))
    return client


@pytest.fixture
def admin(db):
    cuenta = UserFactory()
    organizacion = get_my_organization(user=cuenta)
    organizacion.name = "Estudio Reyes"
    organizacion.save()
    return cuenta


@pytest.fixture
def colaborador(admin):
    return MembershipFactory(account=admin).user


@pytest.fixture
def correo(settings, mocker):
    settings.RESEND_API_KEY = "re_test"
    return mocker.patch("apps.team.emails.mail.send_email", return_value=True)


@pytest.mark.django_db
class TestLaOrganizacion:
    """US-71 / US-102 / US-118: la ve, pero no la cambia."""

    def test_a_collaborator_sees_it(self, colaborador) -> None:
        response = como(colaborador).get(ORG)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Estudio Reyes"

    @pytest.mark.parametrize(
        "cambio",
        [{"name": "Otro nombre"}, {"color": "#000000"}, {"phone": "55 1234 5678"}],
    )
    def test_a_collaborator_cannot_change_it(self, admin, colaborador, cambio):
        response = como(colaborador).patch(ORG, cambio, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.data["detail"] == SOLO_ADMIN
        assert get_my_organization(user=admin).name == "Estudio Reyes"

    def test_the_administrator_still_can(self, admin) -> None:
        response = como(admin).patch(ORG, {"name": "Reyes Arquitectos"}, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert get_my_organization(user=admin).name == "Reyes Arquitectos"


@pytest.mark.django_db
class TestLosColaboradores:
    """Un colaborador no invita a nadie."""

    def test_a_collaborator_cannot_invite(self, colaborador, correo) -> None:
        response = como(colaborador).post(
            INVITAR, {"emails": ["luis@obra.mx"]}, format="json"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert not Invitation.objects.exists()
        correo.assert_not_called()


@pytest.mark.django_db
class TestAdministradorQueColaboraEnOtra:
    """Caso de borde - En la otra empresa es colaborador."""

    def test_in_the_other_company_they_are_a_collaborator(self, admin, correo):
        otra = UserFactory()
        MembershipFactory(account=otra, user=admin)

        organizacion = como(admin, otra.id).patch(ORG, {"name": "X"}, format="json")
        invitar = como(admin, otra.id).post(
            INVITAR, {"emails": ["luis@obra.mx"]}, format="json"
        )

        assert organizacion.status_code == status.HTTP_403_FORBIDDEN
        assert invitar.status_code == status.HTTP_403_FORBIDDEN

    def test_in_their_own_they_are_the_administrator(self, admin, correo) -> None:
        otra = UserFactory()
        MembershipFactory(account=otra, user=admin)

        response = como(admin, admin.id).post(
            INVITAR, {"emails": ["luis@obra.mx"]}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert Invitation.objects.get().account == admin
