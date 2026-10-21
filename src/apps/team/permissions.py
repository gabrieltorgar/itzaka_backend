"""Lo que sólo decide el administrador de la empresa (iteracion-14, US-140)."""

from rest_framework.permissions import BasePermission

from apps.team.tenancy import is_company_admin


class IsCompanyAdmin(BasePermission):
    """Quien pide administra la empresa en la que trabaja.

    Un colaborador hace todo lo demás; esto —la organización y el equipo— lo
    decide quien creó la cuenta.
    """

    message = "Sólo el administrador de la empresa puede hacer esto."

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated) and (
            is_company_admin(request)
        )
