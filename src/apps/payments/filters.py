"""Filtros de GET /api/payments/ (api-lists-errors.md §2, iteracion-17 #1)."""

from django_filters import rest_framework as filters

from apps.payments.models import Payment


class PaymentFilter(filters.FilterSet):
    """Los pagos de un proyecto: ``?project=`` como siempre."""

    project = filters.UUIDFilter(field_name="project")

    class Meta:
        model = Payment
        fields = ("project",)
