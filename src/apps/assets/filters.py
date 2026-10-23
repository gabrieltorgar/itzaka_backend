"""Filtros de GET /api/plan-assets/ (api-lists-errors.md §2, iteracion-17 #1)."""

from django_filters import rest_framework as filters

from apps.assets.models import PlanAsset


class PlanAssetFilter(filters.FilterSet):
    """Por clase: las texturas o las mallas del mobiliario."""

    class Meta:
        model = PlanAsset
        fields = ("kind",)
