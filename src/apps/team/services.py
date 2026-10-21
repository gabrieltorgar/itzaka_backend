"""Reglas de colaboradores: invitar, aceptar, activar y quitar."""

import hashlib
import logging
import secrets
from dataclasses import dataclass, field
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.services import normalize_email
from apps.team.emails import send_invitation_email
from apps.team.models import Invitation
from apps.team.selectors import is_member, pending_invitation
from common.mail import mask_email

logger = logging.getLogger("apps")

#: Cuánto vale un enlace de invitación.
INVITATION_DAYS = 7


def hash_token(token: str) -> str:
    """La huella del enlace: lo que se guarda y con lo que se busca."""
    return hashlib.sha256(token.encode()).hexdigest()


def _new_link() -> tuple[str, str]:
    """Un enlace nuevo: el secreto que viaja y la huella que se queda."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


@dataclass
class Sent:
    invitation: Invitation
    email_sent: bool


@dataclass
class InviteResult:
    invited: list[Sent] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)


def _send(invitation: Invitation, token: str) -> Sent:
    sent = send_invitation_email(
        account=invitation.account,
        email=invitation.email,
        token=token,
        days=INVITATION_DAYS,
    )
    logger.info(
        "Invitation sent",
        extra={"to": mask_email(invitation.email), "delivered": sent},
    )
    return Sent(invitation=invitation, email_sent=sent)


def _refresh_link(invitation: Invitation) -> str:
    """Enlace y vigencia nuevos; el anterior deja de servir."""
    token, invitation.token_hash = _new_link()
    invitation.sent_at = timezone.now()
    invitation.expires_at = invitation.sent_at + timedelta(days=INVITATION_DAYS)
    invitation.save(update_fields=["token_hash", "sent_at", "expires_at"])
    return token


def invite_collaborators(*, account: User, emails: list[str]) -> InviteResult:
    """Invita a cada correo a la empresa de ``account``.

    No se manda una segunda invitación a quien ya colabora o ya tiene una
    vigente; una vencida se renueva. Si el correo no sale, la invitación queda
    y se puede reenviar.
    """
    result = InviteResult()
    seen: set[str] = set()
    for raw in emails:
        email = normalize_email(raw)
        if email in seen:
            continue
        seen.add(email)

        if email == normalize_email(account.email):
            result.skipped.append(
                {
                    "email": email,
                    "reason": "Es tu propio correo: ya eres el administrador.",
                }
            )
            continue
        if is_member(account=account, email=email):
            result.skipped.append({"email": email, "reason": "Ya es colaborador."})
            continue

        invitation = pending_invitation(account=account, email=email)
        if invitation is not None and not invitation.is_expired:
            result.skipped.append(
                {
                    "email": email,
                    "reason": "Ya tiene una invitación pendiente; puedes reenviarla.",
                }
            )
            continue

        with transaction.atomic():
            if invitation is None:
                token, token_hash = _new_link()
                now = timezone.now()
                invitation = Invitation.objects.create(
                    account=account,
                    email=email,
                    token_hash=token_hash,
                    sent_at=now,
                    expires_at=now + timedelta(days=INVITATION_DAYS),
                )
            else:
                token = _refresh_link(invitation)
        result.invited.append(_send(invitation, token))
    return result
