"""Capas e higiene (iteracion-13 #4: MAN-01 y ARQ-B01). No ligado a una US.

Las vistas orquestan: las consultas viven en selectors.py y las reglas en
services.py. Y requirements.txt —que Vercel usa para instalar la función— no
puede quedarse atrás de uv.lock.
"""

import subprocess
from pathlib import Path

SRC = Path(__file__).resolve().parents[2]
REPO = SRC.parent


def test_views_hold_no_orm_queries():
    offenders = [
        f"{path.relative_to(SRC)}:{n}"
        for path in sorted((SRC / "apps").glob("*/views.py"))
        for n, line in enumerate(path.read_text().splitlines(), 1)
        if ".objects." in line
    ]
    assert not offenders, "las consultas van en selectors.py:\n" + "\n".join(
        offenders
    )


def test_requirements_txt_is_the_lockfile_exported():
    exported = subprocess.run(
        [  # noqa: S607 -- uv del entorno, sin shell
            "uv",
            "export",
            "--frozen",
            "--no-dev",
            "--no-hashes",
            "--no-emit-project",
            "--format",
            "requirements-txt",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    def body(text: str) -> list[str]:
        return [line for line in text.splitlines() if not line.startswith("#")]

    committed = (REPO / "requirements.txt").read_text()
    assert body(committed) == body(exported), (
        "requirements.txt no coincide con uv.lock: corre "
        "`uv export --no-dev --no-hashes --no-emit-project "
        "--format requirements-txt -o requirements.txt`"
    )
