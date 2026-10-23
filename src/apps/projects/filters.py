"""Filtros de GET /api/projects/ (api-lists-errors.md §2, iteracion-17 #7)."""

from django_filters import rest_framework as filters

from apps.projects.models import Project
from common.filters import CharInFilter, UUIDInFilter


class ProjectFilter(filters.FilterSet):
    """Estado (varios a la vez) e ids."""

    status = CharInFilter(field_name="status", lookup_expr="in")
    id = UUIDInFilter(field_name="id", lookup_expr="in")

    class Meta:
        model = Project
        fields = ("status", "id")
