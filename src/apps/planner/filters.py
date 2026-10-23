"""Filtros de GET /api/plans/ (api-lists-errors.md §2, iteracion-17 #9)."""

from django_filters import rest_framework as filters

from apps.planner.models import Plan
from common.filters import UUIDInFilter


class PlanFilter(filters.FilterSet):
    """Por ids: los resúmenes de unos planos, sin bajar la lista."""

    id = UUIDInFilter(field_name="id", lookup_expr="in")

    class Meta:
        model = Plan
        fields = ("id",)
