"""US-09 · US-109: la lista de clientes del servidor y borrar en lote (iteracion-17 #5).

Fuente: backlog 4.9 → US-09 list_spec y su cambio «iteracion-17».
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import status

from apps.clients.models import Client
from apps.clients.tests.factories import ClientFactory
from apps.clients.tests.test_clients import quote_for

URL = "/api/clients/"
BULK_DELETE = "/api/clients/bulk/delete/"


def nombres(response) -> list[str]:
    return [row["name"] for row in response.data["results"]]


@pytest.mark.django_db
class TestLaListaDeClientes:
    def test_la_primera_pagina_en_orden_alfabetico(
        self, user, authenticated_client
    ) -> None:
        """Cambio iteracion-17 - El servidor entrega una página."""
        for nombre in ("Zapata", "Álvarez", "Muñoz"):
            ClientFactory(owner=user, name=nombre)

        response = authenticated_client.get(URL)

        assert response.data["count"] == 3
        assert nombres(response) == ["Álvarez", "Muñoz", "Zapata"]

    def test_busca_por_nombre_telefono_o_correo_sin_acentos(
        self, user, authenticated_client
    ) -> None:
        """Cambio iteracion-17 - Buscar por nombre, teléfono o correo."""
        ClientFactory(owner=user, name="Carmen Muciño", phone="", email="")
        ClientFactory(owner=user, name="Reyes", phone="+525555125599", email="")
        ClientFactory(owner=user, name="Peña", phone="", email="obra@penasco.mx")
        ClientFactory(owner=user, name="Otro", phone="", email="")

        assert nombres(authenticated_client.get(URL, {"search": "mucino"})) == [
            "Carmen Muciño"
        ]
        assert nombres(authenticated_client.get(URL, {"search": "5512"})) == ["Reyes"]
        assert nombres(authenticated_client.get(URL, {"search": "penasco"})) == ["Peña"]

    def test_filtrar_por_contacto(self, user, authenticated_client) -> None:
        """Cambio iteracion-17 - Filtrar por contacto."""
        ClientFactory(owner=user, name="Con teléfono", phone="+525555125599", email="")
        ClientFactory(owner=user, name="Con correo", phone="", email="a@b.mx")
        ClientFactory(owner=user, name="Sin nada", phone="", email="")

        con = authenticated_client.get(URL, {"has_contact": "true"})
        sin = authenticated_client.get(URL, {"has_contact": "false"})

        assert nombres(con) == ["Con correo", "Con teléfono"]
        assert nombres(sin) == ["Sin nada"]

    def test_el_orden_es_una_lista_blanca(self, user, authenticated_client) -> None:
        primero = ClientFactory(owner=user, name="B")
        segundo = ClientFactory(owner=user, name="A")
        # Las fechas se fijan: dos altas seguidas pueden caer en el mismo
        # instante del reloj y el orden quedaría al azar.
        ahora = timezone.now()
        ayer = ahora - timedelta(days=1)
        Client.objects.filter(pk=primero.pk).update(created_at=ayer)
        Client.objects.filter(pk=segundo.pk).update(created_at=ahora)

        recientes = authenticated_client.get(URL, {"ordering": "-created_at"})
        desconocido = authenticated_client.get(URL, {"ordering": "owner__email"})

        assert nombres(recientes) == [segundo.name, primero.name]
        assert nombres(desconocido) == ["A", "B"]

    def test_filtra_por_ids_para_rotular_un_selector(
        self, user, authenticated_client
    ) -> None:
        a, b, _ = ClientFactory.create_batch(3, owner=user)

        response = authenticated_client.get(URL, {"id": f"{a.id},{b.id}"})

        assert {row["id"] for row in response.data["results"]} == {str(a.id), str(b.id)}

    def test_cada_fila_dice_en_cuantas_cotizaciones_esta(
        self, user, authenticated_client
    ) -> None:
        cliente = ClientFactory(owner=user, name="Ocupado")
        quote_for(user, cliente)

        response = authenticated_client.get(URL)

        assert response.data["results"][0]["quotes_count"] == 1


@pytest.mark.django_db
class TestBorrarEnLote:
    """US-109 en lote: cada cliente se borra o dice por qué no."""

    def test_borra_los_elegidos(self, user, authenticated_client) -> None:
        a, b = ClientFactory.create_batch(2, owner=user)
        queda = ClientFactory(owner=user)

        response = authenticated_client.post(
            BULK_DELETE, {"ids": [str(a.id), str(b.id)]}
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {"requested": 2, "processed": 2, "failed": []}
        assert list(Client.objects.filter(owner=user)) == [queda]

    def test_falla_parcial_el_que_esta_en_una_cotizacion_se_queda(
        self, user, authenticated_client
    ) -> None:
        """Cambio iteracion-17 - Borrar varios con falla parcial."""
        libres = ClientFactory.create_batch(3, owner=user)
        ocupado = ClientFactory(owner=user)
        quote_for(user, ocupado)

        response = authenticated_client.post(
            BULK_DELETE, {"ids": [str(c.id) for c in [*libres, ocupado]]}
        )

        assert response.data["requested"] == 4
        assert response.data["processed"] == 3
        assert response.data["failed"] == [
            {
                "id": str(ocupado.id),
                "detail": "No se puede borrar: el cliente está en 1 cotización.",
            }
        ]
        assert Client.objects.filter(pk=ocupado.pk).exists()

    def test_todos_los_resultados_de_la_busqueda(
        self, user, authenticated_client
    ) -> None:
        ClientFactory(owner=user, name="Reyes uno")
        ClientFactory(owner=user, name="Reyes dos")
        otro = ClientFactory(owner=user, name="Peña")

        response = authenticated_client.post(
            f"{BULK_DELETE}?search=reyes", {"select_all": True}
        )

        assert response.data["processed"] == 2
        assert list(Client.objects.filter(owner=user)) == [otro]

    def test_uno_de_otra_cuenta_es_no_encontrado_y_no_se_toca(
        self, user, authenticated_client
    ) -> None:
        ajeno = ClientFactory()

        response = authenticated_client.post(BULK_DELETE, {"ids": [str(ajeno.id)]})

        assert response.data["failed"] == [
            {"id": str(ajeno.id), "detail": "No encontrado."}
        ]
        assert Client.objects.filter(pk=ajeno.pk).exists()

    def test_por_encima_del_tope_es_400_con_el_limite(
        self, user, authenticated_client, settings
    ) -> None:
        settings.BULK_MAX_ITEMS = 2
        ids = [str(c.id) for c in ClientFactory.create_batch(3, owner=user)]

        response = authenticated_client.post(BULK_DELETE, {"ids": ids})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Puedes seleccionar hasta 2 registros por acción." in str(response.data)
        assert Client.objects.filter(owner=user).count() == 3

    def test_sin_sesion_es_401(self, api_client) -> None:
        response = api_client.post(BULK_DELETE, {"ids": []})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
