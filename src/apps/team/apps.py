"""Team app config: colaboradores e invitaciones."""

from django.apps import AppConfig


class TeamConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.team"
    label = "team"
    verbose_name = "Colaboradores"
