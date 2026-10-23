"""Línea base del contrato de listas (iteracion-17 #3 · VAL-06 · US-77 · US-79 · US-80).

Las listas del API entregaban todos los registros de una vez, sin filtros de
django-filter ni búsqueda, y las pantallas los paginaban en el navegador. Ahora
toda vista que lista pagina con ``DefaultPagination``, declara sus filtros, su
búsqueda y una lista blanca de orden, y su orden por omisión termina en un
desempate único (django-backend-conventions → api-lists-errors.md §2). Las
acciones en lote van por ``bulk/<acción>/`` con su propio límite. Una vista
nueva que no lo cumpla deja esto en rojo.
"""

import pytest
from django.urls import URLPattern, URLResolver, get_resolver
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import GenericAPIView
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from common.pagination import DefaultPagination
from common.search import (
    AccentInsensitiveOrderingFilter,
    AccentInsensitiveSearchFilter,
)

TIE_BREAKERS = {"id", "-id", "pk", "-pk"}

#: Listas que no son el queryset de una vista genérica de DRF. Cada una dice
#: por qué y la prueba de abajo comprueba que también pagina.
LISTS_OUTSIDE_GENERICS = {
    # apps.team.views.TeamView
    "/api/collaborators/": "junta colaboradores e invitaciones",
    # apps.assets.views.CatalogModelViewSet
    "/api/plan-models/": "fichas del editor tal como las escribe",
}


def _routes(patterns, prefix=""):
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            yield from _routes(pattern.url_patterns, prefix + str(pattern.pattern))
        elif isinstance(pattern, URLPattern):
            yield prefix + str(pattern.pattern), pattern.callback


ROUTES = list(_routes(get_resolver().url_patterns))


def _name(cls) -> str:
    return f"{cls.__module__}.{cls.__name__}"


def _list_views() -> dict[str, type]:
    """Las vistas enrutadas que responden una lista (su acción ``list``)."""
    views = {}
    for _route, callback in ROUTES:
        cls = getattr(callback, "cls", None)
        actions = getattr(callback, "actions", None) or {}
        if cls is not None and "list" in actions.values():
            views[_name(cls)] = cls
    return views


LIST_VIEWS = _list_views()
GENERIC_LISTS = {
    name: cls for name, cls in LIST_VIEWS.items() if issubclass(cls, GenericAPIView)
}


def _bulk_routes() -> list[tuple[str, object]]:
    return [(route, callback) for route, callback in ROUTES if "bulk/" in route]


def test_default_pagination_contract(settings) -> None:
    rest = settings.REST_FRAMEWORK
    assert rest["DEFAULT_PAGINATION_CLASS"] == "common.pagination.DefaultPagination"
    assert DefaultPagination.page_size == 20
    assert DefaultPagination.page_size_query_param == "page_size"
    assert DefaultPagination.max_page_size == 100


def test_default_filter_backends(settings) -> None:
    """django-filter, búsqueda y orden; los dos últimos sin distinguir acentos."""
    assert tuple(settings.REST_FRAMEWORK["DEFAULT_FILTER_BACKENDS"]) == (
        "django_filters.rest_framework.DjangoFilterBackend",
        "common.search.AccentInsensitiveSearchFilter",
        "common.search.AccentInsensitiveOrderingFilter",
    )
    assert issubclass(AccentInsensitiveSearchFilter, SearchFilter)
    assert issubclass(AccentInsensitiveOrderingFilter, OrderingFilter)


def test_bulk_settings(settings) -> None:
    assert settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["bulk"]
    assert settings.BULK_MAX_ITEMS == 500


def test_every_routed_list_is_known() -> None:
    """Una vista que lista y no es genérica tiene que estar anotada."""
    unknown = [
        name for name, cls in LIST_VIEWS.items() if not issubclass(cls, GenericAPIView)
    ]
    assert unknown == ["apps.assets.views.CatalogModelViewSet"], (
        "lista fuera de las vistas genéricas: anótala en LISTS_OUTSIDE_GENERICS"
    )


@pytest.mark.parametrize("name", sorted(GENERIC_LISTS))
def test_every_list_pages_filters_searches_and_orders_on_the_server(name) -> None:
    cls = GENERIC_LISTS[name]

    assert cls.pagination_class is not None and issubclass(
        cls.pagination_class, DefaultPagination
    ), f"{name}: sin DefaultPagination entrega todo de golpe"
    backends = tuple(cls.filter_backends)
    for backend in (
        DjangoFilterBackend,
        AccentInsensitiveSearchFilter,
        AccentInsensitiveOrderingFilter,
    ):
        assert any(issubclass(b, backend) for b in backends), (
            f"{name}: le falta {backend.__name__}"
        )
    assert getattr(cls, "filterset_class", None) is not None, (
        f"{name}: declara su filterset_class"
    )
    assert getattr(cls, "search_fields", None) is not None, (
        f"{name}: declara search_fields (vacío, si no se busca)"
    )
    ordering_fields = getattr(cls, "ordering_fields", None)
    assert isinstance(ordering_fields, (tuple, list)) and ordering_fields, (
        f"{name}: ordering_fields es una lista blanca, nunca '__all__'"
    )
    ordering = tuple(getattr(cls, "ordering", None) or ())
    assert ordering and ordering[-1] in TIE_BREAKERS, (
        f"{name}: el orden por omisión termina en el id"
    )
    allowed = {field.lstrip("-") for field in ordering_fields} | {"id", "pk"}
    assert {term.lstrip("-") for term in ordering} <= allowed, (
        f"{name}: el orden por omisión usa campos de su lista blanca"
    )
    text_fields = set(getattr(cls, "ordering_text_fields", ()))
    assert text_fields <= set(ordering_fields), (
        f"{name}: ordering_text_fields sale de ordering_fields"
    )


@pytest.mark.django_db
@pytest.mark.parametrize("url", sorted(LISTS_OUTSIDE_GENERICS))
def test_lists_outside_generics_page_too(url) -> None:
    client = APIClient()
    client.force_authenticate(user=UserFactory())

    response = client.get(url, {"page_size": 1})

    assert response.status_code == 200
    assert set(response.data) == {"count", "next", "previous", "results"}


def test_bulk_actions_have_their_own_rate_limit() -> None:
    routes = _bulk_routes()
    assert routes, "las acciones en lote van por bulk/<acción>/"
    for route, callback in routes:
        cls = callback.cls
        actions = getattr(callback, "actions", None) or {}
        scopes = {
            getattr(getattr(cls, method), "kwargs", {}).get("throttle_scope")
            for method in actions.values()
        } or {getattr(cls, "throttle_scope", None)}
        assert scopes == {"bulk"}, f"{route}: throttle_scope 'bulk'"
