"""US-06 · US-110: el catálogo del servidor y borrar en lote (iteracion-17 #4).

Fuente: backlog 4.9 → US-06 list_spec y su cambio «iteracion-17».
"""

from decimal import Decimal

import pytest
from rest_framework import status

from apps.catalog.models import Tariff
from apps.catalog.tests.factories import TariffFactory
from apps.clients.tests.factories import ClientFactory

URL = "/api/tariffs/"
BULK_DELETE = "/api/tariffs/bulk/delete/"
M2 = Tariff.UnitType.SQUARE_METER
ML = Tariff.UnitType.LINEAR_METER
LOTE = Tariff.UnitType.UNIT


def nombres(response) -> list[str]:
    return [row["name"] for row in response.data["results"]]


def cotizar(user, tariff) -> None:
    """Una cotización que usa ``tariff``."""
    from apps.quotes.services import create_quote

    create_quote(
        owner=user,
        client=ClientFactory(owner=user),
        items_data=[{"tariff": tariff, "quantity": Decimal("1")}],
    )


@pytest.mark.django_db
class TestElCatalogoDeServicios:
    def test_la_primera_pagina_en_orden_alfabetico(
        self, user, authenticated_client
    ) -> None:
        """Cambio iteracion-17 - El servidor entrega una página."""
        TariffFactory.create_batch(25, owner=user)
        TariffFactory(owner=user, name="Acabado de muro")

        response = authenticated_client.get(URL)

        assert response.data["count"] == 26
        assert len(response.data["results"]) == 20
        assert nombres(response)[0] == "Acabado de muro"

    def test_buscar_en_nombre_o_descripcion_de_todo_el_catalogo(
        self, user, authenticated_client
    ) -> None:
        """Cambio iteracion-17 - Buscar en todo el catálogo."""
        TariffFactory.create_batch(30, owner=user)
        TariffFactory(owner=user, name="Piso porcelánico", description="")
        TariffFactory(
            owner=user, name="Zoclo", description="De porcelanato rectificado"
        )

        response = authenticated_client.get(URL, {"search": "porcel"})

        assert nombres(response) == ["Piso porcelánico", "Zoclo"]

    def test_varios_tipos_de_unidad(self, user, authenticated_client) -> None:
        """Cambio iteracion-17 - Varios tipos de unidad."""
        TariffFactory(owner=user, name="A", unit_type=M2)
        TariffFactory(owner=user, name="B", unit_type=ML)
        TariffFactory(owner=user, name="C", unit_type=LOTE)

        response = authenticated_client.get(URL, {"unit_type": f"{M2},{ML}"})

        assert nombres(response) == ["A", "B"]

    def test_el_orden_por_precio_es_de_todo_el_catalogo(
        self, user, authenticated_client
    ) -> None:
        """Cambio iteracion-17 - El orden es de todo el catálogo."""
        TariffFactory.create_batch(25, owner=user, unit_price=Decimal("100.00"))
        TariffFactory(owner=user, name="El más caro", unit_price=Decimal("9999.00"))

        response = authenticated_client.get(URL, {"ordering": "-unit_price"})

        assert nombres(response)[0] == "El más caro"

    def test_los_servicios_de_una_sola_cotizacion_no_son_del_catalogo(
        self, user, authenticated_client
    ) -> None:
        TariffFactory(owner=user, name="Del catálogo")
        TariffFactory(owner=user, name="Solo de una cotización", in_catalog=False)

        assert nombres(authenticated_client.get(URL)) == ["Del catálogo"]

    def test_filtra_por_ids_para_rotular_un_selector(
        self, user, authenticated_client
    ) -> None:
        a, b, _ = TariffFactory.create_batch(3, owner=user)

        response = authenticated_client.get(URL, {"id": f"{a.id},{b.id}"})

        assert {row["id"] for row in response.data["results"]} == {str(a.id), str(b.id)}


@pytest.mark.django_db
class TestBorrarServiciosEnLote:
    def test_borrar_varios(self, user, authenticated_client) -> None:
        """Cambio iteracion-17 - Borrar varios."""
        a, b, c = TariffFactory.create_batch(3, owner=user)

        response = authenticated_client.post(
            BULK_DELETE, {"ids": [str(a.id), str(b.id), str(c.id)]}
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {"requested": 3, "processed": 3, "failed": []}
        assert not Tariff.objects.filter(owner=user).exists()

    def test_falla_parcial(self, user, authenticated_client) -> None:
        """Cambio iteracion-17 - Borrar varios con falla parcial."""
        libres = TariffFactory.create_batch(3, owner=user)
        cotizados = TariffFactory.create_batch(2, owner=user)
        for tariff in cotizados:
            cotizar(user, tariff)

        response = authenticated_client.post(
            BULK_DELETE, {"ids": [str(t.id) for t in [*libres, *cotizados]]}
        )

        assert response.data["processed"] == 3
        assert {f["detail"] for f in response.data["failed"]} == {
            "No se puede borrar: el servicio está en 1 cotización."
        }
        assert Tariff.objects.filter(pk__in=[t.pk for t in cotizados]).count() == 2

    def test_seleccionar_todos_los_resultados_del_filtro(
        self, user, authenticated_client
    ) -> None:
        """Cambio iteracion-17 - Seleccionar todos los resultados."""
        TariffFactory.create_batch(3, owner=user, unit_type=M2)
        lineal = TariffFactory(owner=user, unit_type=ML)

        response = authenticated_client.post(
            f"{BULK_DELETE}?unit_type={M2}", {"select_all": True}
        )

        assert response.data["processed"] == 3
        assert list(Tariff.objects.filter(owner=user)) == [lineal]

    def test_uno_de_otra_cuenta_no_se_toca(self, user, authenticated_client) -> None:
        ajeno = TariffFactory()

        response = authenticated_client.post(BULK_DELETE, {"ids": [str(ajeno.id)]})

        assert response.data["failed"] == [
            {"id": str(ajeno.id), "detail": "No encontrado."}
        ]
        assert Tariff.objects.filter(pk=ajeno.pk).exists()
