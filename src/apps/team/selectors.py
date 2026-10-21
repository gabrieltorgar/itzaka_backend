"""Lecturas de colaboradores e invitaciones."""

from apps.accounts.models import Organization, User
from apps.team.models import Invitation, Membership


def company_name(*, account: User) -> str:
    """Cómo se llama la empresa: el nombre de su organización, o su correo."""
    name = (
        Organization.objects.filter(user=account).values_list("name", flat=True).first()
    )
    return name or account.email


def is_member(*, account: User, email: str) -> bool:
    """Si ``email`` ya colabora (activo o no) en la empresa de ``account``."""
    return Membership.objects.filter(account=account, user__email=email).exists()


def pending_invitation(*, account: User, email: str) -> Invitation | None:
    """La invitación pendiente de ``email`` en esa empresa, vencida o no."""
    return Invitation.objects.filter(
        account=account, email=email, status=Invitation.Status.PENDING
    ).first()
