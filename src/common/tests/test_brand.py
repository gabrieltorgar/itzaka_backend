"""La marca es Itzaka (iteracion-20 · US-127): el nombre.

El nombre, la firma del grupo, el admin y los identificadores con el nombre
anterior. Las llaves de la sesión cambian de nombre sin cerrar ninguna: la
cookie anterior se sigue leyendo hasta que se renueva.
"""

import pytest
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

import core.settings as core_settings
from common import auth_cookies
from common.brand import BRAND_NAME, GROUP_SIGNATURE
from common.branding import OPTIMIZED_BY
from common.emails import SIGNATURE
from core.settings_unfold import UNFOLD

ME_URL = "/api/auth/me/"
REFRESH_URL = "/api/auth/refresh/"
LOGOUT_URL = "/api/auth/logout/"


class TestElNombre:
    def test_the_product_is_called_itzaka(self) -> None:
        """US-127 - En el texto el nombre es «Itzaka»."""
        assert BRAND_NAME == "Itzaka"

    def test_the_group_signs(self) -> None:
        """US-127 - La firma del grupo, como la escribe el manual."""
        assert GROUP_SIGNATURE == "una solución de Grupo Torres Muciño"
        assert SIGNATURE == (
            "Este mensaje se generó desde Itzaka, una solución de Grupo Torres Muciño."
        )
        assert OPTIMIZED_BY == "optimizado por Itzaka"

    def test_the_admin_says_itzaka(self) -> None:
        """US-127 - El admin se llama Itzaka."""
        assert str(UNFOLD["SITE_TITLE"]) == "Itzaka Admin"
        assert str(UNFOLD["SITE_HEADER"]) == "Itzaka"

    def test_the_cache_table_carries_the_new_name(self) -> None:
        """US-127 - La tabla de caché se llama como el producto."""
        assert core_settings.CACHES["default"]["LOCATION"] == "itzaka_cache"


@pytest.mark.django_db
class TestLasLlavesDeLaSesion:
    def test_the_session_cookies_carry_the_new_name(self) -> None:
        """US-127 - Las cookies de la sesión se llaman como el producto."""
        assert auth_cookies.ACCESS_COOKIE == "itzaka_access"
        assert auth_cookies.REFRESH_COOKIE == "itzaka_refresh"

    def test_an_open_session_keeps_working(self, user_factory) -> None:
        """Caso de borde - Nadie pierde su sesión: se lee la cookie de antes."""
        cuenta = user_factory(is_email_verified=True)
        cliente = APIClient()
        cliente.cookies["cuotreka_access"] = str(
            RefreshToken.for_user(cuenta).access_token
        )

        response = cliente.get(ME_URL)

        assert response.status_code == status.HTTP_200_OK

    def test_the_old_refresh_renews_into_the_new_cookies(self, user_factory) -> None:
        """Caso de borde - Al renovar con la cookie de antes, pasa a las nuevas."""
        cuenta = user_factory(is_email_verified=True)
        cliente = APIClient()
        cliente.cookies["cuotreka_refresh"] = str(RefreshToken.for_user(cuenta))

        response = cliente.post(REFRESH_URL)

        assert response.status_code == status.HTTP_200_OK
        assert response.cookies["itzaka_access"].value
        assert response.cookies["itzaka_refresh"].value
        assert response.cookies["cuotreka_access"].value == ""
        assert response.cookies["cuotreka_refresh"].value == ""

    def test_logout_also_clears_the_old_cookies(self, user_factory) -> None:
        """Caso de borde - Salir borra las cookies nuevas y las de antes."""
        cuenta = user_factory(is_email_verified=True)
        cliente = APIClient()
        cliente.cookies["cuotreka_refresh"] = str(RefreshToken.for_user(cuenta))

        response = cliente.post(LOGOUT_URL)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        for nombre in (
            "itzaka_access",
            "itzaka_refresh",
            "cuotreka_access",
            "cuotreka_refresh",
        ):
            assert response.cookies[nombre].value == ""

    def test_the_old_refresh_is_revoked_on_logout(self, user_factory) -> None:
        """Caso de borde - El refresh de la cookie de antes queda anulado al salir."""
        cuenta = user_factory(is_email_verified=True)
        refresh = RefreshToken.for_user(cuenta)
        cliente = APIClient()
        cliente.cookies["cuotreka_refresh"] = str(refresh)

        cliente.post(LOGOUT_URL)
        otra = APIClient()
        otra.cookies["cuotreka_refresh"] = str(refresh)

        assert otra.post(REFRESH_URL).status_code == status.HTTP_401_UNAUTHORIZED
