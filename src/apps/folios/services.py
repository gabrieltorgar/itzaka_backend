"""Asignar y configurar folios (iteracion-25, US-142).

El folio se asigna aquí, dentro de la transacción que crea el documento, y se
guarda en él: el navegador nunca lo calcula. Cambiar la modalidad o la clave
sólo cambia lo que viene; lo ya emitido no se toca.
"""

import logging

from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from apps.folios.codes import (
    AUTO_PREFIXES,
    INVALID_PREFIX,
    DocumentType,
    Mode,
    is_valid_prefix,
    normalize_prefix,
    random_suffix,
    sequential_folio,
)
from apps.folios.models import FolioCounter, FolioSetting, IssuedFolio

logger = logging.getLogger("apps")

#: Sorteos antes de rendirse: con 16⁸ valores, dos seguidos repetidos ya son
#: un problema del generador, no mala suerte.
AUTO_ATTEMPTS = 10
AUTO_EXHAUSTED = "No se pudo generar un folio nuevo. Inténtalo de nuevo."


def _register(*, owner, document_type: str, folio: str) -> bool:
    """Aparta ``folio`` para la empresa; ``False`` si ya salió antes."""
    try:
        with transaction.atomic():
            IssuedFolio.objects.create(
                owner=owner, folio=folio, document_type=document_type
            )
    except IntegrityError:
        return False
    return True


def _locked_counter(*, owner, prefix: str) -> FolioCounter:
    """El contador de la clave, bloqueado hasta que termine la transacción.

    Dos documentos creados a la vez con la misma clave esperan su turno aquí,
    así que nunca leen el mismo número.
    """
    try:
        with transaction.atomic():
            FolioCounter.objects.get_or_create(owner=owner, prefix=prefix)
    except IntegrityError:
        pass  # otro lo creó al mismo tiempo: existe, que es lo que importa
    return FolioCounter.objects.select_for_update().get(owner=owner, prefix=prefix)


def _setting(*, owner, document_type: str) -> FolioSetting | None:
    return FolioSetting.objects.filter(owner=owner, document_type=document_type).first()


@transaction.atomic
def assign_folio(*, owner, document_type: str) -> str:
    """El folio del documento que se está creando, ya apartado.

    Corre dentro de la transacción del documento: si ésta se deshace, el
    número vuelve al contador y no queda un hueco.

    Raises:
        ValidationError: el sorteo del folio aleatorio repitió todas las veces.
    """
    setting = _setting(owner=owner, document_type=document_type)
    if setting is None or setting.mode == Mode.AUTO:
        prefix = AUTO_PREFIXES[document_type]
        for _ in range(AUTO_ATTEMPTS):
            folio = f"{prefix}-{random_suffix()}"
            if _register(owner=owner, document_type=document_type, folio=folio):
                return folio
        raise ValidationError(AUTO_EXHAUSTED)

    counter = _locked_counter(owner=owner, prefix=setting.prefix)
    while True:
        counter.last_number += 1
        folio = sequential_folio(setting.prefix, counter.last_number)
        # Un número que ya existe (un documento viejo, otro tipo) se salta y no
        # se vuelve a ofrecer: el contador sólo sube.
        if _register(owner=owner, document_type=document_type, folio=folio):
            counter.save(update_fields=["last_number", "updated_at"])
            return folio


def _clean_prefix(*, mode: str, prefix: str | None) -> str:
    if mode == Mode.AUTO:
        return ""
    cleaned = normalize_prefix(prefix)
    if not is_valid_prefix(cleaned):
        raise ValidationError({"prefix": [INVALID_PREFIX]})
    return cleaned


def configure_folios(
    *, owner, document_type: str, mode: str, prefix: str | None
) -> FolioSetting:
    """Guarda la modalidad y la clave de un tipo de documento.

    No toca los documentos ya creados ni los contadores: una clave que vuelve
    sigue en el número donde se quedó.

    Raises:
        ValidationError: ``prefix`` vacío, de más de 5 caracteres o con algo
            que no es letra o número, con «Con clave».
    """
    cleaned = _clean_prefix(mode=mode, prefix=prefix)
    setting, _created = FolioSetting.objects.update_or_create(
        owner=owner,
        document_type=document_type,
        defaults={"mode": mode, "prefix": cleaned},
    )
    logger.info(
        "Folio settings changed",
        extra={"owner_id": str(owner.pk), "document_type": document_type, "mode": mode},
    )
    return setting


def preview_folio(
    *, owner, mode: str, prefix: str | None, document_type: str = DocumentType.QUOTE
) -> str:
    """El folio que saldría ahora, sin apartarlo.

    Con clave dice el número que sigue en el contador (``VEN-101`` si VEN
    llegó a 100); autogenerado, un ejemplo de su forma.

    Raises:
        ValidationError: la clave no es válida.
    """
    cleaned = _clean_prefix(mode=mode, prefix=prefix)
    if mode == Mode.AUTO:
        return f"{AUTO_PREFIXES[document_type]}-{random_suffix()}"
    counter = FolioCounter.objects.filter(owner=owner, prefix=cleaned).first()
    return sequential_folio(cleaned, (counter.last_number if counter else 0) + 1)
