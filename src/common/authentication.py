"""Autenticación JWT desde la cookie de la sesión (iteracion-12 #1)."""

from rest_framework import exceptions
from rest_framework.authentication import CSRFCheck
from rest_framework.request import Request
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from common.auth_cookies import access_from


def _enforce_csrf(request: Request) -> None:
    """Una escritura con la cookie lleva el token CSRF, como la sesión de Django."""
    # CSRFCheck es un middleware: guarda la vista siguiente y nunca la llama aquí.
    check = CSRFCheck(lambda _request: None)
    check.process_request(request)
    reason = check.process_view(request, None, (), {})
    if reason:
        raise exceptions.PermissionDenied(f"CSRF Failed: {reason}")


class CookieJWTAuthentication(JWTAuthentication):
    """El access de la cookie HttpOnly; la cabecera Authorization sigue sirviendo.

    Una cookie vencida o falsa no rompe una ruta pública (entrar, registrarse):
    se trata como si no hubiera sesión, y una ruta privada responde 401 para que
    la SPA renueve.
    """

    def authenticate(self, request: Request):
        if self.get_header(request) is not None:
            return super().authenticate(request)

        raw = access_from(request)
        if not raw:
            return None
        try:
            validated = self.get_validated_token(raw)
        except (InvalidToken, TokenError):
            return None
        user = self.get_user(validated)
        _enforce_csrf(request)
        return user, validated
