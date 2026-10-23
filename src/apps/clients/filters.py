"""Filtros de GET /api/clients/ (api-lists-errors.md §2, iteracion-17 #5)."""

from django.db.models import Q
from django_filters import rest_framework as filters

from apps.clients.models import Client
from common.filters import UUIDInFilter


class ClientFilter(filters.FilterSet):
    """Con o sin contacto (teléfono o correo) e ids, para rotular un selector."""

    has_contact = filters.BooleanFilter(method="filter_has_contact")
    id = UUIDInFilter(field_name="id", lookup_expr="in")

    class Meta:
        model = Client
        fields = ("has_contact", "id")

    def filter_has_contact(self, queryset, name, value):
        with_contact = ~Q(phone="") | ~Q(email="")
        return (
            queryset.filter(with_contact) if value else queryset.exclude(with_contact)
        )
