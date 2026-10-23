"""Filtros compartidos de las listas (api-lists-errors.md §2).

Un filtro de varios valores llega separado por comas (?status=draft,in_project)
y filtra por cualquiera de ellos; un valor solo también sirve.
"""

from django_filters import rest_framework as filters


class CharInFilter(filters.BaseInFilter, filters.CharFilter):
    """?status=draft,in_project → status__in."""


class UUIDInFilter(filters.BaseInFilter, filters.UUIDFilter):
    """?client=<uuid>,<uuid> → client_id__in, cada valor validado como UUID."""


class NumberInFilter(filters.BaseInFilter, filters.NumberFilter):
    """?quantity=1,5,10 → quantity__in."""
