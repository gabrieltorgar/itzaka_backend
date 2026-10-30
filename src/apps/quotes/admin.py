"""Admin registration for quotes."""

from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from apps.quotes.models import Quote, QuoteItem, QuoteItemRoom


class QuoteItemInline(TabularInline):
    model = QuoteItem
    extra = 0


@admin.register(Quote)
class QuoteAdmin(ModelAdmin):
    list_display = ("id", "client", "status", "plan", "owner", "created_at")
    list_filter = ("status",)
    inlines = [QuoteItemInline]


class QuoteItemRoomInline(TabularInline):
    model = QuoteItemRoom
    extra = 0


@admin.register(QuoteItem)
class QuoteItemAdmin(ModelAdmin):
    """Las partidas se editan dentro de su cotización; aquí se buscan."""

    list_display = ("name", "quote", "quantity", "unit_price", "from_plan")
    search_fields = ("name", "quote__client__name")
    list_select_related = ("quote",)
    inlines = [QuoteItemRoomInline]


@admin.register(QuoteItemRoom)
class QuoteItemRoomAdmin(ModelAdmin):
    """Lo que cae en cada habitación (iteracion-25); se edita en su partida."""

    list_display = ("name", "quote_item", "quantity")
    search_fields = ("name", "quote_item__name")
    list_select_related = ("quote_item",)
