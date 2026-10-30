"""Health endpoint tests (scaffold baseline + versión visible, iteracion-20)."""

import tomllib
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import status

PYPROJECT = Path(settings.BASE_DIR).parent / "pyproject.toml"


def _pyproject_version() -> str:
    with PYPROJECT.open("rb") as archivo:
        return tomllib.load(archivo)["project"]["version"]


@pytest.mark.django_db
class TestHealth:
    """The health endpoint is public and reports service status."""

    def test_health_returns_200_ok(self, api_client) -> None:
        response = api_client.get("/api/health/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "ok"

    def test_health_says_the_deployed_version(self, api_client) -> None:
        """Versión visible - La sonda dice la versión de pyproject.toml y nada más."""
        response = api_client.get("/api/health/")

        assert response.data == {"status": "ok", "version": _pyproject_version()}

    def test_a_dead_session_cookie_does_not_break_the_probe(self, api_client) -> None:
        """Caso de borde - Una cookie vencida no vuelve 401 la sonda."""
        api_client.cookies["itzaka_access"] = "no-es-un-token"

        assert api_client.get("/api/health/").status_code == status.HTTP_200_OK


class TestVersionVisible:
    def test_the_version_comes_from_pyproject(self) -> None:
        """Versión visible - Una sola fuente: [project].version de pyproject.toml."""
        assert settings.APP_VERSION == _pyproject_version()

    def test_the_admin_header_shows_it(self, rf) -> None:
        """Versión visible - El admin la muestra bajo el nombre."""
        subheader = settings.UNFOLD["SITE_SUBHEADER"](rf.get("/admin/"))

        assert subheader == f"v{_pyproject_version()}"


@pytest.mark.django_db
class TestVersionEnElAdmin:
    def test_the_login_page_shows_it(self, client) -> None:
        """Versión visible - El acceso del admin también la muestra."""
        response = client.get("/admin/login/")

        assert f"v{_pyproject_version()}" in response.content.decode()

    def test_the_sidebar_shows_it(self, client) -> None:
        """Versión visible - La barra lateral del admin la muestra."""
        admin = get_user_model().objects.create_superuser(
            email="admin@itzaka.test", password="Cantera-Admin-81"
        )
        client.force_login(admin)

        response = client.get("/admin/")

        assert f"v{_pyproject_version()}" in response.content.decode()
