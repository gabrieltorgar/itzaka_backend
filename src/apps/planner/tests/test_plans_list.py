"""US-78: los planos por páginas y eliminar en lote (iteracion-17 #9).

Fuente: backlog 4.9 → US-78 list_spec y su cambio «iteracion-17».
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework import status

from apps.catalog.tests.factories import TariffFactory
from apps.clients.tests.factories import ClientFactory
from apps.planner.models import Plan
from apps.quotes.models import Quote
from apps.quotes.services import create_quote

URL = "/api/plans/"
BULK_DELETE = "/api/plans/bulk/delete/"


def plano(user, name: str, *, hace_dias: int = 0) -> Plan:
    plan = Plan.objects.create(owner=user, name=name, document={})
    # La fecha se fija: dos altas seguidas pueden caer en el mismo instante.
    Plan.objects.filter(pk=plan.pk).update(
        updated_at=timezone.now() - timedelta(days=hace_dias)
    )
    return plan


def nombres(response) -> list[str]:
    return [row["name"] for row in response.data["results"]]


@pytest.mark.django_db
class TestLosPlanosPorPaginas:
    def test_la_lista_se_corta_en_paginas(self, user, authenticated_client) -> None:
        """Cambio iteracion-17 - La lista se corta en páginas."""
        for n in range(45):
            plano(user, f"Plano {n:02d}", hace_dias=n)

        response = authenticated_client.get(URL)

        assert response.data["count"] == 45
        assert len(response.data["results"]) == 20
        assert nombres(response)[:2] == ["Plano 00", "Plano 01"]
        assert "document" not in response.data["results"][0]

    def test_sincronizar_pide_paginas_de_cien(self, user, authenticated_client) -> None:
        """Cambio iteracion-17 - Sincronizar no es descargar todo de una vez."""
        for n in range(150):
            Plan.objects.create(owner=user, name=f"P{n}", document={})

        primera = authenticated_client.get(URL, {"page_size": 100})
        segunda = authenticated_client.get(URL, {"page_size": 100, "page": 2})

        assert len(primera.data["results"]) == 100
        assert primera.data["next"] is not None
        assert len(segunda.data["results"]) == 50
        assert segunda.data["next"] is None

    def test_busca_y_ordena_por_nombre_sin_acentos(
        self, user, authenticated_client
    ) -> None:
        plano(user, "Zapata")
        plano(user, "Ático Álvarez")
        plano(user, "Casa Muñoz")

        buscado = authenticated_client.get(URL, {"search": "munoz"})
        por_nombre = authenticated_client.get(URL, {"ordering": "name"})

        assert nombres(buscado) == ["Casa Muñoz"]
        assert nombres(por_nombre) == ["Ático Álvarez", "Casa Muñoz", "Zapata"]

    def test_un_orden_desconocido_se_ignora(self, user, authenticated_client) -> None:
        plano(user, "Viejo", hace_dias=3)
        plano(user, "Nuevo")

        response = authenticated_client.get(URL, {"ordering": "document"})

        assert nombres(response) == ["Nuevo", "Viejo"]


@pytest.mark.django_db
class TestEliminarVarios:
    """Cambio iteracion-17 - Eliminar varios."""

    def test_elimina_los_elegidos(self, user, authenticated_client) -> None:
        a, b, c = (plano(user, name) for name in ("A", "B", "C"))
        queda = plano(user, "Queda")

        response = authenticated_client.post(
            BULK_DELETE, {"ids": [str(a.id), str(b.id), str(c.id)]}
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {"requested": 3, "processed": 3, "failed": []}
        assert list(Plan.objects.filter(owner=user)) == [queda]

    def test_la_cotizacion_de_un_plano_eliminado_se_queda(
        self, user, authenticated_client
    ) -> None:
        plan = plano(user, "Casa Pérez")
        quote = create_quote(
            owner=user,
            client=ClientFactory(owner=user),
            items_data=[
                {"tariff": TariffFactory(owner=user), "quantity": Decimal("1")}
            ],
            plan=plan,
        )

        authenticated_client.post(BULK_DELETE, {"ids": [str(plan.id)]})

        assert Quote.objects.get(pk=quote.pk).plan is None

    def test_uno_de_otra_cuenta_es_no_encontrado(
        self, user, authenticated_client, user_factory
    ) -> None:
        ajeno = Plan.objects.create(owner=user_factory(), name="Ajeno", document={})

        response = authenticated_client.post(BULK_DELETE, {"ids": [str(ajeno.id)]})

        assert response.data["failed"] == [
            {"id": str(ajeno.id), "detail": "No encontrado."}
        ]
        assert Plan.objects.filter(pk=ajeno.pk).exists()

    def test_sin_sesion_es_401(self, api_client) -> None:
        response = api_client.post(BULK_DELETE, {"ids": []})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
