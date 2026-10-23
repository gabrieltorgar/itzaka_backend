"""Catalog business logic."""

import logging

from django.db import transaction
from django.db.models import QuerySet
from rest_framework.exceptions import ValidationError

from apps.catalog.models import Tariff
from common.bulk import BulkResult, error_text
from common.wording import quotes_phrase

logger = logging.getLogger("apps")


def quotes_using(tariff: Tariff) -> int:
    """En cuántas cotizaciones distintas aparece el servicio."""
    return tariff.quote_items.values("quote_id").distinct().count()


def delete_tariff(*, tariff: Tariff) -> None:
    """Borra un servicio que no está en ninguna cotización.

    Una cotización guarda su propia copia del nombre y del precio, pero sigue
    apuntando al servicio del que salió: el reparto y el precio de cada
    trabajador se buscan por él. Por eso sólo se borra el que nunca se cotizó.

    Quien del personal lo tenía entre lo que hace, deja de tenerlo: no queda
    un trato apuntando a un servicio que ya no existe.

    Raises:
        ValidationError: el servicio está en al menos una cotización.
    """
    count = quotes_using(tariff)
    if count:
        raise ValidationError(
            f"No se puede borrar: el servicio está en {quotes_phrase(count)}."
        )
    tariff_id = str(tariff.pk)
    tariff.delete()
    logger.info("Tariff deleted", extra={"tariff_id": tariff_id})


def delete_tariffs(*, tariffs: QuerySet[Tariff]) -> BulkResult:
    """Borra en lote: cada servicio por su cuenta (US-110 en lote, iteracion-17).

    El que está en una cotización se queda y su motivo va en ``failed``; los
    demás se borran igual. Cada uno en su propio bloque atómico.
    """
    result = BulkResult()
    for tariff in tariffs:
        result.requested += 1
        try:
            with transaction.atomic():
                delete_tariff(tariff=tariff)
        except ValidationError as exc:
            result.fail(tariff.pk, error_text(exc))
        else:
            result.processed += 1
    logger.info(
        "Tariffs deleted in bulk",
        extra={"requested": result.requested, "processed": result.processed},
    )
    return result
