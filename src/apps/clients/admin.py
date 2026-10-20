"""Admin registration for clients."""

from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.clients.models import Client


@admin.register(Client)
class ClientAdmin(ModelAdmin):
    list_display = ("name", "phone", "email", "owner", "created_at")
    search_fields = ("name", "phone", "email")
