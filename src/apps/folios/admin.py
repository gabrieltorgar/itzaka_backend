"""Admin de folios: la configuración se ve y el contador nunca se edita a mano."""

from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.folios.models import FolioCounter, FolioSetting, IssuedFolio
from apps.folios.services import assign_folio


@admin.register(FolioSetting)
class FolioSettingAdmin(ModelAdmin):
    """Se cambia en Organización › Folios de documentos, que valida la clave."""

    list_display = ("owner", "document_type", "mode", "prefix", "updated_at")
    list_filter = ("document_type", "mode")
    search_fields = ("owner__email", "prefix")
    readonly_fields = (
        "owner",
        "document_type",
        "mode",
        "prefix",
        "created_at",
        "updated_at",
    )
    list_select_related = ("owner",)

    def has_add_permission(self, request) -> bool:
        return False


@admin.register(FolioCounter)
class FolioCounterAdmin(ModelAdmin):
    """Bajar un contador repetiría folios: sólo se consulta."""

    list_display = ("owner", "prefix", "last_number", "updated_at")
    search_fields = ("owner__email", "prefix")
    readonly_fields = ("owner", "prefix", "last_number", "created_at", "updated_at")
    list_select_related = ("owner",)

    def has_add_permission(self, request) -> bool:
        return False


@admin.register(IssuedFolio)
class IssuedFolioAdmin(ModelAdmin):
    """Lo que ya salió no se cambia ni se borra: un folio no se reutiliza."""

    list_display = ("folio", "document_type", "owner", "created_at")
    list_filter = ("document_type",)
    search_fields = ("folio", "owner__email")
    readonly_fields = ("owner", "folio", "document_type", "created_at")
    list_select_related = ("owner",)

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


class FolioAssignedAdminMixin:
    """Un documento creado desde el admin toma su folio como en la API.

    Va antes de ``ModelAdmin`` en las bases del admin del documento, que
    declara ``folio_document_type``; el folio se muestra y no se edita.
    """

    folio_document_type: str = ""

    def save_model(self, request, obj, form, change) -> None:
        if not change:
            obj.folio = assign_folio(
                owner=obj.owner, document_type=self.folio_document_type
            )
        super().save_model(request, obj, form, change)
