"""Filtros de las listas de obra (api-lists-errors.md §2, iteracion-17).

``/api/projects/`` (#7) y ``/api/progresses/`` (#1).
"""

from django_filters import rest_framework as filters

from apps.projects.models import Progress, Project
from common.filters import CharInFilter, UUIDInFilter


class ProgressFilter(filters.FilterSet):
    """Los avances de un proyecto, de una partida o de una persona."""

    project = filters.UUIDFilter(field_name="project")
    quote_item = filters.UUIDFilter(field_name="quote_item")
    worker = filters.UUIDFilter(field_name="worker")

    class Meta:
        model = Progress
        fields = ("project", "quote_item", "worker")


class ProjectFilter(filters.FilterSet):
    """Estado (varios a la vez) e ids."""

    status = CharInFilter(field_name="status", lookup_expr="in")
    id = UUIDInFilter(field_name="id", lookup_expr="in")

    class Meta:
        model = Project
        fields = ("status", "id")
