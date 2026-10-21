"""Mandar un documento por correo, con la marca de quien lo firma.

El PDF lo arma el navegador —es donde están las fuentes, el logotipo ya
descargado y la vista previa que el arquitecto acaba de mirar—, así que aquí
llega hecho. Lo que pone el servidor es el sobre: el cuerpo del correo pintado
con el membrete de la organización, el texto que corresponde a cada documento
y el envío por Resend.
"""

import logging
import re
from decimal import Decimal, InvalidOperation

from django.conf import settings
from rest_framework.exceptions import ValidationError

from common import mail
from common.branding import brand_for
from common.emails import render_email
from common.validators import PDF, validate_upload

logger = logging.getLogger("apps")


class Kind:
    """Los cuatro documentos que la aplicación sabe entregar."""

    QUOTE = "quote"
    PROJECT_STATUS = "project_status"
    PAYMENT_VOUCHER = "payment_voucher"
    COLLECTION_VOUCHER = "collection_voucher"

    CHOICES = [
        (QUOTE, "Cotización"),
        (PROJECT_STATUS, "Comprobante de estatus de proyecto"),
        (PAYMENT_VOUCHER, "Comprobante de pago"),
        (COLLECTION_VOUCHER, "Comprobante de cobro"),
    ]


#: Cómo se llama el adjunto: lo pone el servidor, no quien sube el archivo.
FILE_PREFIX = {
    Kind.QUOTE: "cotizacion",
    Kind.PROJECT_STATUS: "estatus-de-proyecto",
    Kind.PAYMENT_VOUCHER: "comprobante-de-pago",
    Kind.COLLECTION_VOUCHER: "comprobante-de-cobro",
}


def attachment_name(kind: str, reference: str = "") -> str:
    """``cotizacion-COT-0007.pdf``: el tipo y, si la hay, la referencia."""
    clean = re.sub(r"[^A-Za-z0-9_-]+", "-", reference).strip("-")[:40]
    return f"{FILE_PREFIX[kind]}{'-' + clean if clean else ''}.pdf"


#: Qué dice cada correo: el asunto, el título y la primera línea.
WORDING: dict[str, dict[str, str]] = {
    Kind.QUOTE: {
        "subject": "Tu cotización",
        "title": "Aquí está tu cotización",
        "intro": (
            "Te comparto la cotización de los trabajos que platicamos. "
            "El detalle va en el PDF adjunto."
        ),
        "party": "Cliente",
    },
    Kind.PROJECT_STATUS: {
        "subject": "Avance de tu proyecto",
        "title": "Cómo va tu proyecto",
        "intro": (
            "Te comparto el estado del proyecto: lo que va hecho, lo que sigue "
            "y las cuentas al día. El detalle va en el PDF adjunto."
        ),
        "party": "Cliente",
    },
    Kind.PAYMENT_VOUCHER: {
        "subject": "Comprobante de pago",
        "title": "Comprobante de tu pago",
        "intro": (
            "Este es el comprobante del pago por los trabajos realizados. "
            "El detalle va en el PDF adjunto."
        ),
        "party": "Para",
    },
    Kind.COLLECTION_VOUCHER: {
        "subject": "Comprobante de cobro",
        "title": "Recibimos tu pago",
        "intro": (
            "Gracias por tu pago. Este es el comprobante de lo recibido; "
            "el detalle va en el PDF adjunto."
        ),
        "party": "Cliente",
    },
}


def _amount(value: str) -> str:
    """El importe como lo lee quien recibe el correo, no como viaja en la API."""
    try:
        return f"${Decimal(value):,.2f}"
    except (InvalidOperation, TypeError, ValueError):
        return value


def _rows(kind: str, reference: str, party: str, amount: str) -> list[tuple[str, str]]:
    """Lo que se lee sin abrir el adjunto."""
    rows: list[tuple[str, str]] = []
    if reference:
        rows.append(("Folio", reference))
    if party:
        rows.append((WORDING[kind]["party"], party))
    if amount:
        rows.append(("Importe", _amount(amount)))
    return rows


def send_document(
    *,
    user,
    account=None,
    kind: str,
    to: str,
    file,
    reference: str = "",
    party: str = "",
    amount: str = "",
    message: str = "",
) -> bool:
    """Manda el documento adjunto al correo indicado. Devuelve si salió.

    Sale con la marca de la empresa (``account``; sin ella, la de ``user``) y
    las respuestas le llegan a quien lo manda (``user``): en una empresa con
    colaboradores no tienen por qué ser la misma persona (iteracion-14).

    Raises:
        ValidationError: el adjunto pesa de más, no es un PDF o no hay a quién
            mandarlo.
    """
    if not mail.is_configured():
        raise ValidationError(
            "El envío de correos no está configurado todavía. "
            "Descarga el documento y compártelo como lo haces hoy."
        )

    # Sólo el PDF que genera la aplicación sale con su marca: cualquier otro
    # archivo convertiría el envío en un relevo de malware (iteracion-12).
    limit = settings.DOCUMENT_EMAIL_MAX_BYTES
    validate_upload(
        file,
        allowed=PDF,
        max_bytes=limit,
        too_big=(
            f"El documento pesa más de {limit // (1024 * 1024)} MB y no se puede "
            "enviar por correo."
        ),
        not_allowed="Sólo se envían documentos PDF.",
    )

    wording = WORDING[kind]
    brand = brand_for(user=account or user)
    html = render_email(
        brand=brand,
        title=wording["title"],
        intro=wording["intro"],
        rows=_rows(kind, reference, party, amount),
        note=message or None,
    )
    subject = f"{wording['subject']} — {brand.name}"

    sent = mail.send_email(
        to=to,
        subject=subject,
        html=html,
        reply_to=user.email or None,
        attachments=[
            mail.Attachment(
                filename=attachment_name(kind, reference), content=file.read()
            )
        ],
    )
    logger.info(
        "Document emailed", extra={"kind": kind, "sent": sent, "user_id": str(user.pk)}
    )
    return sent
