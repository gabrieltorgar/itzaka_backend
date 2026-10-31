"""La forma de un folio: tipos de documento, modalidades y claves.

Sin consultas ni modelos, para que los modelos de los documentos lo importen
(su ``default``) sin ciclos.
"""

import re
import secrets
import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

#: Lo que cabe en la clave que elige el usuario.
PREFIX_MAX_LENGTH = 5
#: Lo que cabe en un folio: la clave, el guion y el consecutivo, o el id
#: completo de un documento viejo que repetía sus primeros ocho caracteres.
FOLIO_MAX_LENGTH = 40
#: Los caracteres del folio aleatorio, como lo imprimía el navegador.
AUTO_SUFFIX_LENGTH = 8

PREFIX_PATTERN = re.compile(rf"^[A-Z0-9]{{1,{PREFIX_MAX_LENGTH}}}$")
INVALID_PREFIX = "La clave lleva de 1 a 5 letras o números, sin espacios ni símbolos."


class DocumentType(models.TextChoices):
    """Los documentos que la aplicación emite con folio."""

    QUOTE = "quote", _("Cotizaciones")
    PROJECT = "project", _("Estados de proyecto")
    PAYMENT = "payment", _("Comprobantes de pago")
    WORKER_PAYMENT = "worker_payment", _("Comprobantes de pago a personal")


class Mode(models.TextChoices):
    """Cómo se arma el folio de un tipo de documento."""

    AUTO = "auto", _("Autogenerado")
    SEQUENTIAL = "sequential", _("Con clave")


#: La clave del folio aleatorio de cada tipo: la que los PDFs ya imprimían.
AUTO_PREFIXES: dict[str, str] = {
    DocumentType.QUOTE: "COT",
    DocumentType.PROJECT: "PRO",
    DocumentType.PAYMENT: "REC",
    DocumentType.WORKER_PAYMENT: "PAG",
}


def random_suffix() -> str:
    """Ocho caracteres hexadecimales en mayúsculas, sin sesgo."""
    return secrets.token_hex(AUTO_SUFFIX_LENGTH // 2).upper()


def random_folio(prefix: str) -> str:
    """``COT-1A2B3C4D``: el folio «Autogenerado». Es el ``default`` del campo,
    así que un documento creado fuera de los servicios también lleva uno."""
    return f"{prefix}-{random_suffix()}"


def sequential_folio(prefix: str, number: int) -> str:
    """``VEN-101``: la clave y el consecutivo, sin ceros a la izquierda."""
    return f"{prefix}-{number}"


def legacy_folio(
    prefix: str, value: uuid.UUID | str, length: int = AUTO_SUFFIX_LENGTH
) -> str:
    """El folio que el navegador derivaba del id antes de iteracion-25.

    ``folioFrom('COT', id)``: la clave y los primeros ``length`` caracteres
    alfanuméricos del id en mayúsculas. Lo usan las migraciones para que los
    PDFs ya emitidos no cambien.
    """
    compact = re.sub(r"[^0-9a-zA-Z]", "", str(value)).upper()
    return f"{prefix}-{compact[:length]}"


def normalize_prefix(raw: str | None) -> str:
    """La clave en mayúsculas y sin espacios alrededor; ``""`` si no hay."""
    return (raw or "").strip().upper()


def is_valid_prefix(prefix: str) -> bool:
    """De 1 a 5 letras (A-Z) o números, sin acentos, espacios ni símbolos."""
    return bool(PREFIX_PATTERN.match(prefix))
