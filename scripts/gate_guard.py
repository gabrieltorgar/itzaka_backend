#!/usr/bin/env python3
"""
gate_guard.py — stops a work-branch pull request that changes the gate that judges it.

  python3 scripts/gate_guard.py --base origin/develop [--repo .] [--approved]

Lists the files changed on HEAD since its merge base with --base (`git diff --name-only --no-renames
<base>...HEAD`) and flags the gate files (git-deploy-ops SKILL.md, "Gate files"):
  whole files  .github/workflows/**, .github/dependabot.yml, .github/CODEOWNERS, scripts/test_gate.py,
               scripts/security_audit.py, scripts/gate_guard.py, scripts/readme_sync.py, .security-exceptions,
               .gitleaksignore, .coveragerc, pytest.ini, vitest.config.*, src/tests/platform/**,
               src/__tests__/platform/**, test/platform/** (mobile)
  sections     pyproject.toml [tool.coverage*] and [tool.pytest*]; the `test: { … }` block (coverage
               included) of vite.config.*; the `headers` of vercel.json
Exit 0 = no gate file changed, or --approved (the user approved the change in chat; record it in the PR
body) · 1 = gate files changed without --approved → BLOQUEO_DEPLOY (gate_modificado) with the diff ·
2 = git error (unknown base, not a repository).
"""
import argparse, fnmatch, json, re, subprocess, sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

GATE_GLOBS = (
    ".github/workflows/*", ".github/dependabot.yml", ".github/dependabot.yaml", ".github/CODEOWNERS",
    "scripts/test_gate.py", "scripts/security_audit.py", "scripts/gate_guard.py", "scripts/readme_sync.py",
    ".security-exceptions", ".gitleaksignore", ".coveragerc", "pytest.ini", "vitest.config.*",
    "src/tests/platform/*", "src/__tests__/platform/*", "test/platform/*",
)


class GitError(RuntimeError):
    pass


def git(repo, *args, check=True):
    res = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and res.returncode:
        raise GitError(f"git {' '.join(args)}: {res.stderr.strip()}")
    return res


def show(repo, rev, path):
    res = git(repo, "show", f"{rev}:{path}", check=False)
    return res.stdout if res.returncode == 0 else ""


def toml_sections(text, prefixes=("tool.coverage", "tool.pytest")):
    out, keep = [], False
    for line in text.splitlines():
        header = re.match(r"\s*\[\[?\s*([^\]]+?)\s*\]\]?\s*(#.*)?$", line)
        if header:
            keep = header.group(1).startswith(prefixes)
        if keep:
            out.append(line.rstrip())
    return "\n".join(out)


def js_block(text, key="test"):
    m = re.search(rf"(?<![\w.]){key}\s*:\s*\{{", text)
    if not m:
        return ""
    depth, i = 0, m.end() - 1
    for j in range(i, len(text)):
        depth += {"{": 1, "}": -1}.get(text[j], 0)
        if depth == 0:
            return text[i:j + 1]
    return text[i:]


def json_headers(text):
    try:
        return json.dumps(json.loads(text).get("headers"), sort_keys=True) if text.strip() else ""
    except (ValueError, AttributeError):
        return text


SECTION_RULES = (
    (lambda p: p.rsplit("/", 1)[-1] == "pyproject.toml", toml_sections, "[tool.coverage*] / [tool.pytest*]"),
    (lambda p: re.search(r"(^|/)vite\.config\.[cm]?[jt]s$", p), js_block, "bloque test/coverage de vite.config"),
    (lambda p: p.rsplit("/", 1)[-1] == "vercel.json", json_headers, "headers de vercel.json"),
)


def gate_hits(repo, base):
    mb = git(repo, "merge-base", base, "HEAD").stdout.strip()
    changed = [p for p in git(repo, "diff", "--name-only", "--no-renames", f"{mb}..HEAD").stdout.splitlines() if p]
    hits = []
    for path in changed:
        if any(fnmatch.fnmatch(path, g) for g in GATE_GLOBS):
            hits.append((path, "archivo de gate"))
            continue
        for match, extract, label in SECTION_RULES:
            if match(path) and extract(show(repo, mb, path)) != extract(show(repo, "HEAD", path)):
                hits.append((path, label))
                break
    return mb, changed, hits


def main(argv=None):
    ap = argparse.ArgumentParser(description="Archivos de gate modificados en la rama de trabajo")
    ap.add_argument("--base", required=True, help="rama destino del PR, p. ej. origin/develop")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--approved", action="store_true", help="el usuario aprobó el cambio de gate en el chat")
    a = ap.parse_args(argv)
    try:
        mb, changed, hits = gate_hits(a.repo, a.base)
    except (GitError, OSError) as exc:
        print(f"gate_guard: error de git: {exc}", file=sys.stderr)
        return 2
    if not hits:
        print(f"gate_guard: ok ({len(changed)} archivos cambiados, ninguno de gate)")
        return 0
    lines = "\n".join(f"  {p} ({why})" for p, why in hits)
    if a.approved:
        print(f"gate_guard: cambios de gate aprobados por el usuario (regístralo en el cuerpo del PR):\n{lines}")
        return 0
    print("BLOQUEO_DEPLOY\n- Etapa: pull_request\n- Motivo: gate_modificado\n- Evidencia:\n" + lines
          + f"\n- Acción requerida: revisa el diff (git diff {mb[:12]}..HEAD -- <archivo>) y aprueba en el chat;"
          " el cambio viaja como su propio item TEC")
    return 1


if __name__ == "__main__":
    sys.exit(main())
