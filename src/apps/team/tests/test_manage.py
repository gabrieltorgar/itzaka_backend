"""Gestionar a mis colaboradores (iteracion-14 #5, US-138).

La tabla del administrador junta a quien ya colabora (activo o inactivo) y las
invitaciones que siguen esperando (pendientes o vencidas). Desde ahí activa,
desactiva o quita a un colaborador.
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.clients.models import Client
from apps.team.models import Membership
from apps.team.tests.factories import InvitationFactory, MembershipFactory

LISTA = "/api/collaborators/"


def miembro(pk) -> str:
    return f"/api/collaborators/members/{pk}/"


def como(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def admin(db):
    return UserFactory()


@pytest.fixture
def equipo(admin):
    """Un activo, un inactivo, una invitación pendiente y una vencida."""
    activo = MembershipFactory(account=admin, user__email="ana@estudio.mx")
    inactivo = MembershipFactory(
        account=admin, user__email="luis@obra.mx", is_active=False
    )
    pendiente = InvitationFactory(account=admin, email="mar@despacho.mx")
    vencida = InvitationFactory(
        account=admin,
        email="pepe@obra.mx",
        expires_at=timezone.now() - timedelta(days=1),
    )
    InvitationFactory(account=admin, email="ya@entro.mx", status="accepted")
    InvitationFactory(account=admin, email="no@vino.mx", status="cancelled")
    MembershipFactory()  # de otra empresa
    return {
        "activo": activo,
        "inactivo": inactivo,
        "pendiente": pendiente,
        "vencida": vencida,
    }


@pytest.mark.django_db
class TestLaTabla:
    """US-138 Flujo principal - La tabla."""

    def test_members_and_waiting_invitations_with_their_state(self, admin, equipo):
        response = como(admin).get(LISTA)

        assert response.status_code == status.HTTP_200_OK
        filas = {fila["email"]: fila for fila in response.data["results"]}
        assert {e: f["status"] for e, f in filas.items()} == {
            "ana@estudio.mx": "active",
            "luis@obra.mx": "inactive",
            "mar@despacho.mx": "pending",
            "pepe@obra.mx": "expired",
        }
        assert filas["ana@estudio.mx"]["kind"] == "member"
        assert filas["mar@despacho.mx"]["kind"] == "invitation"
        assert filas["mar@despacho.mx"]["expires_at"]
        assert all(fila["since"] for fila in response.data["results"])

    @pytest.mark.parametrize(
        ("params", "esperados"),
        [
            ({"search": "OBRA"}, {"luis@obra.mx", "pepe@obra.mx"}),
            ({"status": "inactive"}, {"luis@obra.mx"}),
            ({"status": "pending"}, {"mar@despacho.mx"}),
            ({"search": "nadie"}, set()),
        ],
    )
    def test_search_and_filter(self, admin, equipo, params, esperados) -> None:
        response = como(admin).get(LISTA, params)

        assert {fila["email"] for fila in response.data["results"]} == esperados

    def test_without_collaborators_the_list_is_empty(self, admin) -> None:
        assert como(admin).get(LISTA).data["results"] == []

    def test_a_collaborator_cannot_see_the_team(self, admin, equipo) -> None:
        response = como(equipo["activo"].user).get(LISTA)

        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestActivarYDesactivar:
    """US-138 Flujo principal - Desactivar y activar."""

    def test_deactivating_leaves_them_out_and_activating_brings_them_back(
        self, admin, equipo
    ) -> None:
        activo = equipo["activo"]

        apagar = como(admin).patch(
            miembro(activo.id), {"is_active": False}, format="json"
        )
        fuera = como(activo.user).get("/api/clients/")
        prender = como(admin).patch(
            miembro(activo.id), {"is_active": True}, format="json"
        )
        dentro = como(activo.user).get("/api/clients/")

        assert apagar.status_code == status.HTTP_200_OK
        assert apagar.data["status"] == "inactive"
        assert fuera.status_code == status.HTTP_403_FORBIDDEN
        assert prender.data["status"] == "active"
        assert dentro.status_code == status.HTTP_200_OK

    def test_someone_else_s_collaborator_does_not_exist(self, admin, equipo) -> None:
        ajeno = MembershipFactory()

        response = como(admin).patch(
            miembro(ajeno.id), {"is_active": False}, format="json"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        ajeno.refresh_from_db()
        assert ajeno.is_active is True


@pytest.mark.django_db
class TestEliminar:
    """US-138 Flujo principal - Eliminar."""

    def test_removed_from_the_company_but_what_they_did_stays(
        self, admin, equipo
    ) -> None:
        activo = equipo["activo"]
        Client.objects.create(owner=admin, name="Lo registró Ana")

        response = como(admin).delete(miembro(activo.id))

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Membership.objects.filter(pk=activo.pk).exists()
        assert Client.objects.filter(owner=admin, name="Lo registró Ana").exists()
        # Su cuenta sigue siendo suya: sólo deja de estar en esta empresa.
        assert User.objects.filter(pk=activo.user_id).exists()
        assert como(activo.user).get("/api/clients/").status_code == 403

    def test_a_collaborator_cannot_remove_anyone(self, admin, equipo) -> None:
        response = como(equipo["activo"].user).delete(miembro(equipo["inactivo"].id))

        assert response.status_code == status.HTTP_403_FORBIDDEN
