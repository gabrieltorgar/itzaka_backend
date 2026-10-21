"""La sesión vive en cookies HttpOnly (iteracion-12 #1, US-03 / US-69).

Hasta 3.4.0 el access y el refresh viajaban en el cuerpo y la SPA los guardaba en
localStorage, donde cualquier script los lee: un XSS o una extensión se llevaba
la cuenta por 30 días. Ahora los pone el servidor en cookies que JavaScript no
puede leer, el refresh rota y el viejo queda en la lista negra, y salir lo anula.
"""

from datetime import timedelta

import pytest
from django.conf import settings
from rest_framework import status
from rest_framework.test import APIClient

from common.auth_cookies import ACCESS_COOKIE, REFRESH_COOKIE

LOGIN = "/api/auth/login/"
REFRESH = "/api/auth/refresh/"
LOGOUT = "/api/auth/logout/"
ME = "/api/auth/me/"
PASSWORD = "/api/auth/me/password/"
ORGANIZATION = "/api/auth/organization/"


def entrar(
    client: APIClient, email: str = "ana@estudio.mx", password: str = "testpass123"
):
    return client.post(LOGIN, {"email": email, "password": password}, format="json")


@pytest.fixture
def cuenta(user_factory):
    return user_factory(
        email="ana@estudio.mx", password="testpass123", is_email_verified=True
    )


@pytest.mark.django_db
class TestLaSesionVaEnCookies:
    def test_login_sets_httponly_cookies_and_returns_no_tokens(
        self, api_client, cuenta
    ) -> None:
        """Flujo principal - La sesión no queda a la vista de otros programas."""
        response = entrar(api_client)

        assert response.status_code == status.HTTP_200_OK
        assert "access" not in response.data
        assert "refresh" not in response.data
        assert response.data["user"]["email"] == "ana@estudio.mx"
        for name in (ACCESS_COOKIE, REFRESH_COOKIE):
            cookie = response.cookies[name]
            assert cookie.value
            assert cookie["httponly"]
            assert cookie["samesite"] == "Lax"
        # El refresh sólo viaja a las rutas de la sesión.
        assert response.cookies[REFRESH_COOKIE]["path"] == "/api/auth/"
        # La SPA necesita leer el token CSRF para mandarlo en cada escritura.
        assert response.cookies["csrftoken"].value
        assert not response.cookies["csrftoken"]["httponly"]

    def test_the_access_cookie_opens_the_account(self, api_client, cuenta) -> None:
        """Flujo principal - Con la cookie, la cuenta responde sin cabecera."""
        entrar(api_client)

        response = api_client.get(ME)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == "ana@estudio.mx"

    def test_a_write_without_the_csrf_token_is_refused(self, cuenta) -> None:
        """Caso de borde - Otra página no puede escribir con la cookie de la sesión."""
        client = APIClient(enforce_csrf_checks=True)
        login = entrar(client)
        token = login.cookies["csrftoken"].value

        sin_token = client.patch(ORGANIZATION, {}, format="json")
        con_token = client.patch(
            ORGANIZATION, {}, format="json", HTTP_X_CSRFTOKEN=token
        )

        assert sin_token.status_code == status.HTTP_403_FORBIDDEN
        assert con_token.status_code == status.HTTP_200_OK

    def test_a_stale_access_cookie_does_not_block_logging_in(
        self, api_client, cuenta
    ) -> None:
        """Caso de borde - Una cookie vencida o falsa no impide volver a entrar."""
        api_client.cookies[ACCESS_COOKIE] = "basura"

        assert entrar(api_client).status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestLaSesionSeRenuevaYSeCierra:
    def test_refresh_rotates_and_the_old_refresh_dies(self, api_client, cuenta) -> None:
        """Flujo principal - La sesión se renueva; el refresh usado ya no sirve."""
        entrar(api_client)
        viejo = api_client.cookies[REFRESH_COOKIE].value

        renovada = api_client.post(REFRESH, {}, format="json")

        assert renovada.status_code == status.HTTP_200_OK
        assert "access" not in renovada.data
        nuevo = renovada.cookies[REFRESH_COOKIE].value
        assert nuevo and nuevo != viejo

        otro = APIClient()
        otro.cookies[REFRESH_COOKIE] = viejo
        assert (
            otro.post(REFRESH, {}, format="json").status_code
            == status.HTTP_401_UNAUTHORIZED
        )

    def test_logout_clears_the_cookies_and_revokes_the_refresh(
        self, api_client, cuenta
    ) -> None:
        """Flujo principal - Salir invalida la sesión, aun si alguien la copió."""
        entrar(api_client)
        copiado = api_client.cookies[REFRESH_COOKIE].value

        salida = api_client.post(LOGOUT, {}, format="json")

        assert salida.status_code == status.HTTP_204_NO_CONTENT
        assert salida.cookies[ACCESS_COOKIE].value == ""
        assert salida.cookies[REFRESH_COOKIE].value == ""
        otro = APIClient()
        otro.cookies[REFRESH_COOKIE] = copiado
        assert (
            otro.post(REFRESH, {}, format="json").status_code
            == status.HTTP_401_UNAUTHORIZED
        )

    def test_logout_without_a_session_is_harmless(self, api_client) -> None:
        """Caso de borde - Salir sin sesión no falla."""
        assert (
            api_client.post(LOGOUT, {}, format="json").status_code
            == status.HTTP_204_NO_CONTENT
        )

    def test_refresh_without_a_session_is_401(self, api_client) -> None:
        """Caso de borde - Sin sesión no hay nada que renovar."""
        assert (
            api_client.post(REFRESH, {}, format="json").status_code
            == status.HTTP_401_UNAUTHORIZED
        )

    def test_changing_the_password_closes_the_other_sessions(self, cuenta) -> None:
        """Caso de borde - Cambiar la contraseña deja fuera las otras sesiones."""
        aqui, alla = APIClient(), APIClient()
        entrar(aqui)
        entrar(alla)

        cambio = aqui.post(
            PASSWORD,
            {"current_password": "testpass123", "new_password": "OtraClave#2026"},
            format="json",
        )

        assert cambio.status_code == status.HTTP_200_OK
        assert (
            alla.post(REFRESH, {}, format="json").status_code
            == status.HTTP_401_UNAUTHORIZED
        )
        # Quien la cambió sigue dentro, con una sesión nueva.
        assert aqui.post(REFRESH, {}, format="json").status_code == status.HTTP_200_OK


def test_lifetimes_rotation_and_blacklist() -> None:
    """Flujo principal - Media hora de acceso, una semana de sesión, rotación."""
    jwt = settings.SIMPLE_JWT
    assert jwt["ACCESS_TOKEN_LIFETIME"] <= timedelta(minutes=30)
    assert jwt["REFRESH_TOKEN_LIFETIME"] <= timedelta(days=7)
    assert jwt["ROTATE_REFRESH_TOKENS"] is True
    assert jwt["BLACKLIST_AFTER_ROTATION"] is True
    assert "rest_framework_simplejwt.token_blacklist" in settings.INSTALLED_APPS
    assert settings.CSRF_COOKIE_HTTPONLY is False
