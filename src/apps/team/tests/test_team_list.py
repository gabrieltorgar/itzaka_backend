"""US-138: los colaboradores por páginas y la gestión en lote (iteracion-17 #10).

Fuente: backlog 4.9 → US-138 list_spec y su cambio «iteracion-17».
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.team.models import Invitation, Membership
from apps.team.tests.factories import InvitationFactory, MembershipFactory

LISTA = "/api/collaborators/"


def lote(accion: str) -> str:
    return f"/api/collaborators/bulk/{accion}/"


def como(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def correos(response) -> list[str]:
    return [fila["email"] for fila in response.data["results"]]


@pytest.fixture
def admin(db):
    return UserFactory()


@pytest.mark.django_db
class TestLosColaboradoresPorPaginas:
    def test_el_servidor_entrega_una_pagina(self, admin) -> None:
        """Cambio iteracion-17 - El servidor entrega una página."""
        for n in range(18):
            MembershipFactory(account=admin, user__email=f"colab{n:02d}@obra.mx")
        for n in range(12):
            InvitationFactory(account=admin, email=f"invitada{n:02d}@obra.mx")

        response = como(admin).get(LISTA)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 30
        assert len(response.data["results"]) == 20
        # Por omisión, por correo de la A a la Z.
        assert correos(response)[:2] == ["colab00@obra.mx", "colab01@obra.mx"]

    def test_varios_estados_a_la_vez(self, admin) -> None:
        """Cambio iteracion-17 - Varios estados a la vez."""
        MembershipFactory(account=admin, user__email="ana@estudio.mx")
        InvitationFactory(account=admin, email="mar@despacho.mx")
        InvitationFactory(
            account=admin,
            email="pepe@obra.mx",
            expires_at=timezone.now() - timedelta(days=1),
        )

        response = como(admin).get(LISTA, {"status": "pending,expired"})

        assert response.data["count"] == 2
        assert correos(response) == ["mar@despacho.mx", "pepe@obra.mx"]

    def test_ordenar_por_desde(self, admin) -> None:
        vieja = InvitationFactory(account=admin, email="b@obra.mx")
        nueva = InvitationFactory(account=admin, email="a@obra.mx")
        Invitation.objects.filter(pk=vieja.pk).update(
            sent_at=timezone.now() - timedelta(days=3)
        )
        Invitation.objects.filter(pk=nueva.pk).update(sent_at=timezone.now())

        recientes = como(admin).get(LISTA, {"ordering": "-since"})
        desconocido = como(admin).get(LISTA, {"ordering": "token_hash"})

        assert correos(recientes) == ["a@obra.mx", "b@obra.mx"]
        assert correos(desconocido) == ["a@obra.mx", "b@obra.mx"]


@pytest.mark.django_db
class TestGestionarEnLote:
    def test_desactivar_varios(self, admin) -> None:
        """Cambio iteracion-17 - Desactivar varios."""
        activos = MembershipFactory.create_batch(3, account=admin)

        response = como(admin).post(
            lote("deactivate"), {"ids": [str(m.id) for m in activos]}, format="json"
        )

        assert response.data == {"requested": 3, "processed": 3, "failed": []}
        assert not Membership.objects.filter(account=admin, is_active=True).exists()

    def test_la_accion_solo_aplica_a_lo_que_corresponde(self, admin) -> None:
        """Cambio iteracion-17 - La acción solo aplica a lo que corresponde."""
        activos = MembershipFactory.create_batch(2, account=admin)
        pendiente = InvitationFactory(account=admin)

        response = como(admin).post(
            lote("deactivate"),
            {"ids": [str(m.id) for m in activos] + [str(pendiente.id)]},
            format="json",
        )

        assert response.data["requested"] == 3
        assert response.data["processed"] == 2
        assert response.data["failed"] == [
            {"id": str(pendiente.id), "detail": "Es una invitación, no un colaborador."}
        ]

    def test_activar_varios(self, admin) -> None:
        inactivos = MembershipFactory.create_batch(2, account=admin, is_active=False)

        response = como(admin).post(
            lote("activate"), {"ids": [str(m.id) for m in inactivos]}, format="json"
        )

        assert response.data["processed"] == 2
        assert Membership.objects.filter(account=admin, is_active=True).count() == 2

    def test_eliminar_varios(self, admin) -> None:
        """Cambio iteracion-17 - Eliminar varios."""
        quitar = MembershipFactory.create_batch(2, account=admin)
        queda = MembershipFactory(account=admin)

        response = como(admin).post(
            lote("delete"), {"ids": [str(m.id) for m in quitar]}, format="json"
        )

        assert response.data["processed"] == 2
        assert list(Membership.objects.filter(account=admin)) == [queda]

    def test_cancelar_varias_invitaciones(self, admin) -> None:
        """Cambio iteracion-17 - Cancelar varias invitaciones."""
        invitaciones = InvitationFactory.create_batch(4, account=admin)
        colaborador = MembershipFactory(account=admin)

        response = como(admin).post(
            lote("cancel"),
            {"ids": [str(i.id) for i in invitaciones] + [str(colaborador.id)]},
            format="json",
        )

        assert response.data["processed"] == 4
        assert response.data["failed"] == [
            {
                "id": str(colaborador.id),
                "detail": "Es un colaborador, no una invitación.",
            }
        ]
        assert not Invitation.objects.filter(
            account=admin, status=Invitation.Status.PENDING
        ).exists()

    def test_todos_los_resultados_del_filtro(self, admin) -> None:
        InvitationFactory.create_batch(3, account=admin)
        vencida = InvitationFactory(
            account=admin, expires_at=timezone.now() - timedelta(days=1)
        )

        response = como(admin).post(
            f"{lote('cancel')}?status=pending",
            {"select_all": True, "exclude_ids": []},
            format="json",
        )

        assert response.data["processed"] == 3
        assert Invitation.objects.get(pk=vencida.pk).status == Invitation.Status.PENDING

    def test_lo_de_otra_empresa_es_no_encontrado(self, admin) -> None:
        ajeno = MembershipFactory()

        response = como(admin).post(
            lote("delete"), {"ids": [str(ajeno.id)]}, format="json"
        )

        assert response.data["failed"] == [
            {"id": str(ajeno.id), "detail": "No encontrado."}
        ]
        assert Membership.objects.filter(pk=ajeno.pk).exists()

    def test_por_encima_del_tope_es_400(self, admin, settings) -> None:
        settings.BULK_MAX_ITEMS = 2
        ids = [str(m.id) for m in MembershipFactory.create_batch(3, account=admin)]

        response = como(admin).post(lote("deactivate"), {"ids": ids}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Puedes seleccionar hasta 2 registros por acción." in str(response.data)

    def test_una_accion_que_no_existe_es_404(self, admin) -> None:
        response = como(admin).post(
            lote("reenviar"),
            {"ids": [str(MembershipFactory(account=admin).id)]},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_un_colaborador_no_gestiona_a_nadie(self, admin) -> None:
        colaborador = MembershipFactory(account=admin)

        response = como(colaborador.user).post(
            lote("deactivate"), {"ids": [str(colaborador.id)]}, format="json"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
