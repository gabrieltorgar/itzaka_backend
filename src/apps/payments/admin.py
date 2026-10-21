"""Admin registration for payments."""

from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.payments.models import Payment


@admin.register(Payment)
class PaymentAdmin(ModelAdmin):
    list_display = ("id", "project", "amount", "date", "owner", "created_at")
