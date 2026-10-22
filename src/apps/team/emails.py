"""El correo que lleva una invitación a colaborar."""

from django.conf import settings

from apps.accounts.models import User
from apps.team.selectors import company_name
from common import mail
from common.branding import Brand, brand_for
from common.emails import render_link_email


def invitation_url(token: str) -> str:
    """El enlace de la pantalla que acepta la invitación."""
    return f"{settings.APP_BASE_URL.rstrip('/')}/invitacion/{token}"


def _invitation(*, brand: Brand, empresa: str, email: str, token: str, days: int):
    """El correo de una invitación, con la marca de la empresa que invita."""
    html = render_link_email(
        brand=brand,
        title="Te invitaron a colaborar",
        intro=(
            f"{empresa} te invita a trabajar con su equipo en CUOTREKA: "
            "cotizaciones, proyectos, cobros y planos de la empresa."
        ),
        url=invitation_url(token),
        label="Aceptar la invitación",
        note=(
            f"La invitación vence en {days} días. Si no esperabas este correo, "
            "puedes ignorarlo: sin el enlace no pasa nada."
        ),
    )
    return mail.Message(to=email, subject=f"{empresa} te invita a CUOTREKA", html=html)


def send_invitation_email(*, account: User, email: str, token: str, days: int) -> bool:
    """Le hace llegar a ``email`` la invitación a la empresa de ``account``.

    Va con la marca de la empresa: es ella quien invita.
    """
    message = _invitation(
        brand=brand_for(user=account),
        empresa=company_name(account=account),
        email=email,
        token=token,
        days=days,
    )
    return mail.send_email(to=message.to, subject=message.subject, html=message.html)


def send_invitation_emails(
    *, account: User, links: list[tuple[str, str]], days: int
) -> bool:
    """Le hace llegar a cada correo de ``links`` (correo, token) su invitación.

    Salen en una sola tanda: veinte envíos seguidos, con su espera cada uno,
    podían pasar del tiempo de la función (iteracion-16).
    """
    brand = brand_for(user=account)
    empresa = company_name(account=account)
    return mail.send_batch(
        [
            _invitation(
                brand=brand, empresa=empresa, email=email, token=token, days=days
            )
            for email, token in links
        ]
    )
