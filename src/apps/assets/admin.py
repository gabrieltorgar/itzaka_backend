"""Admin registration for the editor's files and catalogue."""

from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.assets.models import CatalogModel, PlanAsset


@admin.register(PlanAsset)
class PlanAssetAdmin(ModelAdmin):
    list_display = ("path", "kind", "size", "owner", "created_at")
    list_filter = ("kind",)
    search_fields = ("path",)


@admin.register(CatalogModel)
class CatalogModelAdmin(ModelAdmin):
    list_display = ("model_id", "owner", "created_at")
    search_fields = ("model_id",)
