"""Filtros de GET /api/tariffs/ (api-lists-errors.md §2, iteracion-17 #4)."""

from django_filters import rest_framework as filters

from apps.catalog.models import Tariff
from common.filters import CharInFilter, UUIDInFilter


class TariffFilter(filters.FilterSet):
    """Tipo de unidad (varios a la vez) e ids, para rotular un selector."""

    unit_type = CharInFilter(field_name="unit_type", lookup_expr="in")
    id = UUIDInFilter(field_name="id", lookup_expr="in")

    class Meta:
        model = Tariff
        fields = ("unit_type", "id")
