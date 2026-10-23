"""Filtros de las listas del personal (api-lists-errors.md §2, iteracion-17).

``/api/workers/`` (#8), ``/api/assignments/`` y ``/api/worker-payments/`` (#1).
"""

from django.db.models import Exists, OuterRef
from django_filters import rest_framework as filters

from apps.staff.models import Assignment, Worker, WorkerPayment, WorkerService
from common.filters import UUIDInFilter


class WorkerFilter(filters.FilterSet):
    """Con saldo, tipo, quienes hacen un servicio (US-97) e ids."""

    has_balance = filters.BooleanFilter(method="filter_has_balance")
    kind = filters.ChoiceFilter(choices=Worker.Kind.choices)
    service = filters.UUIDFilter(method="filter_service")
    id = UUIDInFilter(field_name="id", lookup_expr="in")

    class Meta:
        model = Worker
        fields = ("has_balance", "kind", "service", "id")

    def filter_has_balance(self, queryset, name, value):
        # ``balance`` lo calcula la consulta (selectors.worker_rows_for_owner).
        return queryset.filter(balance__gt=0) if value else queryset.filter(balance=0)

    def filter_service(self, queryset, name, value):
        # Con Exists y no con un join: cada quien aparece una sola vez.
        does = WorkerService.objects.filter(worker=OuterRef("pk"), tariff_id=value)
        return queryset.filter(Exists(does))


class AssignmentFilter(filters.FilterSet):
    """El reparto de un proyecto o de una persona: ``?project=`` como siempre."""

    project = filters.UUIDFilter(field_name="project")
    worker = filters.UUIDFilter(field_name="worker")

    class Meta:
        model = Assignment
        fields = ("project", "worker")


class WorkerPaymentFilter(filters.FilterSet):
    """Los pagos de una persona o de un proyecto: ``?worker=`` y ``?project=``."""

    worker = filters.UUIDFilter(field_name="worker")
    project = filters.UUIDFilter(field_name="project")

    class Meta:
        model = WorkerPayment
        fields = ("worker", "project")
