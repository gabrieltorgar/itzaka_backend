"""Lo que se queda fuera de la función de Vercel (iteracion-15 #1, US-121 · US-122).

También US-123 (aceptar los documentos al entrar).

`excludeFiles` de vercel.json adelgaza el paquete quitando pruebas, reportes y
documentación. Un patrón de más se llevaba también los términos y la política
de privacidad (`**/*.md`): en producción el registro no podía cargar los
documentos vigentes y `/api/auth/me/` respondía 500.
"""

import json
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2]
REPO = SRC.parent


def _patterns() -> list[str]:
    config = json.loads((REPO / "vercel.json").read_text(encoding="utf-8"))
    raw = config["functions"]["wsgi.py"]["excludeFiles"]
    return raw.strip("{}").split(",") if raw.startswith("{") else [raw]


def _regex(glob: str) -> re.Pattern[str]:
    """Un glob con `**` como lo entiende Vercel, relativo a la raíz del repo."""
    out, i = "", 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif glob.startswith("**", i):
            out, i = out + ".*", i + 2
        elif glob[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif glob[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(glob[i]), i + 1
    return re.compile(out + r"\Z")


def excluded(path: str) -> bool:
    return any(_regex(p).match(path) for p in _patterns())


def test_the_legal_documents_ship_with_the_function() -> None:
    documentos = sorted((SRC / "apps" / "legal" / "documents").glob("*.md"))

    assert documentos, "no hay documentos legales que revisar"
    for documento in documentos:
        assert not excluded(str(documento.relative_to(REPO))), documento.name


def test_tests_and_repo_docs_still_stay_out() -> None:
    for ruta in [
        "src/apps/team/tests/test_tenancy.py",
        "src/conftest.py",
        "README.md",
        "CHANGELOG.md",
        "docs/despliegue.md",
        "reports/junit.xml",
    ]:
        assert excluded(ruta), ruta
