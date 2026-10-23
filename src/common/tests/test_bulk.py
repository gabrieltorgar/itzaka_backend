"""Base de las acciones en lote (iteracion-17 #1, api-lists-errors.md §4).

Cada módulo prueba sus propias acciones; aquí, la selección que comparten:
por ids, o «todos los resultados» con la búsqueda y los filtros de la lista.
"""

import uuid

import pytest
from rest_framework import serializers, viewsets
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.clients.models import Client
from apps.clients.tests.factories import ClientFactory
from common.bulk import BulkActionMixin, BulkResult, BulkSelectionSerializer


class _Clientes(BulkActionMixin, viewsets.GenericViewSet):
    """Una lista con búsqueda, acotada a un dueño, como las de verdad."""

    search_fields = ("name",)
    owner = None

    def get_queryset(self):
        return Client.objects.filter(owner=self.owner).order_by("name")


def vista(owner, body: dict, query: str = "") -> _Clientes:
    django_request = APIRequestFactory().post(f"/{query}", body, format="json")
    view = _Clientes()
    view.owner = owner
    view.request = Request(django_request, parsers=view.get_parsers())
    view.format_kwarg = None
    return view


class TestLaSeleccion:
    def test_ids_o_todos_los_resultados_nunca_los_dos(self) -> None:
        ambos = BulkSelectionSerializer(
            data={"ids": [str(uuid.uuid4())], "select_all": True}
        )
        ninguno = BulkSelectionSerializer(data={})

        assert not ambos.is_valid()
        assert not ninguno.is_valid()
        assert "Selecciona al menos un registro." in str(ninguno.errors)

    def test_excluir_solo_con_todos_los_resultados(self) -> None:
        seleccion = BulkSelectionSerializer(
            data={"ids": [str(uuid.uuid4())], "exclude_ids": [str(uuid.uuid4())]}
        )

        assert not seleccion.is_valid()
        assert "exclude_ids" in seleccion.errors

    def test_el_tope_dice_cuantos_se_pueden(self, settings) -> None:
        settings.BULK_MAX_ITEMS = 2
        seleccion = BulkSelectionSerializer(
            data={"ids": [str(uuid.uuid4()) for _ in range(3)]}
        )

        assert not seleccion.is_valid()
        assert "Puedes seleccionar hasta 2 registros por acción." in str(
            seleccion.errors
        )

    def test_un_id_repetido_cuenta_una_vez(self) -> None:
        mismo = str(uuid.uuid4())
        seleccion = BulkSelectionSerializer(data={"ids": [mismo, mismo]})

        assert seleccion.is_valid(), seleccion.errors
        assert seleccion.validated_data["ids"] == [uuid.UUID(mismo)]


@pytest.mark.django_db
class TestResolverLaSeleccion:
    def test_por_ids_solo_lo_propio_y_lo_ajeno_es_no_encontrado(self, user) -> None:
        mio = ClientFactory(owner=user)
        ajeno = ClientFactory()
        view = vista(user, {"ids": [str(mio.id), str(ajeno.id)]})

        queryset = view.get_bulk_queryset(view.request)
        result = BulkResult(requested=1, processed=1)
        body = view.bulk_response(result).data

        assert list(queryset) == [mio]
        assert body["requested"] == 2
        assert body["failed"] == [{"id": str(ajeno.id), "detail": "No encontrado."}]
        assert Client.objects.filter(pk=ajeno.pk).exists()

    def test_todos_los_resultados_repite_la_busqueda_de_la_lista(self, user) -> None:
        reyes = ClientFactory(owner=user, name="Reyes y asociados")
        ClientFactory(owner=user, name="Constructora Peña")
        excluido = ClientFactory(owner=user, name="Reyes hermanos")
        view = vista(
            user,
            {"select_all": True, "exclude_ids": [str(excluido.id)]},
            "?search=reyes",
        )

        assert list(view.get_bulk_queryset(view.request)) == [reyes]

    def test_todos_los_resultados_por_encima_del_tope_es_400(
        self, user, settings
    ) -> None:
        settings.BULK_MAX_ITEMS = 2
        ClientFactory.create_batch(3, owner=user)
        view = vista(user, {"select_all": True})

        with pytest.raises(serializers.ValidationError) as error:
            view.get_bulk_queryset(view.request)

        assert "select_all" in error.value.detail
        assert "3 registros" in str(error.value.detail)

    def test_el_motivo_de_una_falla_es_el_texto_del_error(self) -> None:
        from django.core.exceptions import ValidationError as DjangoValidationError

        from common.bulk import error_text

        assert error_text(serializers.ValidationError("Está en una cotización.")) == (
            "Está en una cotización."
        )
        assert (
            error_text(DjangoValidationError("Ya estaba inactivo."))
            == "Ya estaba inactivo."
        )
        assert (
            error_text(
                serializers.ValidationError(
                    {"status": ["No se puede."], "x": ["Otra."]}
                )
            )
            == "No se puede. Otra."
        )

    def test_el_resultado_tiene_la_forma_del_contrato(self) -> None:
        result = BulkResult()
        result.requested = 2
        result.processed = 1
        result.fail("abc", "Está en una cotización")

        assert result.as_dict() == {
            "requested": 2,
            "processed": 1,
            "failed": [{"id": "abc", "detail": "Está en una cotización"}],
        }
