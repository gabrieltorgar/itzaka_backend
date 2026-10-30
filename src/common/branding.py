"""Con qué cara sale un correo: la de la organización, o la de Itzaka.

Es la misma regla que ya siguen los PDF —el membrete manda cuando está
configurado— con una diferencia que pidió el negocio: cuando el documento sale
con la marca del arquitecto, el pie dice que va «optimizado por Itzaka».
Cuando la cuenta no ha configurado nada, el correo es de Itzaka y ese pie
sobraría.
"""

from dataclasses import dataclass

from django.conf import settings

from apps.accounts.models import DEFAULT_ORGANIZATION_COLOR
from common.brand import BRAND_NAME

#: El logotipo propio, para cuando la cuenta todavía no tiene el suyo.
#: El símbolo a color en PNG @2x con fondo transparente: muchos clientes de
#: correo no muestran SVG. Lo publica el frontend.
BRAND_LOGO_PATH = "/email-logo@2x.png"

#: El encabezado de la casa: blanco, para que el logo a color se lea (manual v2.0).
HOUSE_BAND = "#FFFFFF"
HOUSE_INK = "#141517"
#: Sobre la banda de color de un membrete, el nombre va en blanco.
LETTERHEAD_INK = "#FFFFFF"

#: El pie que acompaña a los documentos con marca del arquitecto.
OPTIMIZED_BY = f"optimizado por {BRAND_NAME}"


@dataclass(frozen=True)
class Brand:
    """Nombre, color y logotipo con los que se pinta un correo."""

    name: str
    color: str
    logo_url: str
    #: Si el pie lleva el «optimizado por Itzaka».
    optimized: bool
    #: El fondo del encabezado (vacío: el color de la marca) y el nombre encima.
    band: str = ""
    ink: str = LETTERHEAD_INK
    #: Si el nombre se escribe como el de Itzaka junto al símbolo: «ITZAKA»,
    #: Inter 800 a +0.08 em, con la firma del grupo debajo (manual v2.0).
    wordmark: bool = False


def house_brand() -> Brand:
    """La marca de la casa."""
    return Brand(
        name=BRAND_NAME,
        color=DEFAULT_ORGANIZATION_COLOR,
        logo_url=f"{settings.APP_BASE_URL.rstrip('/')}{BRAND_LOGO_PATH}",
        optimized=False,
        band=HOUSE_BAND,
        ink=HOUSE_INK,
        wordmark=True,
    )


def brand_for(*, user) -> Brand:
    """La marca con la que firma esa cuenta.

    Una organización cuenta como configurada en cuanto tiene nombre o
    logotipo: el color solo no basta, porque todas las cuentas nacen con uno.
    """
    organization = getattr(user, "organization", None)
    if organization is None:
        return house_brand()

    logo = organization.logo.url if organization.logo else ""
    if not organization.name and not logo:
        return house_brand()

    return Brand(
        name=organization.name or BRAND_NAME,
        color=organization.color or DEFAULT_ORGANIZATION_COLOR,
        logo_url=logo,
        optimized=True,
    )
