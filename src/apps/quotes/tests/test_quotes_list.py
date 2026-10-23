"""US-13: la lista de cotizaciones del servidor (iteracion-17 #6).

Fuente: backlog 4.9 → US-13 list_spec y su cambio «iteracion-17».
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.tests.factories import TariffFactory
from apps.clients.tests.factories import ClientFactory
from apps.planner.models import Plan
from apps.quotes.models import Quote
from apps.quotes.services import create_quote

URL = "/api/quotes/"


def cotizar(
    user, *, cliente: str = "Constructora Reyes", importe: str = "100", **extra
):
    """Una cotización de ``cliente`` con una sola partida de ``importe``."""
    return create_quote(
        owner=user,
        client=ClientFactory(owner=user, name=cliente),
        items_data=[
            {
                "tariff": TariffFactory(owner=user, unit_price=importe),
                "quantity": Decimal("1"),
            }
        ],
        **extra,
    )


def clientes(response) -> list[str]:
    return [row["client_name"] for row in response.data["results"]]


@pytest.mark.django_db
class TestLaListaDeCotizaciones:
    def test_el_servidor_entrega_una_pagina_de_las_mas_recientes(
        self, user, authenticated_client
    ) -> None:
        """Cambio iteracion-17 - El servidor entrega una página."""
        cotizaciones = [cotizar(user, cliente=f"Cliente {n:02d}") for n in range(25)]
        ahora = timezone.now()
        for dias, quote in enumerate(reversed(cotizaciones)):
            Quote.objects.filter(pk=quote.pk).update(
                created_at=ahora - timedelta(days=dias)
            )

        response = authenticated_client.get(URL)

        assert response.data["count"] == 25
        assert len(response.data["results"]) == 20
        assert clientes(response)[:2] == ["Cliente 24", "Cliente 23"]

    def test_varios_estados_a_la_vez(self, user, authenticated_client) -> None:
        """Cambio iteracion-17 - Varios estados a la vez."""
        cotizar(user, cliente="Borrador")
        en_proyecto = cotizar(user, cliente="En proyecto")
        Quote.objects.filter(pk=en_proyecto.pk).update(status=Quote.Status.IN_PROJECT)

        ambos = authenticated_client.get(URL, {"status": "draft,in_project"})
        solo = authenticated_client.get(URL, {"status": "in_project"})

        assert ambos.data["count"] == 2
        assert clientes(solo) == ["En proyecto"]

    def test_mayor_importe_de_todas(self, user, authenticated_client) -> None:
        """Cambio iteracion-17 - Mayor importe de todas."""
        cotizar(user, cliente="Chica", importe="100")
        cotizar(user, cliente="Grande", importe="9500")
        cotizar(user, cliente="Mediana", importe="2500")

        mayor = authenticated_client.get(URL, {"ordering": "-total"})
        menor = authenticated_client.get(URL, {"ordering": "total"})

        assert clientes(mayor) == ["Grande", "Mediana", "Chica"]
        assert clientes(menor) == ["Chica", "Mediana", "Grande"]
        assert mayor.data["results"][0]["total"] == Decimal("9500.00")

    def test_busca_y_ordena_por_cliente_sin_acentos(
        self, user, authenticated_client
    ) -> None:
        for nombre in ("Zapata", "Álvarez", "Muñoz"):
            cotizar(user, cliente=nombre)

        buscada = authenticated_client.get(URL, {"search": "munoz"})
        por_cliente = authenticated_client.get(URL, {"ordering": "client_name"})

        assert clientes(buscada) == ["Muñoz"]
        assert clientes(por_cliente) == ["Álvarez", "Muñoz", "Zapata"]

    def test_las_de_un_plano(self, user, authenticated_client) -> None:
        """US-133: el plano pide solo sus cotizaciones, no la lista entera."""
        plano = Plan.objects.create(owner=user, name="Casa Pérez", document={})
        otro = Plan.objects.create(owner=user, name="Bodega", document={})
        cotizar(user, cliente="Del plano", plan=plano)
        cotizar(user, cliente="De otro plano", plan=otro)
        cotizar(user, cliente="A mano")

        response = authenticated_client.get(URL, {"plan": str(plano.id)})

        assert clientes(response) == ["Del plano"]
        assert response.data["results"][0]["plan_name"] == "Casa Pérez"

    def test_un_orden_desconocido_se_ignora(self, user, authenticated_client) -> None:
        cotizar(user, cliente="Primera")
        segunda = cotizar(user, cliente="Segunda")
        Quote.objects.filter(pk=segunda.pk).update(
            created_at=timezone.now() + timedelta(days=1)
        )

        response = authenticated_client.get(URL, {"ordering": "owner__email"})

        assert clientes(response) == ["Segunda", "Primera"]

    def test_la_de_otra_cuenta_no_aparece(
        self, user, authenticated_client, user_factory
    ) -> None:
        cotizar(user_factory(), cliente="Ajena")

        assert authenticated_client.get(URL).data["count"] == 0

    def test_cada_cotizacion_se_pide_sola(self, user, authenticated_client) -> None:
        """Cada cotización con su propio pedido: el detalle no baja la lista."""
        quote = cotizar(user, cliente="Constructora Reyes", importe="350")

        response = authenticated_client.get(f"{URL}{quote.id}/")

        assert response.data["client_name"] == "Constructora Reyes"
        assert response.data["total"] == Decimal("350.00")
        assert len(response.data["items"]) == 1
