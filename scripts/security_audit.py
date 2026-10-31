#!/usr/bin/env python3
"""Dependency vulnerability audit for the `security` CI check (criterion SRV-03). Fails closed.

Audits every ecosystem the repo has, from its lockfile, with every command run in --repo:
  python  pyproject.toml + uv.lock: `uv export --locked --no-dev` (the runtime set; a uv.lock that no
          longer matches pyproject.toml fails) and pip-audit at an exact version (PIP_AUDIT) over it.
  node    pnpm-lock.yaml: `pnpm audit --json`, production and dev dependencies (the build and dev-server
          toolchain counts). Requires pnpm >= 11: npm retired the legacy audit endpoints that pnpm <= 10
          calls (HTTP 410 since 2026-07-15); pnpm 11 uses the bulk advisory endpoint, which returns GHSA
          ids and no CVE. Never `--ignore-registry-errors`.
  dart    pubspec.lock: osv-scanner (OSV_IMAGE, tag + digest) through docker. A CI-only tool, not an app
          dependency: Dart has no first-party audit and neither pip-audit nor pnpm audit reads pub
          lockfiles. (osv-scanner also reads pnpm-lock.yaml and uv.lock: the fallback if an audit
          endpoint is retired again.)
Prints `auditado <ecosistema>: N paquetes` per ecosystem and fails on findings at or above --min-severity
that no valid line of .security-exceptions covers:

    # id                    revisar-antes-de  motivo
    GHSA-xxxx-xxxx-xxxx     2026-12-31        Solo afecta al servidor de desarrollo de Vite, nunca expuesto

Ids are GHSA / PYSEC (pnpm >= 11 returns no CVE). The date is at most MAX_EXCEPTION_DAYS (90) ahead; an
expired, farther or malformed line fails the check. pip-audit reports no severity and a pub finding
without a CVSS score has none, so both count as `high` unless excepted.

Exit codes (fail closed: any tool or registry error is 2, never "pasa"):
  0  every detected ecosystem audited and nothing blocking
  1  blocking findings, or an expired / invalid exception
  2  tool or registry error (unexpected exit code, missing tool, empty / non-JSON / error report),
     pnpm < 11, uv.lock out of date, an ecosystem that audited 0 packages, pyproject.toml next to
     requirements*.txt / Pipfile / poetry.lock (two dependency sources), or no recognized lockfile
     (pyproject.toml, pnpm-lock.yaml, pubspec.lock) unless --allow-empty

Pins: PIP_AUDIT and OSV_IMAGE are bumped by hand (Dependabot does not see them) next to the gitleaks image
of security.yml: read the release notes, take a release at least two weeks old, resolve the image digest
(`docker buildx imagetools inspect <imagen>:<tag>`), update security.yml's pull step to the same reference,
and run --self-test.
--self-test runs the parsers on embedded fixtures (no network, no tools) and exits 0 when all behave.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

PIP_AUDIT = "pip-audit==2.10.1"
OSV_IMAGE = ("ghcr.io/google/osv-scanner:v2.6.0"
             "@sha256:afd838850ac1a0fcc15ff4a041dc9ba11123c3f0d2666217a5f0fcf9222b55fa")
MIN_PNPM_MAJOR = 11
MAX_EXCEPTION_DAYS = 90
LEVELS = {"info": 0, "low": 1, "moderate": 2, "medium": 2, "high": 3, "critical": 4}
GHSA_RE = re.compile(r"GHSA(?:-[0-9a-z]{4}){3}", re.I)
SECOND_SOURCES = ("requirements*.txt", "Pipfile", "Pipfile.lock", "poetry.lock")


def load_exceptions(path: Path, today: dt.date) -> tuple[set[str], list[str]]:
    ok, problems = set(), []
    if not path.exists():
        return ok, problems
    limit = today + dt.timedelta(days=MAX_EXCEPTION_DAYS)
    for n, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            problems.append(f".security-exceptions:{n}: formato inválido (id fecha motivo)")
            continue
        vid, date, _reason = parts
        try:
            until = dt.date.fromisoformat(date)
        except ValueError:
            problems.append(f".security-exceptions:{n}: fecha inválida '{date}'")
            continue
        if until < today:
            problems.append(f".security-exceptions:{n}: {vid} venció el {date}: revisar")
        elif until > limit:
            problems.append(f".security-exceptions:{n}: {vid} con fecha {date}: máximo {MAX_EXCEPTION_DAYS} días "
                            f"(hasta {limit})")
        else:
            ok.add(vid.upper())
    return ok, problems


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd)


def tail(text: str, n: int = 12) -> str:
    lines = [line for line in (text or "").strip().splitlines() if line.strip()]
    return "\n    ".join(lines[-n:]) or "(sin salida)"


def load_json(text: str, tool: str):
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        raise RuntimeError(f"{tool} no devolvió JSON: {tail(text, 3)}") from None


# ── python ────────────────────────────────────────────────────────────────────────────────────────

def python_findings(root: Path) -> tuple[list[dict], int]:
    with tempfile.TemporaryDirectory() as tmp:
        req = str(Path(tmp) / "requirements.txt")
        exp = run(["uv", "export", "--locked", "--no-dev", "--no-emit-project", "--no-hashes",
                   "--format", "requirements-txt", "-o", req], root)
        if exp.returncode:
            raise RuntimeError("uv export --locked falló (uv.lock desactualizado: corre uv lock y commitea):\n    "
                               + tail(exp.stderr))
        res = run(["uvx", PIP_AUDIT, "-r", req, "--no-deps", "--disable-pip", "--format", "json",
                   "--progress-spinner", "off"], root)
        if res.returncode not in (0, 1):
            raise RuntimeError(f"pip-audit terminó con código {res.returncode}:\n    {tail(res.stderr)}")
        try:
            return parse_pip_audit(res.stdout)
        except RuntimeError as exc:
            raise RuntimeError(f"{exc}\n    stderr: {tail(res.stderr)}") from None


def parse_pip_audit(text: str) -> tuple[list[dict], int]:
    data = load_json(text, "pip-audit")
    if not isinstance(data, dict) or not isinstance(data.get("dependencies"), list):
        raise RuntimeError("pip-audit no devolvió un reporte (falta la lista 'dependencies')")
    deps = data["dependencies"]
    out = []
    for dep in deps:
        for v in dep.get("vulns") or []:
            ids = [v.get("id", "")] + list(v.get("aliases") or [])
            out.append({"ids": unique(ids), "package": f"{dep.get('name')} {dep.get('version')}",
                        "severity": "high", "fix": ", ".join(v.get("fix_versions") or []) or "sin versión corregida"})
    return out, len(deps)


# ── node ──────────────────────────────────────────────────────────────────────────────────────────

def require_pnpm(version_text: str) -> None:
    m = re.match(r"\s*v?(\d+)\.", version_text or "")
    if not m:
        raise RuntimeError(f"pnpm --version ilegible: {version_text.strip()!r}")
    if int(m.group(1)) < MIN_PNPM_MAJOR:
        raise RuntimeError(f"pnpm >= {MIN_PNPM_MAJOR} requerido (el endpoint legado de auditoría responde 410): "
                           f"hay {version_text.strip()}; fija \"packageManager\": \"pnpm@11.x.y\" o mayor en package.json")


def node_findings(root: Path) -> tuple[list[dict], int]:
    ver = run(["pnpm", "--version"], root)
    if ver.returncode:
        raise RuntimeError(f"pnpm --version falló:\n    {tail(ver.stderr)}")
    require_pnpm(ver.stdout)
    res = run(["pnpm", "audit", "--json"], root)
    if res.returncode not in (0, 1):
        raise RuntimeError(f"pnpm audit terminó con código {res.returncode}:\n    {tail(res.stderr)}")
    try:
        return parse_pnpm_audit(res.stdout)
    except RuntimeError as exc:
        raise RuntimeError(f"{exc}\n    stderr: {tail(res.stderr)}") from None


def parse_pnpm_audit(text: str) -> tuple[list[dict], int]:
    data = load_json(text, "pnpm audit")
    meta = data.get("metadata") if isinstance(data, dict) else None
    if (not isinstance(data, dict) or "error" in data or not isinstance(data.get("advisories"), dict)
            or not isinstance(meta, dict) or not isinstance(meta.get("vulnerabilities"), dict)):
        detail = data.get("error") if isinstance(data, dict) else None
        raise RuntimeError(f"pnpm audit no devolvió un reporte (error del registro o salida inesperada): {detail or tail(text, 3)}")
    total = meta.get("totalDependencies")
    if not isinstance(total, int):
        total = sum(int(meta.get(k) or 0) for k in ("dependencies", "devDependencies", "optionalDependencies"))
    out = []
    for adv in data["advisories"].values():
        ids = [str(adv.get("github_advisory_id") or "")] + [str(c) for c in adv.get("cves") or []]
        ids += GHSA_RE.findall(str(adv.get("url") or ""))
        findings = adv.get("findings") or []
        dev_only = bool(findings) and all(f.get("dev") for f in findings)
        out.append({"ids": unique(ids), "package": f"{adv.get('module_name', '?')}" + (" (solo dev)" if dev_only else ""),
                    "severity": str(adv.get("severity") or "high").lower(),
                    "fix": adv.get("patched_versions") or "sin versión corregida"})
    return out, total


# ── dart ──────────────────────────────────────────────────────────────────────────────────────────

def count_pub_packages(text: str) -> int:
    n, inside = 0, False
    for line in text.splitlines():
        if re.match(r"\S", line):
            inside = line.rstrip() == "packages:"
        elif inside and re.match(r"  [A-Za-z0-9_]+:\s*$", line):
            n += 1
    return n


def dart_findings(root: Path) -> tuple[list[dict], int]:
    total = count_pub_packages((root / "pubspec.lock").read_text(encoding="utf-8-sig"))
    res = run(["docker", "run", "--rm", "-v", f"{root.resolve()}:/src:ro", OSV_IMAGE,
               "scan", "source", "-L", "/src/pubspec.lock", "--format", "json"], root)
    if res.returncode == 128:
        raise RuntimeError("osv-scanner no encontró paquetes en pubspec.lock (código 128)")
    if res.returncode not in (0, 1):
        raise RuntimeError(f"osv-scanner (docker) terminó con código {res.returncode}:\n    {tail(res.stderr)}")
    findings = parse_osv(res.stdout)
    if res.returncode == 1 and not findings:
        raise RuntimeError("osv-scanner salió con 1 (hallazgos) pero su JSON no trae vulnerabilidades")
    return findings, total


def cvss_level(score: str) -> str:
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "high"
    if value <= 0:
        return "high"
    return "critical" if value >= 9 else "high" if value >= 7 else "moderate" if value >= 4 else "low"


def parse_osv(text: str) -> list[dict]:
    data = load_json(text, "osv-scanner")
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise RuntimeError("osv-scanner no devolvió un reporte (falta la lista 'results')")
    out = []
    for result in data["results"]:
        for pkg in result.get("packages") or []:
            info = pkg.get("package") or {}
            name, label = info.get("name", "?"), f"{info.get('name', '?')} {info.get('version', '?')}"
            vulns = {v.get("id"): v for v in pkg.get("vulnerabilities") or [] if v.get("id")}
            groups = pkg.get("groups") or [{"ids": [vid], "aliases": [], "max_severity": ""} for vid in vulns]
            for group in groups:
                members = [vulns[i] for i in group.get("ids") or [] if i in vulns]
                ids = list(group.get("ids") or []) + list(group.get("aliases") or [])
                for v in members:
                    ids += [v.get("id", "")] + list(v.get("aliases") or [])
                fixes = []
                for v in members:
                    for aff in v.get("affected") or []:
                        if (aff.get("package") or {}).get("name") not in (None, name):
                            continue
                        for rng in aff.get("ranges") or []:
                            fixes += [e["fixed"] for e in rng.get("events") or [] if e.get("fixed")]
                out.append({"ids": unique(ids), "package": label, "severity": cvss_level(group.get("max_severity")),
                            "fix": ", ".join(unique(fixes, upper=False)) or "sin versión corregida"})
    return out


# ── common ────────────────────────────────────────────────────────────────────────────────────────

def unique(items, upper: bool = True) -> list[str]:
    seen, out = set(), []
    for i in items:
        i = str(i or "").strip()
        i = i.upper() if upper else i
        if i and i != "NONE" and i not in seen:
            seen.add(i)
            out.append(i)
    return out


AUDITORS = (("python", "pyproject.toml", python_findings), ("node", "pnpm-lock.yaml", node_findings),
            ("dart", "pubspec.lock", dart_findings))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--min-severity", default="high", choices=sorted(LEVELS))
    ap.add_argument("--repo", default=".")
    ap.add_argument("--allow-empty", action="store_true", help="un repo sin lockfile reconocido pasa (nunca en CI de código)")
    ap.add_argument("--self-test", action="store_true", help="prueba los parsers con fixtures embebidos")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    root = Path(a.repo).resolve()
    detected = [(name, fn) for name, marker, fn in AUDITORS if (root / marker).exists()]
    if (root / "pyproject.toml").exists():
        strays = sorted(p.name for pattern in SECOND_SOURCES for p in root.glob(pattern))
        if strays:
            print(f"security_audit: dos fuentes de dependencias: pyproject.toml + {', '.join(strays)} "
                  "(Vercel puede instalar de ellas; lo auditado sale de uv.lock): bórralas", file=sys.stderr)
            return 2
    if not detected:
        if a.allow_empty:
            print("security_audit: sin lockfile reconocido: nada que auditar (--allow-empty)")
            return 0
        print("security_audit: sin lockfile reconocido (pyproject.toml + uv.lock, pnpm-lock.yaml, pubspec.lock): "
              "sin auditor para este repo", file=sys.stderr)
        return 2
    allowed, problems = load_exceptions(root / ".security-exceptions", dt.date.today())
    findings: list[dict] = []
    try:
        for name, fn in detected:
            found, total = fn(root)
            print(f"auditado {name}: {total} paquetes")
            if total <= 0:
                raise RuntimeError(f"{name}: 0 paquetes auditados (el auditor no vio el lockfile)")
            findings += found
    except (RuntimeError, OSError, ValueError) as exc:
        print(f"security_audit: error de herramienta (falla cerrado): {exc}", file=sys.stderr)
        return 2
    threshold = LEVELS[a.min_severity]
    blocking = [f for f in findings if LEVELS.get(f["severity"], 3) >= threshold and not (set(f["ids"]) & allowed)]
    for f in blocking:
        problems.append(f"{f['severity'].upper():8} {f['package']} · {', '.join(f['ids'][:3])} · corrige con: {f['fix']}")
    if problems:
        print("security_audit: FALLA\n  " + "\n  ".join(problems))
        return 1
    print(f"security_audit: ok ({len(findings)} hallazgos bajo el umbral o con excepción vigente)")
    return 0


# ── self-test ─────────────────────────────────────────────────────────────────────────────────────

FIXTURE_PNPM = json.dumps({
    "advisories": {"1": {"id": 1, "title": "axios SSRF", "module_name": "axios", "vulnerable_versions": "<1.8.2",
                         "patched_versions": ">=1.8.2", "severity": "high", "cwe": "CWE-918",
                         "github_advisory_id": "GHSA-jr5f-v2jv-69x6",
                         "url": "https://github.com/advisories/GHSA-jr5f-v2jv-69x6",
                         "findings": [{"version": "1.7.9", "paths": ["."], "dev": False, "optional": False, "bundled": False}]}},
    "metadata": {"vulnerabilities": {"info": 0, "low": 0, "moderate": 0, "high": 1, "critical": 0},
                 "dependencies": 80, "devDependencies": 40, "optionalDependencies": 0, "totalDependencies": 120}})
FIXTURE_PIP = json.dumps({"dependencies": [
    {"name": "django", "version": "5.2.0", "vulns": [{"id": "PYSEC-2025-1", "fix_versions": ["5.2.1"], "aliases": ["CVE-2025-0001"]}]},
    {"name": "pillow", "version": "11.3.0", "vulns": []}], "fixes": []})
FIXTURE_OSV = json.dumps({"results": [{"source": {"path": "/src/pubspec.lock", "type": "lockfile"}, "packages": [{
    "package": {"name": "dio", "version": "4.0.6", "ecosystem": "Pub"},
    "vulnerabilities": [{"id": "GHSA-9324-jv53-9cc8", "aliases": ["CVE-2021-31402"], "affected": [{
        "package": {"name": "dio", "ecosystem": "Pub"},
        "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "5.0.0"}]}]}]}],
    "groups": [{"ids": ["GHSA-9324-jv53-9cc8"], "aliases": ["CVE-2021-31402", "GHSA-9324-jv53-9cc8"], "max_severity": "7.5"}]}]}]})
FIXTURE_PUBSPEC_LOCK = "packages:\n  dio:\n    dependency: \"direct main\"\n    version: \"4.0.6\"\n  http:\n    version: \"1.2.0\"\nsdks:\n  dart: \">=3.5.0 <4.0.0\"\n"


def self_test() -> int:
    failures: list[str] = []
    cases = [0]

    def check(name: str, fn) -> None:
        cases[0] += 1
        try:
            if not fn():
                failures.append(name)
        except Exception as exc:  # noqa: BLE001 - a crash is a failure of the case
            failures.append(f"{name} ({type(exc).__name__}: {exc})")

    def raises(fn) -> bool:
        try:
            fn()
        except RuntimeError:
            return True
        return False

    check("pnpm 11: un advisory high con GHSA", lambda: (lambda f, n: len(f) == 1 and f[0]["severity"] == "high"
          and "GHSA-JR5F-V2JV-69X6" in f[0]["ids"] and n == 120)(*parse_pnpm_audit(FIXTURE_PNPM)))
    check("pnpm: JSON de error del registro = error", lambda: raises(lambda: parse_pnpm_audit(
        '{"error": {"code": "ERR_PNPM_AUDIT_BAD_RESPONSE", "message": "410 Gone"}}')))
    check("pnpm: salida vacía = error", lambda: raises(lambda: parse_pnpm_audit("")))
    check("pnpm 10 = error", lambda: raises(lambda: require_pnpm("10.34.7")))
    check("pnpm 11 aceptado", lambda: require_pnpm("11.28.6") is None)
    check("pip-audit: una vulnerabilidad", lambda: (lambda f, n: len(f) == 1 and n == 2
          and {"PYSEC-2025-1", "CVE-2025-0001"} <= set(f[0]["ids"]))(*parse_pip_audit(FIXTURE_PIP)))
    check("pip-audit: salida vacía con código 1 = error", lambda: raises(lambda: parse_pip_audit("")))
    check("osv pub: dio 4.0.6 = CVE-2021-31402 high", lambda: (lambda f: len(f) == 1 and f[0]["severity"] == "high"
          and "CVE-2021-31402" in f[0]["ids"] and f[0]["fix"] == "5.0.0")(parse_osv(FIXTURE_OSV)))
    check("osv: reporte sin results = error", lambda: raises(lambda: parse_osv('{"error": "x"}')))
    check("pubspec.lock: 2 paquetes", lambda: count_pub_packages(FIXTURE_PUBSPEC_LOCK) == 2)
    check("CVSS 9.8 = critical, 5.0 = moderate, vacío = high",
          lambda: (cvss_level("9.8"), cvss_level("5.0"), cvss_level("")) == ("critical", "moderate", "high"))

    def exceptions_window() -> bool:
        today = dt.date(2026, 1, 1)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / ".security-exceptions"
            p.write_text("GHSA-aaaa-aaaa-aaaa 2026-04-01 a 90 días\nGHSA-bbbb-bbbb-bbbb 2026-04-02 a 91 días\n", encoding="utf-8")
            ok, problems = load_exceptions(p, today)
        return ok == {"GHSA-AAAA-AAAA-AAAA"} and len(problems) == 1
    check("excepciones: 90 días sí, 91 no", exceptions_window)

    if failures:
        print("security_audit --self-test: FALLA\n  " + "\n  ".join(failures))
        return 1
    print(f"security_audit --self-test: ok ({cases[0]} casos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
