"""El correo que lleva una invitación a colaborar."""

from django.conf import settings

from apps.accounts.models import User
from apps.team.selectors import company_name
from common import mail
from common.branding import brand_for
from common.emails import render_link_email


def invitation_url(token: str) -> str:
    """El enlace de la pantalla que acepta la invitación."""
    return f"{settings.APP_BASE_URL.rstrip('/')}/invitacion/{token}"


def send_invitation_email(*, account: User, email: str, token: str, days: int) -> bool:
    """Le hace llegar a ``email`` la invitación a la empresa de ``account``.

    Va con la marca de la empresa: es ella quien invita.
    """
    empresa = company_name(account=account)
    html = render_link_email(
        brand=brand_for(user=account),
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
    return mail.send_email(
        to=email, subject=f"{empresa} te invita a CUOTREKA", html=html
    )
