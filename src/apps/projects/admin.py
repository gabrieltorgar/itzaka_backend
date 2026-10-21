"""Admin registration for projects."""

from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.projects.models import Evidence, Progress, Project


@admin.register(Project)
class ProjectAdmin(ModelAdmin):
    list_display = ("id", "quote", "status", "owner", "created_at")
    list_filter = ("status",)


@admin.register(Progress)
class ProgressAdmin(ModelAdmin):
    list_display = ("id", "project", "quote_item", "quantity", "date")


@admin.register(Evidence)
class EvidenceAdmin(ModelAdmin):
    list_display = ("id", "progress", "image", "created_at")
