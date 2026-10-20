#!/usr/bin/env python3
"""Dependency vulnerability audit for the `security` CI check (criterion SRV-03).

Runs pip-audit over the runtime dependencies (uv export, no dev groups) when
pyproject.toml exists, and `pnpm audit --prod` when pnpm-lock.yaml exists. Fails on
findings at or above --min-severity that are not covered by a non-expired entry of
.security-exceptions:

    # id                    revisar-antes-de  motivo
    GHSA-xxxx-xxxx-xxxx     2026-12-31        Solo afecta al CLI, no se usa en runtime

pip-audit reports no severity, so every Python finding counts as at least `high`
unless excepted.
Exit codes: 0 clean · 1 findings or expired exceptions · 2 tool error.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import tempfile
from pathlib import Path

LEVELS = {"low": 1, "moderate": 2, "medium": 2, "high": 3, "critical": 4}


def load_exceptions(path: Path, today: dt.date) -> tuple[set[str], list[str]]:
    ok, expired = set(), []
    if not path.exists():
        return ok, expired
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            expired.append(
                f".security-exceptions:{n}: formato inválido (id fecha motivo)"
            )
            continue
        vid, date, _reason = parts
        try:
            until = dt.date.fromisoformat(date)
        except ValueError:
            expired.append(f".security-exceptions:{n}: fecha inválida '{date}'")
            continue
        if until < today:
            expired.append(
                f".security-exceptions:{n}: {vid} venció el {date} — revisar"
            )
        else:
            ok.add(vid.upper())
    return ok, expired


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)  # noqa: S603 -- comandos fijos (uv, pnpm)


def python_findings() -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        req = Path(tmp) / "requirements.txt"
        exp = run(
            [
                "uv",
                "export",
                "--no-dev",
                "--no-hashes",
                "--format",
                "requirements-txt",
                "-o",
                str(req),
            ]
        )
        if exp.returncode:
            raise RuntimeError(f"uv export falló: {exp.stderr.strip()}")
        res = run(
            [
                "uvx",
                "pip-audit",
                "-r",
                str(req),
                "--format",
                "json",
                "--progress-spinner",
                "off",
            ]
        )
        if res.returncode not in (0, 1):
            raise RuntimeError(f"pip-audit falló: {res.stderr.strip()}")
        return parse_pip_audit(res.stdout)


def parse_pip_audit(text: str) -> list[dict]:
    data = json.loads(text or "{}")
    deps = data.get("dependencies", data if isinstance(data, list) else [])
    out = []
    for dep in deps:
        for v in dep.get("vulns", []):
            ids = [v.get("id", "")] + list(v.get("aliases", []))
            out.append(
                {
                    "ids": [i.upper() for i in ids if i],
                    "package": f"{dep.get('name')} {dep.get('version')}",
                    "severity": "high",
                    "fix": ", ".join(v.get("fix_versions", []))
                    or "sin versión corregida",
                }
            )
    return out


def node_findings() -> list[dict]:
    res = run(["pnpm", "audit", "--prod", "--json"])
    if res.returncode not in (0, 1) and not res.stdout.strip():
        raise RuntimeError(f"pnpm audit falló: {res.stderr.strip()}")
    return parse_pnpm_audit(res.stdout)


def parse_pnpm_audit(text: str) -> list[dict]:
    data = json.loads(text or "{}")
    out = []
    for adv in (data.get("advisories") or {}).values():
        ids = [str(adv.get("github_advisory_id", ""))] + [
            str(c) for c in adv.get("cves", [])
        ]
        out.append(
            {
                "ids": [i.upper() for i in ids if i and i != "None"],
                "package": adv.get("module_name", "?"),
                "severity": str(adv.get("severity", "high")).lower(),
                "fix": adv.get("patched_versions") or "sin versión corregida",
            }
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--min-severity", default="high", choices=sorted(LEVELS))
    ap.add_argument("--repo", default=".")
    a = ap.parse_args()
    root = Path(a.repo)
    allowed, problems = load_exceptions(root / ".security-exceptions", dt.date.today())
    findings: list[dict] = []
    try:
        if (root / "pyproject.toml").exists():
            findings += python_findings()
        if (root / "pnpm-lock.yaml").exists():
            findings += node_findings()
    except (RuntimeError, json.JSONDecodeError, FileNotFoundError) as exc:
        print(f"security_audit: error de herramienta: {exc}", file=sys.stderr)
        return 2
    threshold = LEVELS[a.min_severity]
    blocking = [
        f
        for f in findings
        if LEVELS.get(f["severity"], 3) >= threshold and not (set(f["ids"]) & allowed)
    ]
    for f in blocking:
        ids = ", ".join(f["ids"][:3])
        problems.append(
            f"{f['severity'].upper():8} {f['package']} · {ids} · "
            f"corrige con: {f['fix']}"
        )
    if problems:
        print("security_audit: FALLA\n  " + "\n  ".join(problems))
        return 1
    print(
        f"security_audit: ok ({len(findings)} hallazgos bajo el umbral "
        "o con excepción vigente)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
