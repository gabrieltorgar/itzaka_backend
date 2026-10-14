"""The deployment entrypoint: what Vercel imports, and with which path.

This suite exists because the API answered 404 to everything in production
while every other test was green. The cause was not code but routing: a
catch-all rewrite in ``vercel.json`` sent every request to ``/api/index``, and
once Vercel started handing the app the REWRITTEN path, Django had no URL for
it. Nothing under ``src/`` could see that, so it is checked here.
"""

import importlib
import io
import json
import re
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _vercel_entrypoint() -> str:
    """The WSGI instance Vercel is told to serve, as ``module:attribute``."""
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["tool"]["vercel"]["entrypoint"]


def _load(entrypoint: str):
    """Imports it the way Vercel does: by module name, from the repo root."""
    module_name, _, attribute = entrypoint.partition(":")
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    return getattr(importlib.import_module(module_name), attribute)


def _get(app, path: str) -> str:
    """The status line of a real WSGI call — the request Vercel would deliver."""
    captured: dict[str, str] = {}

    def start_response(status: str, headers, exc_info=None) -> None:
        captured["status"] = status

    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": path,
        "SERVER_NAME": "testserver",
        "SERVER_PORT": "443",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "wsgi.url_scheme": "https",
        "wsgi.input": io.BytesIO(b""),
        "CONTENT_LENGTH": "0",
        "QUERY_STRING": "",
    }
    list(app(environ, start_response))
    return captured["status"]


@pytest.mark.django_db
def test_entrypoint_serves_a_real_path() -> None:
    """Flujo principal - La instancia que sirve Vercel resuelve la API."""
    app = _load(_vercel_entrypoint())

    assert _get(app, "/api/health/").startswith("200")


def test_entrypoint_is_importable_from_the_repository_root() -> None:
    """Caso de borde - Vercel importa por nombre de módulo, no por ruta."""
    module_name = _vercel_entrypoint().partition(":")[0]

    assert (REPO_ROOT / f"{module_name.replace('.', '/')}.py").is_file()


def test_no_catch_all_rewrite_reaches_the_app() -> None:
    """Caso de borde - Un rewrite general le cambiaría la ruta a Django.

    Vercel entrega ahora la ruta ya reescrita, de modo que un `/(.*)` hacia una
    función deja a Django resolviendo siempre el mismo camino inexistente: eso
    es lo que hizo que toda la API respondiera 404.
    """
    config = json.loads((REPO_ROOT / "vercel.json").read_text())

    for rewrite in config.get("rewrites", []):
        assert rewrite["source"] not in ("/(.*)", "/(.*)$", "/:path*"), (
            "un rewrite general vuelve a romper el enrutado de la API"
        )


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["/api/tariffs/", "/api/auth/login/", "/admin/login/"])
def test_the_paths_the_app_actually_receives_resolve(path: str) -> None:
    """Flujo principal - Las rutas que pide el cliente existen para Django."""
    app = _load(_vercel_entrypoint())

    assert not _get(app, path).startswith("404")


# --- TEC Configuración de despliegue en Vercel (iteracion-9) ---------------
#
# Cada despliegue guarda su propia copia de la función, de modo que lo que viaja
# en ella y qué ramas despliegan es lo que llena el almacenamiento de Vercel.

# Lo que el runtime necesita y ninguna exclusión puede tocar.
_RUNTIME_FILES = (
    "wsgi.py",
    "pyproject.toml",
    "src/manage.py",
    "src/core/settings.py",
    "src/core/wsgi.py",
    "src/api/urls.py",
    "src/apps/planner/photo_cleanup.py",
    "src/apps/planner/migrations/0001_initial.py",
)


def _vercel_config() -> dict:
    return json.loads((REPO_ROOT / "vercel.json").read_text())


def _expand_braces(pattern: str) -> list[str]:
    """``{a,b}`` → ``[a, b]``: la única llave que usa ``excludeFiles``."""
    if pattern.startswith("{") and pattern.endswith("}"):
        return pattern[1:-1].split(",")
    return [pattern]


def _glob_regex(pattern: str) -> re.Pattern[str]:
    """Un glob como lo lee Vercel (minimatch): ``**`` cruza carpetas, ``*`` no."""
    out = ""
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.compile(f"^{out}$")


def _excluded(path: str, patterns: list[str]) -> bool:
    return any(_glob_regex(pattern).match(path) for pattern in patterns)


def _exclude_patterns() -> list[str]:
    functions = _vercel_config()["functions"]
    (settings,) = functions.values()
    return _expand_braces(settings["excludeFiles"])


def test_only_main_and_develop_deploy() -> None:
    """Flujo principal - Sólo producción y develop crean un despliegue.

    Las ramas de trabajo ya tienen su contrato en el quality gate de CI; un
    preview por cada una sólo llena el almacenamiento de Vercel.
    """
    enabled = _vercel_config()["git"]["deploymentEnabled"]

    assert enabled == {"**": False, "main": True, "develop": True}


def test_the_function_settings_apply_to_the_entrypoint_vercel_serves() -> None:
    """Caso de borde - Con otra clave, ``excludeFiles`` se ignora en silencio."""
    module_file = _vercel_entrypoint().partition(":")[0].replace(".", "/") + ".py"

    assert list(_vercel_config()["functions"]) == [module_file]


def test_tests_docs_and_caches_stay_out_of_the_function() -> None:
    """Flujo principal - Pruebas, documentación y cachés no viajan en el bundle."""
    patterns = _exclude_patterns()
    out = [
        "src/api/tests/test_health.py",
        "src/apps/planner/tests/test_photo_cleanup.py",
        "src/conftest.py",
        "CHANGELOG.md",
        "README.md",
        "scripts/test_gate.py",
        ".github/workflows/quality-gate.yml",
        "reports/junit.xml",
        "coverage.xml",
        ".pytest_cache/v/cache/lastfailed",
        ".ruff_cache/0.6.0/123",
    ]

    assert [path for path in out if not _excluded(path, patterns)] == []


def test_nothing_the_runtime_needs_is_excluded() -> None:
    """Caso de borde - Una exclusión de más sólo se nota al responder."""
    patterns = _exclude_patterns()
    source = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in (REPO_ROOT / "src").rglob("*.py")
        if "tests" not in path.parts and "__pycache__" not in path.parts
        and path.name != "conftest.py"
    ]

    needed = (*_RUNTIME_FILES, *source)

    assert [path for path in needed if _excluded(path, patterns)] == []


def test_the_build_installs_only_the_runtime_and_migrates() -> None:
    """Flujo principal - Sin dependencias de desarrollo ni collectstatic doble.

    Vercel instala desde ``uv.lock`` y corre ``collectstatic`` por su cuenta; aquí
    WhiteNoise sirve los estáticos con sus finders, así que el build sólo fija
    el entorno de ejecución y migra.
    """
    build = _vercel_config()["buildCommand"]

    assert build.startswith("uv sync --frozen --no-dev && ")
    assert "uv run --no-sync python src/manage.py migrate --noinput" in build
    assert "collectstatic" not in build
