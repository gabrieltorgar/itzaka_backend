"""Folios de documentos (iteracion-25, US-142).

Tres piezas, todas de la empresa (``owner``, la cuenta del administrador):

- ``FolioSetting``: la modalidad y la clave de cada tipo de documento.
- ``FolioCounter``: el último número de cada clave. Nunca baja: volver a una
  clave sigue donde se quedó.
- ``IssuedFolio``: cada folio que salió. Su restricción única es la que
  garantiza en la base que dentro de una empresa no se repite ninguno, ni
  entre tipos de documento que comparten clave; no se borra con el documento.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.folios.codes import FOLIO_MAX_LENGTH, PREFIX_MAX_LENGTH, DocumentType, Mode
from common.models import TimestampedModel


class FolioSetting(TimestampedModel):
    """Cómo arma sus folios una empresa para un tipo de documento."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="folio_settings",
        verbose_name=_("empresa"),
    )
    document_type = models.CharField(
        max_length=20, choices=DocumentType.choices, verbose_name=_("tipo de documento")
    )
    mode = models.CharField(
        max_length=12,
        choices=Mode.choices,
        default=Mode.AUTO,
        verbose_name=_("modalidad"),
    )
    prefix = models.CharField(
        max_length=PREFIX_MAX_LENGTH, blank=True, default="", verbose_name=_("clave")
    )

    class Meta:
        db_table = "folios_setting"
        ordering = ["document_type", "id"]
        verbose_name = _("configuración de folios")
        verbose_name_plural = _("configuraciones de folios")
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "document_type"], name="folios_setting_one_per_type"
            )
        ]

    def __str__(self) -> str:
        kind, mode = self.get_document_type_display(), self.get_mode_display()
        return f"{kind}: {mode} {self.prefix}".strip()


class FolioCounter(TimestampedModel):
    """El último número que salió con una clave en una empresa."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="folio_counters",
        verbose_name=_("empresa"),
    )
    prefix = models.CharField(max_length=PREFIX_MAX_LENGTH, verbose_name=_("clave"))
    last_number = models.PositiveBigIntegerField(
        default=0, verbose_name=_("último número")
    )

    class Meta:
        db_table = "folios_counter"
        ordering = ["prefix", "id"]
        verbose_name = _("contador de folios")
        verbose_name_plural = _("contadores de folios")
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "prefix"], name="folios_counter_per_prefix"
            )
        ]

    def __str__(self) -> str:
        return f"{self.prefix}-{self.last_number}"


class IssuedFolio(models.Model):
    """Un folio que ya salió en una empresa: nunca vuelve a salir."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="issued_folios",
        verbose_name=_("empresa"),
    )
    folio = models.CharField(max_length=FOLIO_MAX_LENGTH, verbose_name=_("folio"))
    document_type = models.CharField(
        max_length=20, choices=DocumentType.choices, verbose_name=_("tipo de documento")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("emitido en"))

    class Meta:
        db_table = "folios_issued"
        ordering = ["-created_at", "-id"]
        verbose_name = _("folio emitido")
        verbose_name_plural = _("folios emitidos")
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "folio"], name="folios_issued_unique_per_owner"
            )
        ]

    def __str__(self) -> str:
        return self.folio
