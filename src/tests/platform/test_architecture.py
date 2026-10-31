"""Capas e higiene (iteracion-13 #4: MAN-01 y ARQ-B01; iteracion-14 #3).

Las vistas orquestan: las consultas viven en selectors.py y las reglas en
services.py. Y las dependencias tienen una sola fuente, pyproject.toml + uv.lock
(iteracion-25 #8): Vercel instala de uv.lock y security_audit.py lo audita.
"""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2]
REPO = SRC.parent


def test_views_hold_no_orm_queries():
    offenders = [
        f"{path.relative_to(SRC)}:{n}"
        for path in sorted((SRC / "apps").glob("*/views.py"))
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if ".objects." in line
    ]
    assert not offenders, "las consultas van en selectors.py:\n" + "\n".join(offenders)


def test_data_belongs_to_the_company_not_to_whoever_asks():
    """Iteracion-14 (US-137): un colaborador trabaja con los datos de la empresa.

    Los datos se acotan con ``account_of(request)``; ``owner=request.user``
    dejaría a un colaborador viendo una empresa vacía —la suya— y guardando
    donde nadie más lo ve.
    """
    offenders = [
        f"{path.relative_to(SRC)}:{n}"
        for path in sorted((SRC / "apps").glob("*/views.py"))
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if "owner=self.request.user" in line or "owner=request.user" in line
    ]
    assert not offenders, "usa account_of(request):\n" + "\n".join(offenders)


def test_dependency_manifest_is_uv_only():
    """ARQ-B01: sin requirements*.txt, Pipfile ni poetry.lock junto a uv."""
    manifest = re.compile(r"requirements[^/]*\.txt|Pipfile(\.lock)?|poetry\.lock")
    stray = [
        str(path.relative_to(REPO))
        for path in [*REPO.iterdir(), *SRC.rglob("*")]
        if manifest.fullmatch(path.name)
    ]
    assert not stray, (
        "pyproject.toml + uv.lock son la única fuente (Vercel instala de uv.lock "
        f"y pip-audit lo audita): borra {stray}"
    )
    assert (REPO / "pyproject.toml").is_file()
    assert (REPO / "uv.lock").is_file()
