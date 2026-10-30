"""Payments model: a payment against a project, optionally tied to an element."""

from functools import partial

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.folios.codes import FOLIO_MAX_LENGTH, random_folio
from common.models import TimestampedModel


class Payment(TimestampedModel):
    """A payment received on a project (total, partial or advance)."""

    class Method(models.TextChoices):
        CASH = "cash", _("Efectivo")
        TRANSFER = "transfer", _("Transferencia")

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name=_("propietario"),
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name=_("proyecto"),
    )
    quote_item = models.ForeignKey(
        "quotes.QuoteItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
        verbose_name=_("partida cubierta"),
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name=_("monto")
    )
    method = models.CharField(
        max_length=12,
        choices=Method.choices,
        default=Method.CASH,
        verbose_name=_("método de pago"),
    )
    date = models.DateField(verbose_name=_("fecha"))
    # El folio que imprime el documento (iteracion-25, US-142): lo asigna
    # apps.folios.services.assign_folio al crearlo y no cambia nunca. El
    # default es el «Autogenerado», por si algo lo crea fuera del servicio.
    folio = models.CharField(
        max_length=FOLIO_MAX_LENGTH,
        default=partial(random_folio, "REC"),
        editable=False,
        verbose_name=_("folio"),
    )

    class Meta:
        db_table = "payments_payment"
        ordering = ["date", "created_at"]
        verbose_name = _("pago")
        verbose_name_plural = _("pagos")
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "folio"], name="payments_payment_folio_per_owner"
            )
        ]

    def __str__(self) -> str:
        return f"Pago {self.amount}"
