"""Admin registration for quotes."""

from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from apps.folios.admin import FolioAssignedAdminMixin
from apps.folios.codes import DocumentType
from apps.quotes.models import Quote, QuoteItem


class QuoteItemInline(TabularInline):
    model = QuoteItem
    extra = 0


@admin.register(Quote)
class QuoteAdmin(FolioAssignedAdminMixin, ModelAdmin):
    folio_document_type = DocumentType.QUOTE
    list_display = ("folio", "client", "status", "plan", "owner", "created_at")
    list_filter = ("status",)
    search_fields = ("folio", "client__name")
    readonly_fields = ("folio",)
    inlines = [QuoteItemInline]


@admin.register(QuoteItem)
class QuoteItemAdmin(ModelAdmin):
    """Las partidas se editan dentro de su cotización; aquí se buscan."""

    list_display = ("name", "quote", "quantity", "unit_price", "from_plan")
    search_fields = ("name", "quote__client__name")
    list_select_related = ("quote",)
