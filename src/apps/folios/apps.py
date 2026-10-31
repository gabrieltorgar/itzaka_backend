"""Folios app config: cómo se numeran los documentos de cada empresa."""

from django.apps import AppConfig


class FoliosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.folios"
    label = "folios"
    verbose_name = "Folios de documentos"
