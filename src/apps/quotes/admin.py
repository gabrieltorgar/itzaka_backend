"""Admin registration for quotes."""

from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from apps.quotes.models import Quote, QuoteItem


class QuoteItemInline(TabularInline):
    model = QuoteItem
    extra = 0


@admin.register(Quote)
class QuoteAdmin(ModelAdmin):
    list_display = ("id", "client", "status", "plan", "owner", "created_at")
    list_filter = ("status",)
    inlines = [QuoteItemInline]


@admin.register(QuoteItem)
class QuoteItemAdmin(ModelAdmin):
    """Las partidas se editan dentro de su cotización; aquí se buscan."""

    list_display = ("name", "quote", "quantity", "unit_price", "from_plan")
    search_fields = ("name", "quote__client__name")
    list_select_related = ("quote",)
