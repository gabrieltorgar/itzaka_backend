"""Línea base del contrato de la API: listas y errores (TDD-B01, iteracion-25 #10).

No sale de una historia: codifica api-lists-errors.md (django-backend-conventions).
Toda lista del URLconf pagina aunque no llegue ``?page`` y declara sus filtros,
su búsqueda y su orden; los errores salen de ``api_exception_handler`` con la
forma de DRF. Lo que es propio del proyecto —búsqueda y orden sin acentos,
desempate por id, listas fuera de las vistas genéricas— lo afirma
``test_list_contract.py`` (iteracion-17), que esta prueba reutiliza.
"""

import inspect
import re
from datetime import date, timedelta

import pytest
from django.conf import settings as dj_settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import ProtectedError
from django.utils.module_loading import import_string
from rest_framework.exceptions import Throttled
from rest_framework.mixins import ListModelMixin
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from common.exceptions import CONFLICT_MESSAGE
from common.pagination import DefaultPagination
from tests.platform.routes import api_routes, is_format_twin
from tests.platform.test_list_contract import LISTS_OUTSIDE_GENERICS

FILTER_BACKENDS = (
    "django_filters.rest_framework.DjangoFilterBackend",
    "rest_framework.filters.SearchFilter",
    "rest_framework.filters.OrderingFilter",
)
#: Vistas que un lote posterior migra, cada una con TransitionalPagination y su
#: marcador (api-lists-errors.md §1): "<módulo>.<Vista>": {"hasta":
#: "YYYY-MM-DD", "lote": K, "motivo": "<por qué>"}, a 90 días o menos.
LIST_CONTRACT_PENDING: dict[str, dict] = {}
CLOSED_CATALOG = re.compile(r"#\s*closed catalog:\s*\S", re.I)
OPT_IN_PAGE = re.compile(
    r"""['"]page(?:_size)?['"]\s+(?:not\s+)?in\s+(?:self\.)?request\.(?:query_params|GET)"""
    r"""|request\.(?:query_params|GET)\.get\(\s*['"]page(?:_size)?['"]"""
)


def test_default_pagination_contract():
    """20 por página, ``?page_size=`` y nunca más de 100.

    Movida de test_list_contract.py, con las mismas afirmaciones.
    """
    rest = dj_settings.REST_FRAMEWORK
    assert rest["DEFAULT_PAGINATION_CLASS"] == "common.pagination.DefaultPagination"
    paginator = import_string(rest["DEFAULT_PAGINATION_CLASS"])
    assert paginator is DefaultPagination
    assert paginator.page_size == 20
    assert paginator.page_size_query_param == "page_size"
    assert paginator.max_page_size == 100


def test_a_list_without_page_is_paginated_too():
    """Sin ``?page`` es la página 1 de 20 en el sobre, nunca la colección entera."""
    paginator = import_string(dj_settings.REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"])()
    request = Request(APIRequestFactory().get("/fake/"))

    page = paginator.paginate_queryset(list(range(25)), request)

    assert page == list(range(20)), "DefaultPagination pagina aunque no llegue ?page"
    assert set(paginator.get_paginated_response(page).data) == {
        "count",
        "next",
        "previous",
        "results",
    }


def _list_views() -> dict:
    """Cada vista de lista del URLconf una vez: un GET ``list`` o un ListModelMixin."""
    views = {}
    for route in api_routes():
        if is_format_twin(route):
            continue
        if route.actions:
            listing = route.actions.get("get") == "list"
        else:
            listing = issubclass(route.cls, ListModelMixin)
        if listing:
            views.setdefault(f"{route.cls.__module__}.{route.cls.__qualname__}", route)
    return views


def _view(route):
    """La vista como la arma DRF (con los initkwargs de as_view), sin ``?page``."""
    view = route.cls(**route.initkwargs)
    view.request = Request(APIRequestFactory().get("/"))
    view.args, view.kwargs, view.format_kwarg = (), {}, None
    return view


def _source(cls) -> str:
    """El código propio de la vista y de sus mixins (apps.*, common.*)."""
    return "\n".join(
        inspect.getsource(k)
        for k in cls.__mro__
        if k.__module__.split(".")[0] in {"apps", "common"}
    )


def _closed_catalog(source: str) -> bool:
    """``pagination_class = None`` con ``# closed catalog: <motivo>`` cerca."""
    lines = source.splitlines()
    return any(
        re.search(r"\bpagination_class\s*=\s*None\b", line)
        and any(CLOSED_CATALOG.search(above) for above in lines[max(0, i - 3) : i + 1])
        for i, line in enumerate(lines)
    )


def test_every_list_route_paginates():
    """LST-B01 · LST-B04: sin ``?page``, una lista responde la página 1 en el sobre.

    Una lista fuera de las vistas genéricas solo pasa si está en
    ``LISTS_OUTSIDE_GENERICS`` (test_list_contract.py), donde una petición real
    comprueba que también pagina.
    """
    offenders = []
    for key, route in _list_views().items():
        if key in LIST_CONTRACT_PENDING:
            continue
        view, source = _view(route), _source(route.cls)
        pagination = getattr(view, "pagination_class", None)
        if pagination is None:
            if f"/{route.route}" in LISTS_OUTSIDE_GENERICS:
                continue
            if not _closed_catalog(source):
                offenders.append(
                    f"{key} ({route.route}): "
                    + (
                        "pagination_class is None sin `# closed catalog: <motivo>`"
                        if hasattr(view, "paginate_queryset")
                        else "no es GenericViewSet/ListAPIView: no usa el paginador"
                    )
                )
            continue
        if issubclass(pagination, CursorPagination):
            continue
        if view.paginate_queryset(list(range(101))) is None:
            offenders.append(
                f"{key} ({route.route}): {pagination.__name__} entrega todo sin ?page"
            )
        if OPT_IN_PAGE.search(source):
            offenders.append(f"{key} ({route.route}): pagina solo si llega ?page")
    assert not offenders, (
        "las listas paginan en cada petición (api-lists-errors.md §1); una vista que "
        "migra un lote posterior va a LIST_CONTRACT_PENDING con su marcador:\n"
        + "\n".join(offenders)
    )


def test_every_list_route_declares_filters_search_and_ordering():
    """LST-B02 · LST-B03: FilterSet, búsqueda declarada, orden en lista blanca.

    ``search_fields`` puede ser vacío cuando la lista no se busca (así lo
    declara test_list_contract.py), pero tiene que estar escrito en la vista.
    """
    required = [import_string(b) for b in FILTER_BACKENDS]
    offenders = []
    for key, route in _list_views().items():
        view = _view(route)
        pagination = getattr(view, "pagination_class", None)
        if key in LIST_CONTRACT_PENDING or pagination is None:
            continue
        cursor = issubclass(pagination, CursorPagination)
        gaps = [] if getattr(view, "search_fields", None) is not None else ["search"]
        gaps += [
            a
            for a in (() if cursor else ("ordering_fields", "ordering"))
            if not getattr(view, a, None)
        ]
        if not (
            getattr(view, "filterset_class", None)
            or getattr(view, "filterset_fields", None)
        ):
            gaps.append("filterset_class")
        if getattr(view, "ordering_fields", None) == "__all__":
            gaps.append('ordering_fields = "__all__"')
        gaps += [
            f"filter_backends sin {b.__name__}"
            for b in (required[:2] if cursor else required)
            if not any(issubclass(x, b) for x in getattr(view, "filter_backends", ()))
        ]
        if gaps:
            offenders.append(f"{key} ({route.route}): {', '.join(gaps)}")
    assert not offenders, (
        "se ignorarían la búsqueda, el orden y los filtros (api-lists-errors.md):\n"
        + "\n".join(offenders)
    )


def test_list_contract_pending_is_dated_and_current():
    """Cada entrada: una lista del URLconf con su marcador, a 90 días o menos."""
    today, views, bad = date.today(), _list_views(), []
    for key, entry in LIST_CONTRACT_PENDING.items():
        until, lote = str(entry.get("hasta", "")), entry.get("lote")
        try:
            due = today <= date.fromisoformat(until) <= today + timedelta(days=90)
        except ValueError:
            due = False
        if not due:
            bad.append(f"{key}: hasta {until or '—'} no está entre hoy y 90 días")
        if not (
            isinstance(lote, int) and lote > 0 and str(entry.get("motivo", "")).strip()
        ):
            bad.append(f"{key}: lote (número) y motivo son obligatorios")
        marker = re.compile(
            rf"#\s*contrato-transitorio:\s*{re.escape(until)}\s*[·\-|,]\s*"
            rf"retiro:\s*lote\s*{lote}\b",
            re.I,
        )
        if key not in views:
            bad.append(f"{key}: no es una lista del URLconf (su migración la quita)")
        elif not marker.search(_source(views[key].cls)):
            bad.append(
                f"{key}: sin `# contrato-transitorio: {until} · retiro: lote {lote}`"
            )
    assert not bad, (
        "migra estas listas o difiere su lote con docs-hub (≤ 90 días):\n"
        + "\n".join(bad)
    )


# ---------- errores (api-lists-errors.md §5, ERR-B01 · iteracion-25 #3)


def test_exception_handler_is_registered():
    assert (
        dj_settings.REST_FRAMEWORK.get("EXCEPTION_HANDLER")
        == "common.exceptions.api_exception_handler"
    )


class _ServiceErrorView(APIView):
    """Una vista cuyo servicio rechaza la operación."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []
    error: Exception | None = None

    def post(self, request):
        raise self.error


def _post(error: Exception):
    request = APIRequestFactory().post("/fake/", {}, format="json")
    return _ServiceErrorView.as_view(error=error)(request)


@pytest.mark.parametrize(
    ("error", "body"),
    [
        (
            DjangoValidationError({"status": "Transición no permitida."}),
            {"status": ["Transición no permitida."]},
        ),
        (
            DjangoValidationError("El pedido ya fue facturado."),
            {"non_field_errors": ["El pedido ya fue facturado."]},
        ),
    ],
)
def test_service_validation_error_returns_400_with_field_dict(error, body):
    response = _post(error)

    assert response.status_code == 400, "sin api_exception_handler, DRF responde 500"
    assert response.data == body


def test_deleting_a_protected_row_is_a_409_that_says_why():
    response = _post(ProtectedError("protected", [Group(pk=1, name="Equipo")]))

    assert response.status_code == 409
    assert response.data["detail"] != CONFLICT_MESSAGE
    assert response.data["detail"].startswith("No se puede eliminar")
    assert str(Group._meta.verbose_name_plural) in response.data["detail"]


def test_a_throttled_request_is_a_429_with_retry_after():
    response = _post(Throttled(wait=30))

    assert response.status_code == 429
    assert response["Retry-After"] == "30"
    assert (
        response.data["detail"]
        == "Demasiados intentos. Intenta de nuevo en 30 segundos."
    )
