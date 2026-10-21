"""Reglas de colaboradores: invitar, aceptar, activar y quitar."""

import hashlib
import logging
import secrets
from dataclasses import dataclass, field
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, ValidationError

from apps.accounts.models import User
from apps.accounts.services import check_password_strength, find_user, normalize_email
from apps.legal.services import record_acceptance
from apps.team.emails import send_invitation_email
from apps.team.models import Invitation, Membership
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


class InvitationGone(APIException):
    """La invitación existió pero ya no sirve: venció o se canceló."""

    status_code = status.HTTP_410_GONE
    default_code = "invitation_gone"


class InvitationUsed(APIException):
    """La invitación ya se aceptó: el enlace sirve una sola vez."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "invitation_used"
    default_detail = "Ya aceptaste esta invitación: inicia sesión con tu correo."


def find_invitation(*, token: str, lock: bool = False) -> Invitation:
    """La invitación de ese enlace.

    Raises:
        NotFound: ningún enlace emitido tiene esa huella.
    """
    queryset = Invitation.objects.select_related("account")
    if lock:
        queryset = queryset.select_for_update()
    invitation = queryset.filter(token_hash=hash_token(token)).first()
    if invitation is None:
        raise NotFound("Esta invitación no existe. Revisa el enlace o pide otra.")
    return invitation


def invitation_state(invitation: Invitation) -> str:
    """Pendiente, vencida, aceptada o cancelada: lo que la pantalla necesita."""
    return "expired" if invitation.is_expired else invitation.status


def _ensure_usable(invitation: Invitation) -> None:
    if invitation.status == Invitation.Status.ACCEPTED:
        raise InvitationUsed()
    if invitation.status == Invitation.Status.CANCELLED:
        raise InvitationGone("La invitación se canceló. Pide otra al administrador.")
    if invitation.is_expired:
        raise InvitationGone(
            "La invitación venció. Pide al administrador que te la reenvíe."
        )


@transaction.atomic
def accept_invitation(
    *,
    token: str,
    password: str,
    terms_version: str = "",
    privacy_version: str = "",
    ip_address: str | None = None,
    user_agent: str = "",
) -> User:
    """Sumar a la empresa a quien recibió el enlace.

    Sin cuenta, la crea ya confirmada —el enlace llegó a ese correo— y sin
    empresa propia, con la constancia de los documentos que aceptó. Con cuenta,
    pide su contraseña. El enlace sirve una sola vez.

    Raises:
        NotFound, InvitationGone, InvitationUsed: el enlace no sirve.
        ValidationError: contraseña débil o equivocada, o faltan los documentos.
    """
    invitation = find_invitation(token=token, lock=True)
    _ensure_usable(invitation)

    user = find_user(email=invitation.email)
    if user is None:
        if not terms_version:
            raise ValidationError(
                {"terms_version": ["Acepta los términos y condiciones para continuar."]}
            )
        if not privacy_version:
            raise ValidationError(
                {
                    "privacy_version": [
                        "Acepta la política de privacidad para continuar."
                    ]
                }
            )
        check_password_strength(password=password, user=User(email=invitation.email))
        user = User.objects.create_user(
            email=invitation.email,
            password=password,
            is_email_verified=True,
            has_own_workspace=False,
        )
        record_acceptance(
            user=user,
            terms_version=terms_version,
            privacy_version=privacy_version,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    else:
        if not user.check_password(password):
            raise ValidationError({"password": ["La contraseña no es correcta."]})
        if not user.is_email_verified:
            user.is_email_verified = True
            user.save(update_fields=["is_email_verified", "updated_at"])

    Membership.objects.get_or_create(account=invitation.account, user=user)
    invitation.status = Invitation.Status.ACCEPTED
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=["status", "accepted_at"])
    logger.info(
        "Invitation accepted",
        extra={"user_id": str(user.pk), "account_id": str(invitation.account_id)},
    )
    return user
