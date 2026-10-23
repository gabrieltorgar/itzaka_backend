"""Filtros de GET /api/quotes/ (api-lists-errors.md §2, iteracion-17 #6)."""

from django_filters import rest_framework as filters

from apps.quotes.models import Quote
from common.filters import CharInFilter, UUIDInFilter


class QuoteFilter(filters.FilterSet):
    """Estado (varios a la vez), las de unos planos (US-133) e ids."""

    status = CharInFilter(field_name="status", lookup_expr="in")
    plan = UUIDInFilter(field_name="plan", lookup_expr="in")
    id = UUIDInFilter(field_name="id", lookup_expr="in")

    class Meta:
        model = Quote
        fields = ("status", "plan", "id")
