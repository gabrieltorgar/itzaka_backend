"""Contrato de listas: el servidor pagina, busca, filtra y ordena (iteracion-17 #1).

Fuente: US-77 y US-79 (backlog 4.9) y api-lists-errors.md §1. Las listas de
cada módulo prueban sus propios filtros; aquí vive lo que comparten todas.
"""

import pytest
from django.conf import settings
from rest_framework import status
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.clients.models import Client
from apps.clients.tests.factories import ClientFactory
from common.search import AccentInsensitiveOrderingFilter, AccentInsensitiveSearchFilter

CLIENTS_URL = "/api/clients/"


@pytest.mark.django_db
class TestSiemprePagina:
    """US-77: el servidor corta las páginas aunque no se pida una."""

    def test_without_asking_llega_la_primera_pagina_de_veinte(
        self, user, authenticated_client
    ) -> None:
        ClientFactory.create_batch(25, owner=user)

        response = authenticated_client.get(CLIENTS_URL)

        assert response.status_code == status.HTTP_200_OK
        assert set(response.data) == {"count", "next", "previous", "results"}
        assert response.data["count"] == 25
        assert len(response.data["results"]) == 20
        assert response.data["next"] is not None

    def test_page_size_acotado_a_cien(self, user, authenticated_client) -> None:
        ClientFactory.create_batch(105, owner=user)

        response = authenticated_client.get(CLIENTS_URL, {"page_size": 1000})

        assert len(response.data["results"]) == 100

    def test_un_page_size_invalido_vuelve_a_veinte(
        self, user, authenticated_client
    ) -> None:
        ClientFactory.create_batch(25, owner=user)

        for valor in ("abc", "0"):
            response = authenticated_client.get(CLIENTS_URL, {"page_size": valor})
            assert len(response.data["results"]) == 20, valor

    def test_una_pagina_que_no_existe_es_404(self, user, authenticated_client) -> None:
        ClientFactory.create_batch(3, owner=user)

        response = authenticated_client.get(CLIENTS_URL, {"page": 9})

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in response.data

    def test_los_empates_no_se_repiten_ni_se_pierden_entre_paginas(
        self, user, authenticated_client
    ) -> None:
        """Caso de borde - Ordenar por una columna repetida no salta filas."""
        ClientFactory.create_batch(7, owner=user, name="Mismo nombre")

        vistos = []
        for page in (1, 2, 3):
            response = authenticated_client.get(
                CLIENTS_URL, {"page": page, "page_size": 3, "ordering": "name"}
            )
            vistos += [row["id"] for row in response.data["results"]]

        assert len(vistos) == 7
        assert len(set(vistos)) == 7

    def test_otra_cuenta_no_cuenta_en_el_total(
        self, user, authenticated_client
    ) -> None:
        ClientFactory.create_batch(2, owner=user)
        ClientFactory.create_batch(5)

        response = authenticated_client.get(CLIENTS_URL)

        assert response.data["count"] == 2


class _ListaDeClientes:
    """Lo único que el filtro de búsqueda lee de la vista."""

    search_fields = ("name", "email")


def buscar(termino: str) -> list[str]:
    request = Request(APIRequestFactory().get("/", {"search": termino}))
    queryset = AccentInsensitiveSearchFilter().filter_queryset(
        request, Client.objects.order_by("name"), _ListaDeClientes()
    )
    return list(queryset.values_list("name", flat=True))


@pytest.mark.django_db
class TestBuscarSinAcentos:
    """US-79: la búsqueda del servidor no exige acentos ni mayúsculas."""

    def test_mucino_encuentra_a_mucino_con_enie(self) -> None:
        ClientFactory(name="Arquitectos Muciño")
        ClientFactory(name="Constructora Reyes")

        assert buscar("mucino") == ["Arquitectos Muciño"]

    def test_con_acento_y_en_mayusculas_tambien(self) -> None:
        ClientFactory(name="José Ángel Pérez")

        for termino in ("ANGEL", "pérez", "jose angel", "ÁNGEL"):
            assert buscar(termino) == ["José Ángel Pérez"], termino

    def test_busca_en_cada_campo_declarado(self) -> None:
        ClientFactory(name="Reyes", email="contacto@peñasco.mx")

        assert buscar("penasco") == ["Reyes"]

    def test_sin_termino_no_filtra(self) -> None:
        ClientFactory.create_batch(3)

        assert len(buscar("")) == 3


class _ListaOrdenable:
    """Lo que el filtro de orden lee de la vista."""

    ordering_fields = ("name", "created_at")
    ordering_text_fields = ("name",)
    ordering = ("name",)


def ordenar(ordering: str | None) -> list[str]:
    query = {"ordering": ordering} if ordering is not None else {}
    request = Request(APIRequestFactory().get("/", query))
    queryset = AccentInsensitiveOrderingFilter().filter_queryset(
        request, Client.objects.all(), _ListaOrdenable()
    )
    return list(queryset.values_list("name", flat=True))


@pytest.mark.django_db
class TestOrdenarComoSeLee:
    """US-79: el orden alfabético no depende de acentos ni mayúsculas.

    Con la intercalación C de PostgreSQL, «Álvarez» quedaría después de
    «zapata» y «Zapata» antes de «alvarez»; el navegador ordenaba bien.
    """

    def test_de_la_a_a_la_z(self) -> None:
        for nombre in ("zapata", "Álvarez", "Muñoz", "beltrán"):
            ClientFactory(name=nombre)

        assert ordenar(None) == ["Álvarez", "beltrán", "Muñoz", "zapata"]
        assert ordenar("-name") == ["zapata", "Muñoz", "beltrán", "Álvarez"]

    def test_lo_que_no_es_texto_se_ordena_igual(self) -> None:
        viejo = ClientFactory(name="B")
        nuevo = ClientFactory(name="A")

        assert ordenar("-created_at") == [nuevo.name, viejo.name]

    def test_un_campo_fuera_de_la_lista_blanca_se_ignora(self) -> None:
        ClientFactory(name="b")
        ClientFactory(name="A")

        assert ordenar("owner__email") == ["A", "b"]


class TestBackendsPorOmision:
    """api-lists-errors.md §1: paginar, filtrar, buscar y ordenar en el servidor."""

    def test_settings(self) -> None:
        rest = settings.REST_FRAMEWORK
        assert rest["DEFAULT_PAGINATION_CLASS"] == "common.pagination.DefaultPagination"
        assert list(rest["DEFAULT_FILTER_BACKENDS"]) == [
            "django_filters.rest_framework.DjangoFilterBackend",
            "common.search.AccentInsensitiveSearchFilter",
            "common.search.AccentInsensitiveOrderingFilter",
        ]

    def test_el_tope_de_las_acciones_en_lote(self) -> None:
        assert settings.BULK_MAX_ITEMS == 500
        assert settings.BULK_COSTLY_MAX_ITEMS == 50
        assert "bulk" in settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]


@pytest.mark.django_db
class TestFiltrosDeVariosValores:
    """api-lists-errors.md §2: ?campo=a,b filtra por cualquiera de los valores."""

    def test_uuid_in_filter_acota_y_valida(self, user) -> None:
        import django_filters

        from common.filters import UUIDInFilter

        class Filtro(django_filters.FilterSet):
            id = UUIDInFilter(field_name="id", lookup_expr="in")

            class Meta:
                model = Client
                fields = ("id",)

        a, b, _ = ClientFactory.create_batch(3, owner=user)

        ok = Filtro({"id": f"{a.id},{b.id}"}, queryset=Client.objects.all())
        malo = Filtro({"id": "no-es-uuid"}, queryset=Client.objects.all())

        assert set(ok.qs) == {a, b}
        assert not malo.is_valid()
