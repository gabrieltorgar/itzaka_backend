"""Admin registration for staff."""

from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from apps.staff.models import Assignment, Worker, WorkerPayment, WorkerService


class WorkerServiceInline(TabularInline):
    model = WorkerService
    extra = 0


@admin.register(Worker)
class WorkerAdmin(ModelAdmin):
    list_display = ("name", "kind", "is_self", "phone", "owner", "created_at")
    list_filter = ("kind", "is_self", "is_active")
    search_fields = ("name", "phone", "email")
    inlines = [WorkerServiceInline]


@admin.register(Assignment)
class AssignmentAdmin(ModelAdmin):
    list_display = ("worker", "quote_item", "quantity", "unit_price", "created_at")
    search_fields = ("worker__name", "quote_item__name")


@admin.register(WorkerPayment)
class WorkerPaymentAdmin(ModelAdmin):
    list_display = ("worker", "amount", "method", "date", "project", "owner")
    list_filter = ("method",)
    search_fields = ("worker__name",)


@admin.register(WorkerService)
class WorkerServiceAdmin(ModelAdmin):
    """Lo que cobra cada quien por servicio; se edita dentro de su persona."""

    list_display = ("worker", "tariff", "unit_price")
    search_fields = ("worker__name", "tariff__name")
    list_select_related = ("worker", "tariff")
