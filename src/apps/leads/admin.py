"""Admin registration for leads."""

from django.contrib import admin

from apps.leads.models import Lead


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "email", "handled", "needs_review", "created_at")
    list_filter = ("handled", "needs_review", "created_at")
    search_fields = ("name", "phone", "email", "message")
    list_editable = ("handled",)
