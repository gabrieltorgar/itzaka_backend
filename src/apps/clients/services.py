"""Clients business logic."""

import logging

from django.db import transaction
from django.db.models import QuerySet
from rest_framework.exceptions import ValidationError

from apps.clients.models import Client
from common.bulk import BulkResult, error_text
from common.wording import quotes_phrase

logger = logging.getLogger("apps")


def delete_client(*, client: Client) -> None:
    """Borra un cliente que no está en ninguna cotización.

    Un cliente con cotizaciones es parte de su historia —el documento lleva su
    nombre, el proyecto cobra a su cuenta—, así que sólo se puede borrar el que
    se capturó y nunca llegó a cotizarse.

    Raises:
        ValidationError: el cliente está en al menos una cotización.
    """
    count = client.quotes.count()
    if count:
        raise ValidationError(
            f"No se puede borrar: el cliente está en {quotes_phrase(count)}."
        )
    client_id = str(client.pk)
    client.delete()
    logger.info("Client deleted", extra={"client_id": client_id})


def delete_clients(*, clients: QuerySet[Client]) -> BulkResult:
    """Borra en lote: cada cliente por su cuenta (US-109 en lote, iteracion-17).

    El que está en una cotización se queda y su motivo va en ``failed``; los
    demás se borran igual. Cada uno en su propio bloque atómico.
    """
    result = BulkResult()
    for client in clients:
        result.requested += 1
        try:
            with transaction.atomic():
                delete_client(client=client)
        except ValidationError as exc:
            result.fail(client.pk, error_text(exc))
        else:
            result.processed += 1
    logger.info(
        "Clients deleted in bulk",
        extra={"requested": result.requested, "processed": result.processed},
    )
    return result
