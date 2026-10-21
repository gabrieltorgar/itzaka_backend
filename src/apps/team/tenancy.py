"""La empresa en la que trabaja quien hace la petición (iteracion-14, US-137).

Los datos de trabajo cuelgan de la cuenta del administrador (``owner``). Quien
pide trabaja en su empresa propia o en una donde colabora; la aplicación lo
dice con la cabecera ``X-Empresa`` (el id de esa cuenta). Sin cabecera se usa
la propia o, si no tiene, la primera donde colabora activo. Una empresa donde
no colabora, o donde lo desactivaron, no existe para él: 403.
"""

import uuid
from dataclasses import dataclass

from django.core.exceptions import ObjectDoesNotExist
from rest_framework.exceptions import PermissionDenied

from apps.accounts.models import User
from apps.team.models import Membership

#: La cabecera con la que la aplicación elige la empresa.
COMPANY_HEADER = "HTTP_X_EMPRESA"

ADMIN = "admin"
COLLABORATOR = "collaborator"


class CompanyAccessDenied(PermissionDenied):
    """Sin acceso a la empresa pedida; ``code`` deja a la aplicación reaccionar."""

    def __init__(self, detail: str) -> None:
        super().__init__({"detail": detail, "code": "company_access"})


NO_ACCESS = "No tienes acceso a esa empresa."
DEACTIVATED = (
    "Tu acceso a esta empresa está desactivado. Pide al administrador que lo active."
)
NO_COMPANY = (
    "No tienes una empresa activa. Pide a quien te invitó que te active o te "
    "invite de nuevo."
)


@dataclass(frozen=True)
class Company:
    """Una empresa en la que trabaja la persona, y con qué papel."""

    account: User
    name: str
    role: str


def _name(account: User) -> str:
    try:
        return account.organization.name or account.email
    except ObjectDoesNotExist:
        return account.email


def companies_of(user: User) -> list[Company]:
    """Las empresas activas de ``user``: la propia primero, luego donde colabora."""
    companies = []
    if user.has_own_workspace:
        companies.append(Company(account=user, name=_name(user), role=ADMIN))
    memberships = (
        Membership.objects.filter(user=user, is_active=True, account__is_active=True)
        .select_related("account", "account__organization")
        .order_by("created_at")
    )
    companies.extend(
        Company(account=m.account, name=_name(m.account), role=COLLABORATOR)
        for m in memberships
    )
    return companies


def _chosen(user: User, raw: str) -> User:
    try:
        account_id = uuid.UUID(raw)
    except ValueError:
        raise CompanyAccessDenied(NO_ACCESS) from None
    if account_id == user.pk:
        if user.has_own_workspace:
            return user
        raise CompanyAccessDenied(NO_ACCESS)
    membership = (
        Membership.objects.select_related("account")
        .filter(user=user, account_id=account_id, account__is_active=True)
        .first()
    )
    if membership is None:
        raise CompanyAccessDenied(NO_ACCESS)
    if not membership.is_active:
        raise CompanyAccessDenied(DEACTIVATED)
    return membership.account


def _default(user: User) -> User:
    if user.has_own_workspace:
        return user
    membership = (
        Membership.objects.select_related("account")
        .filter(user=user, is_active=True, account__is_active=True)
        .order_by("created_at")
        .first()
    )
    if membership is None:
        raise CompanyAccessDenied(NO_COMPANY)
    return membership.account


def account_of(request) -> User:
    """La cuenta dueña de los datos con los que trabaja esta petición.

    Raises:
        CompanyAccessDenied: la empresa pedida no es suya, lo desactivaron o no
            tiene ninguna activa.
    """
    cached = getattr(request, "_company_account", None)
    if cached is not None:
        return cached
    user = request.user
    raw = (request.META.get(COMPANY_HEADER) or "").strip()
    account = _chosen(user, raw) if raw else _default(user)
    request._company_account = account
    return account


def is_company_admin(request) -> bool:
    """Si quien pide es el administrador de la empresa en la que trabaja."""
    return account_of(request).pk == request.user.pk
