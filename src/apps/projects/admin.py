"""Admin registration for projects."""

from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.folios.admin import FolioAssignedAdminMixin
from apps.folios.codes import DocumentType
from apps.projects.models import Evidence, Progress, Project


@admin.register(Project)
class ProjectAdmin(FolioAssignedAdminMixin, ModelAdmin):
    folio_document_type = DocumentType.PROJECT
    list_display = ("folio", "quote", "status", "owner", "created_at")
    list_filter = ("status",)
    search_fields = ("folio",)
    readonly_fields = ("folio",)


@admin.register(Progress)
class ProgressAdmin(ModelAdmin):
    list_display = ("id", "project", "quote_item", "quantity", "date")


@admin.register(Evidence)
class EvidenceAdmin(ModelAdmin):
    list_display = ("id", "progress", "image", "created_at")
