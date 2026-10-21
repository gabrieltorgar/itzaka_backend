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


def member_row(membership: Membership) -> dict:
    """Un colaborador como fila de la tabla del administrador."""
    return {
        "id": membership.id,
        "kind": "member",
        "email": membership.user.email,
        "status": "active" if membership.is_active else "inactive",
        "since": membership.created_at,
        "expires_at": None,
    }


def invitation_row(invitation: Invitation) -> dict:
    """Una invitación que espera respuesta, como fila de la misma tabla."""
    return {
        "id": invitation.id,
        "kind": "invitation",
        "email": invitation.email,
        "status": "expired" if invitation.is_expired else "pending",
        "since": invitation.sent_at,
        "expires_at": invitation.expires_at,
    }


def team_of(*, account: User, search: str = "", status: str = "") -> list[dict]:
    """Quién colabora en la empresa y a quién se espera (US-138).

    Primero los colaboradores, en el orden en que llegaron; después las
    invitaciones pendientes o vencidas, la más reciente primero. Las aceptadas
    ya son colaboradores y las canceladas no esperan a nadie.
    """
    members = (
        Membership.objects.filter(account=account)
        .select_related("user")
        .order_by("created_at")
    )
    invitations = Invitation.objects.filter(
        account=account, status=Invitation.Status.PENDING
    ).order_by("-sent_at")
    if search:
        members = members.filter(user__email__icontains=search)
        invitations = invitations.filter(email__icontains=search)
    rows = [member_row(m) for m in members] + [invitation_row(i) for i in invitations]
    return [row for row in rows if not status or row["status"] == status]


def get_member(*, account: User, member_id) -> Membership | None:
    """El colaborador de esa empresa con ese id, o nada si es de otra."""
    return (
        Membership.objects.select_related("user")
        .filter(account=account, pk=member_id)
        .first()
    )
