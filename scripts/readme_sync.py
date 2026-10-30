#!/usr/bin/env python3
"""
readme_sync.py — keeps a code repo's README.md in the house format (git-deploy-ops references/readme-format.md):
generated blocks rewritten from the repo's sources of truth, curated sections written by people.

  python3 scripts/readme_sync.py --check --kind backend [--repo .] [--docs <memoria>] [--require-routes] [--json]
  python3 scripts/readme_sync.py --write --kind frontend [--docs <memoria>] [--dry-run]
  python3 <skill>/scripts/readme_sync.py --init --kind mobile --repo <repo> [--docs <memoria>] [--template <md>]
  python3 scripts/readme_sync.py --adopt --kind backend [--docs <memoria>] [--dry-run]

Blocks are delimited by <!-- readme:auto:<id> --> … <!-- /readme:auto:<id> --> and only this script writes them;
every other line is curated text and is never changed or deleted (markers inside code fences are ignored).
  --write   regenerates every block; a mandatory block missing from the README → exit 1 (run --adopt)
  --check   exit 1 when a block is stale, a mandatory block or section is missing, the README version differs from
            the manifest or a value of a real .env file appears in the README; prints the unified diff --write would
            apply. Generic contribution text ("Fork el proyecto") is a warning in every mode: human text goes only
            on the user's yes, and compliance doc (DOC-RM04) keeps reporting it
  --init    creates README.md from assets/readme/README.<kind>.md (or --template) when there is none; curated
            sections keep their <!-- COMPLETA: … --> hints. In a new repo before its scaffold (no manifest file
            yet) the blocks that come from the manifest stay "Pendiente" until the scaffold commit's --write
  --adopt   existing README: keeps every line, inserts each missing block under its section (matched by heading,
            with synonyms such as "Instalación" → Puesta en marcha), else as a new section at the template's
            position, else in a final "Referencia generada" section; reports the missing curated sections
  --docs    project memory: estado/proyecto.json fills the "entornos" block (without --docs that block is kept
            as it is) and its cobertura_minima is cross-checked against the workflow's MIN_COVERAGE
  --routes-cmd  command that prints the backend API table (default: uv run --no-sync python src/manage.py
            api_routes --format md → "| Método | Ruta | Vista | Nombre |", only when the repo already has .venv:
            nothing is installed or downloaded). When it can't run, the block is kept and a warning printed — never
            wiped; --require-routes makes that exit 2 (CI)
  --dry-run prints the report and the diff without writing; --json prints the report as JSON
Deterministic: sorted listings, no dates or absolute paths, only the files git shows (tracked + untracked not
ignored), so CI and a laptop agree. Keeps the UTF-8 BOM and each kept line's ending (new lines take the file's
majority). Never writes a value from .env or .env.example: names and comments only.
Exit 0 = in sync / written · 1 = drift or pending action (report) · 2 = can't run (no repo, no manifest outside
--init, manifest without a version, a source or the README not in UTF-8, malformed markers, template missing, README
present for --init or absent for --write/--adopt, --require-routes failing); with --json, exit 2 prints {"error"}.
"""
import argparse
import codecs
import difflib
import json
import os
import re
import subprocess
import sys
import tomllib
import unicodedata
from collections import namedtuple
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

KINDS = ("backend", "frontend", "mobile")
MANIFESTS = {"backend": "pyproject.toml", "frontend": "package.json", "mobile": "pubspec.yaml"}
SKILL_TEMPLATES = Path(__file__).resolve().parent.parent / "assets" / "readme"

Section = namedtuple("Section", "key title blocks synonyms")


def _sec(key, title, blocks=(), synonyms=()):
    return Section(key, title, tuple(blocks), tuple(synonyms))


_MODULOS = _sec("modulos", "Módulos", (), ("modulos principales", "caracteristicas", "funcionalidades", "features",
                                           "que hace", "funciones"))
_ESTADO = _sec("estado", "Estado", ("version", "entornos"), ("version", "entornos", "estado del proyecto"))
_STACK = _sec("stack", "Stack", ("stack",), ("stack tecnologico", "tecnologias", "tecnologia", "dependencias"))
_REQ = _sec("requisitos", "Requisitos", ("requisitos",), ("requerimientos", "prerrequisitos", "requisitos previos"))
_SETUP = _sec("puesta", "Puesta en marcha", ("puesta-en-marcha",), ("instalacion", "setup", "inicio rapido",
                                                                     "como empezar", "configuracion local",
                                                                     "desarrollo local", "primeros pasos"))
_VARS = _sec("variables", "Variables de entorno", ("variables",), ("variables", "entorno", "configuracion", "env"))
_CMDS = _sec("comandos", "Comandos", ("comandos",), ("scripts", "scripts disponibles", "comandos utiles"))
_TESTS = _sec("pruebas", "Pruebas y quality gate", ("pruebas",), ("pruebas", "testing", "tests", "quality gate"))
_TREE = _sec("estructura", "Estructura", ("estructura",), ("estructura del proyecto", "estructura de carpetas",
                                                           "arquitectura"))
_API = _sec("api", "API", ("api",), ("endpoints", "endpoints principales", "rutas de la api"))
_RUTAS = _sec("rutas", "Rutas", ("rutas",), ("rutas publicas", "paginas publicas"))
_PANT = _sec("pantallas", "Pantallas", ("pantallas",), ("screens", "navegacion"))
_PLAT = _sec("plataformas", "Plataformas y build", ("plataformas",), ("plataformas", "build", "flavors",
                                                                      "compilacion"))
_AUTH = _sec("auth", "Autenticación y sesión", (), ("autenticacion", "sesion", "auth", "login"))
_INTEG = _sec("integraciones", "Integraciones", (), ("servicios externos", "terceros"))
_ADMIN = _sec("admin", "Administración", (), ("admin", "admin panel", "panel de administracion"))
_MARCA = _sec("marca", "Marca y tema", (), ("marca", "tema", "paleta de colores", "paleta", "colores", "diseno",
                                            "sistema de diseno"))
_DEPLOY = _sec("despliegue", "Despliegue", ("despliegue",), ("deploy", "despliegue en vercel"))
_DEPLOY_MOBILE = _sec("despliegue", "Despliegue", (), ("deploy", "distribucion", "publicacion", "tiendas"))
_DOCS = _sec("documentacion", "Documentación", ("documentacion",), ("docs", "enlaces", "referencias"))
_CONTRIB = _sec("contribucion", "Contribución", ("contribucion",), ("contribuir", "contributing", "como contribuir"))
_LIC = _sec("licencia", "Licencia", (), ("license", "licencia y contacto"))

# Template order; every section is mandatory (the templates may add the optional "Contacto" after Licencia).
SPEC = {
    "backend": [_MODULOS, _ESTADO, _STACK, _REQ, _SETUP, _VARS, _CMDS, _TESTS, _TREE, _API, _AUTH, _INTEG, _ADMIN,
                _DEPLOY, _DOCS, _CONTRIB, _LIC],
    "frontend": [_MODULOS, _ESTADO, _STACK, _REQ, _SETUP, _VARS, _CMDS, _TESTS, _TREE, _RUTAS, _AUTH, _INTEG, _MARCA,
                 _DEPLOY, _DOCS, _CONTRIB, _LIC],
    "mobile": [_MODULOS, _ESTADO, _STACK, _REQ, _SETUP, _VARS, _CMDS, _TESTS, _TREE, _PANT, _PLAT, _AUTH, _INTEG,
               _MARCA, _DEPLOY_MOBILE, _DOCS, _CONTRIB, _LIC],
}
BLOCKS = {k: [b for s in v for b in s.blocks] for k, v in SPEC.items()}

FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
ATX = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
# at most 3 spaces of indent: 4 or more is an indented code block (CommonMark), where markers are only shown
OPEN = re.compile(r"^ {0,3}<!--\s*readme:auto:([a-z0-9][a-z0-9-]*)(?:\s[^>]*)?-->\s*$")
CLOSE = re.compile(r"^ {0,3}<!--\s*/readme:auto:([a-z0-9][a-z0-9-]*)\s*-->\s*$")
HINT = re.compile(r"<!--\s*COMPLETA:")
VERSION_IN_BLOCK = re.compile(r"\*\*Versión:\*\*\s*([0-9A-Za-z.\-]+)")
# Generic open-source contribution text ("Fork el proyecto", feature/AmazingFeature). The same two patterns, byte for
# byte, in agent_files.py, docs-hub readme_docs.py and compliance-audit scan.py (test_assets.py compares them).
GENERIC_CONTRIB = re.compile(r"\bfork\w*\b[^\n]{0,40}\b(?:proyecto|repositorio|project|repo)\b|amazingfeature|checkout\s+-b\s+feature/", re.I)
GENERIC_NEGATED = re.compile(r"\b(?:no|nunca|never|sin)\b[^\n]{0,30}\bfork", re.I)
HEX_COLOR = re.compile(r"(?<![\w&/#])#(?=[0-9A-Fa-f]*\d)(?:[0-9A-Fa-f]{8}|[0-9A-Fa-f]{6})\b")
ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]{2,})\s*=\s*\S")
ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")
URL_CREDENTIALS = re.compile(r"(\b[a-z][a-z0-9+.\-]*://)[^/\s:@]+:[^/\s@]+@", re.I)
ROUTES_HEADER = ["Método", "Ruta", "Vista", "Nombre"]
REQUIRED_CHECKS = ("quality-gate", "security")
CONTRIB_RULES = ".claude/rules/contribucion.md"
CONTRIB_STEM = re.compile(r"(contribuci[oó]n|contributing|contribution)([-_. ].*)?", re.I)  # agent_files.py's aliases
CONTRIBUTING = tuple(f"{d}{n}" for d in ("", ".github/", "docs/")
                     for n in ("CONTRIBUTING.md", "CONTRIBUTING.rst", "CONTRIBUTING.txt", "CONTRIBUTING"))
LOCKS = {"pnpm": "pnpm-lock.yaml", "npm": "package-lock.json", "yarn": "yarn.lock"}
INSTALL = {"pnpm": "pnpm install --frozen-lockfile", "npm": "npm ci", "yarn": "yarn install --frozen-lockfile"}
SKIP_DIRS = {"__pycache__", "node_modules"}  # build output is gitignored; an app may well be called "reports"
SECRET_NAME = re.compile(r"SECRET|PASSWORD|PASSWD|TOKEN|KEY|PRIVATE|CREDENTIAL|DSN|AUTH", re.I)


class Fatal(Exception):
    """Can't run at all: exit 2."""


class Unavailable(Exception):
    """A block's source can't be read now: the block is kept as it is (or gets the placeholder when empty)."""

    def __init__(self, reason, placeholder):
        super().__init__(reason)
        self.reason, self.placeholder = reason, placeholder


# ── text helpers ────────────────────────────────────────────────────────────────────────────────────────────

def read_file(path, label=None):
    """(text with LF, raw text as read without the BOM, BOM present); a file that isn't UTF-8 → Fatal (exit 2)."""
    raw = Path(path).read_bytes()
    bom = raw.startswith(codecs.BOM_UTF8)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise Fatal(f"{label or Path(path).name}: no es UTF-8 (byte {e.start}); guárdalo como UTF-8") from None
    return text.replace("\r\n", "\n"), text, bom


def restore_endings(new, raw_old):
    """new (LF) with the line endings of raw_old: every line kept from it keeps its own ending (a mixed README stays
    byte for byte outside the regenerated blocks); new or changed lines take the file's majority ending."""
    if "\r\n" not in raw_old:
        return new
    parts = raw_old.split("\n")
    last = len(parts) - 1
    crlf = [i < last and p.endswith("\r") for i, p in enumerate(parts)]
    old = [p[:-1] if crlf[i] else p for i, p in enumerate(parts)]
    majority = sum(crlf) * 2 > last
    crlf[last] = majority  # the old last line had no ending: if it gets one, the majority's
    lines = new.split("\n")
    ends = [majority] * len(lines)
    for tag, i1, i2, j1, _j2 in difflib.SequenceMatcher(None, old, lines, autojunk=False).get_opcodes():
        if tag == "equal":
            ends[j1:j1 + i2 - i1] = crlf[i1:i2]
    return "".join(line + ("\r\n" if end else "\n") for line, end in zip(lines[:-1], ends)) + lines[-1]


def write_file(path, text, raw_old="", bom=False):
    out = restore_endings(text, raw_old)
    Path(path).write_bytes((codecs.BOM_UTF8 if bom else b"") + out.encode("utf-8"))


def norm(text):
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s]|_", " ", text.lower())
    return " ".join(text.split())


def code(text):
    text = str(text)
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    fence = "`" * (longest + 1)
    pad = " " if longest or text.startswith("`") or text.endswith("`") else ""
    return f"{fence}{pad}{text}{pad}{fence}"


def cell(text):
    return str(text).replace("\n", " ").replace("|", "\\|").strip() or "—"


def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(cell(c) for c in row) + " |" for row in rows]
    return "\n".join(out)


def sort_key(name):
    return (str(name).lower(), str(name))


def redact(text):
    return URL_CREDENTIALS.sub(r"\1<usuario>:<contraseña>@", text)


def generic_contrib(line):
    """A line of generic open-source contribution text ("No se aceptan forks del repositorio" is not)."""
    return bool(GENERIC_CONTRIB.search(line)) and not GENERIC_NEGATED.search(line)


def pct(fraction):
    value = fraction * 100
    return f"{value:.0f} %" if abs(value - round(value)) < 1e-9 else f"{value:.1f} %"


def unquote(value):
    """A YAML scalar without its surrounding quotes ('' inside single quotes is one quote)."""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1].replace("''", "'") if value[0] == "'" else value[1:-1]
    return value


def strip_yaml_comment(line):
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i].rstrip()
    return line.rstrip()


def mini_yaml(text):
    """Mappings only (enough for pubspec.yaml): nested dicts of scalars; lists and block scalars are skipped."""
    root, block = {}, None
    stack = [(-1, root)]
    for raw in text.split("\n"):
        line = strip_yaml_comment(raw)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        if block is not None:
            if indent > block:
                continue
            block = None
        body = line.strip()
        if body.startswith("- ") or body == "-":
            continue
        m = re.match(r"^(\"[^\"]*\"|'[^']*'|[^:]+?):(?:\s+(.*))?$", body)
        if not m:
            continue
        key, value = unquote(m.group(1)), (m.group(2) or "").strip()
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if not value:
            parent[key] = {}
            stack.append((indent, parent[key]))
        elif value[0] in "|>":
            parent[key] = ""
            block = indent
        else:
            parent[key] = unquote(value)
    return root


# ── Markdown scan ──────────────────────────────────────────────────────────────────────────────────────────

class Doc:
    """README lines with its headings and generated blocks; code fences are skipped."""

    def __init__(self, text):
        self.lines = text.split("\n")
        self.headings, self.blocks, self.errors = [], {}, []
        fence, current = None, None
        n = len(self.lines)
        for i, line in enumerate(self.lines):
            m = FENCE.match(line)
            if fence:
                if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) \
                        and not line.strip()[len(m.group(1)):].strip():
                    fence = None
                continue
            if m:
                fence = m.group(1)
                continue
            opened, closed = OPEN.match(line), CLOSE.match(line)
            if opened:
                bid = opened.group(1)
                if current:
                    self.errors.append(f"línea {i + 1}: bloque «{bid}» abierto dentro de «{current[0]}»")
                elif bid in self.blocks:
                    self.errors.append(f"línea {i + 1}: bloque «{bid}» duplicado")
                else:
                    current = (bid, i)
                continue
            if closed:
                bid = closed.group(1)
                if not current or current[0] != bid:
                    self.errors.append(f"línea {i + 1}: cierre de «{bid}» sin su apertura")
                else:
                    self.blocks[bid] = (current[1], i)
                    current = None
                continue
            if current:
                continue
            h = ATX.match(line)
            if h:
                self.headings.append((i, len(h.group(1)), (h.group(2) or "").strip()))
            elif (line.strip() and i + 1 < n and SETEXT.match(self.lines[i + 1])
                  and (i == 0 or not self.lines[i - 1].strip()) and not re.match(r"^\s*([-*+>|<]|\d+[.)])", line)):
                self.headings.append((i, 1 if self.lines[i + 1].strip()[0] == "=" else 2, line.strip()))
        if current:
            bid, at = current
            self.errors.append(f"línea {at + 1}: bloque «{bid}» sin cierre <!-- /readme:auto:{bid} -->")

    def generated(self, i):
        return any(o <= i <= c for o, c in self.blocks.values())

    def fenced_lines(self):
        """Indexes of lines inside code fences (fence lines included)."""
        out, fence = set(), None
        for i, line in enumerate(self.lines):
            m = FENCE.match(line)
            if fence:
                out.add(i)
                if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) \
                        and not line.strip()[len(m.group(1)):].strip():
                    fence = None
            elif m:
                fence = m.group(1)
                out.add(i)
        return out

    def section_end(self, idx, level):
        for j, lvl, _ in self.headings:
            if j > idx and lvl <= level:
                return j
        return len(self.lines)

    def heading_before(self, i, max_level=6):
        found = None
        for j, lvl, title in self.headings:
            if j > i:
                break
            if 2 <= lvl <= max_level:
                found = (j, lvl, title)
        return found


def section_for(title, kind, taken=()):
    n = norm(title)
    for sec in SPEC[kind]:
        if sec.key in taken:
            continue
        for syn in (norm(sec.title),) + sec.synonyms:
            if n == syn or n.startswith(syn + " "):
                return sec.key
    return None


def map_sections(doc, kind):
    """{section key: (line, level, title)} — `##` headings first, deeper ones only for sections still unmatched and
    never inside another named section («### Autenticación» under «## Módulos» is a module, not the auth section)."""
    found = {}
    for wanted in (lambda lvl: lvl == 2, lambda lvl: lvl > 2):
        for idx, level, title in doc.headings:
            if not wanted(level) or any(v[0] == idx for v in found.values()):
                continue
            key = section_for(title, kind, found)
            parent = doc.heading_before(idx, max_level=2) if level > 2 else None
            if key and parent and section_for(parent[2], kind) not in (None, key):
                continue
            if key:
                found[key] = (idx, level, title)
    return found


# ── sources of truth ───────────────────────────────────────────────────────────────────────────────────────

class Ctx:
    def __init__(self, root, kind, docs=None, routes_cmd=None, before_scaffold=False):
        self.root, self.kind, self.routes_cmd = Path(root), kind, routes_cmd
        self.warnings = []
        self.project, self.brand = None, False
        if docs:
            pj = Path(docs) / "estado" / "proyecto.json"
            if not pj.exists():
                raise Fatal(f"--docs {docs}: falta estado/proyecto.json")
            try:
                self.project = json.loads(pj.read_text(encoding="utf-8-sig"))
            except (ValueError, OSError) as e:
                raise Fatal(f"estado/proyecto.json ilegible ({e})")
            self.brand = (Path(docs) / "site" / "marca" / "index.html").exists()
        self.visible = git_visible(self.root)
        # --init in a new repo runs before the scaffold brings the manifest: None, and the blocks it feeds stay
        # pending (a manifest that exists but can't be read, or has no version, is still exit 2)
        missing = before_scaffold and not (self.root / MANIFESTS[kind]).exists()
        self.manifest = None if missing else self._manifest()

    @property
    def m(self):
        if self.manifest is None:
            src = MANIFESTS[self.kind]
            raise Unavailable(f"sin {src} todavía (llega con el scaffold)",
                              f"Pendiente: sale de {code(src)}, que llega con el scaffold; "
                              f"`python3 scripts/readme_sync.py --write --kind {self.kind}` llena este bloque.")
        return self.manifest

    # files: inside a git work tree only what git shows (tracked + untracked not ignored), so a local
    # staticfiles/, logs/ or ignored .python-version never reaches the README and CI sees the same tree
    def p(self, rel):
        return self.root / rel

    def shown(self, path):
        path = Path(path)
        if not path.exists():
            return False
        if self.visible is None:
            return True
        rel = self.rel(path)
        return rel in self.visible[0] or rel in self.visible[1]

    def has(self, rel):
        return self.shown(self.root / rel)

    def is_dir(self, rel):
        return self.has(rel) and (self.root / rel).is_dir()

    def read(self, rel):
        return read_file(self.root / rel, rel)[0]

    def subdirs(self, rel):
        base = self.root / rel
        if not base.is_dir():
            return []
        return sorted((d for d in base.iterdir() if d.is_dir() and not d.name.startswith((".", "_"))
                       and d.name not in SKIP_DIRS and self.shown(d)), key=lambda d: sort_key(d.name))

    def files(self, rel, pattern):
        base = self.root / rel
        if not base.is_dir():
            return []
        return sorted((f for f in base.glob(pattern) if f.is_file() and self.shown(f)), key=lambda f: sort_key(f.name))

    def rglob(self, rel, pattern):
        base = self.root / rel
        if not base.is_dir():
            return []
        return sorted((f for f in base.rglob(pattern) if f.is_file() and self.shown(f)),
                      key=lambda f: self.rel(f).lower())

    def rel(self, path):
        return Path(path).relative_to(self.root).as_posix()

    # manifest
    def _manifest(self):
        src = MANIFESTS[self.kind]
        if self.kind == "backend":
            if not (self.root / src).exists():
                raise Fatal("sin pyproject.toml en el repositorio")
            try:
                data = tomllib.loads(self.read(src))
            except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
                raise Fatal(f"pyproject.toml ilegible ({e})")
            proj = data.get("project") or {}
            poetry = (data.get("tool") or {}).get("poetry") or {}
            if "version" in (proj.get("dynamic") or []):
                raise Fatal("pyproject.toml: versión dinámica; el flujo escribe la versión con set_version.py")
            version, build = proj.get("version") or poetry.get("version"), None
            name = proj.get("name") or poetry.get("name") or ""
            desc = proj.get("description") or poetry.get("description") or ""
        elif self.kind == "frontend":
            if not (self.root / src).exists():
                raise Fatal("sin package.json en el repositorio")
            try:
                data = json.loads(self.read(src))
            except ValueError as e:
                raise Fatal(f"package.json ilegible ({e})")
            version, build = data.get("version"), None
            name, desc = data.get("name") or "", data.get("description") or ""
        else:
            if not (self.root / src).exists():
                raise Fatal("sin pubspec.yaml en el repositorio")
            data = mini_yaml(self.read(src))
            raw = str(data.get("version") or "")
            version, _, build = raw.partition("+")
            build = build or None
            name, desc = data.get("name") or "", data.get("description") or ""
        if not version or not isinstance(version, str):
            raise Fatal(f"{src} sin versión")
        return {"data": data, "version": version, "build": build, "name": name, "description": desc, "source": src}

    def deps(self):
        """(runtime: [(name, spec)], groups: {group: [names]})."""
        if not hasattr(self, "_deps"):
            self._deps = self._read_deps()
        return self._deps

    def _read_deps(self):
        d, runtime, groups = self.m["data"], [], {}
        if self.kind == "backend":
            for req in (d.get("project") or {}).get("dependencies") or []:
                runtime.append(split_requirement(req))
            for group, items in sorted(((d.get("dependency-groups") or {}).items())):
                groups[group] = sorted({split_requirement(i)[0] for i in items if isinstance(i, str)}, key=sort_key)
            legacy = ((d.get("tool") or {}).get("uv") or {}).get("dev-dependencies") or []
            if legacy:
                groups.setdefault("dev", sorted({split_requirement(i)[0] for i in legacy}, key=sort_key))
        elif self.kind == "frontend":
            for name, spec in (d.get("dependencies") or {}).items():
                runtime.append((name, "referencia directa" if "://" in str(spec) else str(spec)))
            dev = d.get("devDependencies") or {}
            if dev:
                groups["devDependencies"] = sorted(dev, key=sort_key)
        else:
            for name, spec in (d.get("dependencies") or {}).items():
                runtime.append((name, pub_spec(spec)))
            dev = d.get("dev_dependencies") or {}
            if dev:
                groups["dev_dependencies"] = sorted(dev, key=sort_key)
        return sorted(runtime, key=lambda r: sort_key(r[0])), groups

    def has_dep(self, *prefixes):
        runtime, groups = self.deps()
        names = [n.split("[")[0].lower() for n, _ in runtime]
        names += [n.split("[")[0].lower() for group in groups.values() for n in group]
        return any(n == p or n.startswith(p) for n in names for p in prefixes)

    def env_example(self):
        candidates = [".env.example", "src/core/.env.example", "src/.env.example"] if self.kind == "backend" \
            else [".env.example"]
        return next((c for c in candidates if self.has(c)), None)

    def env_entries(self):
        rel = self.env_example()
        return (rel, parse_env(self.read(rel))) if rel else (None, [])

    def real_env_values(self):
        """{(file, name): value} of secret-looking values in the real env files (never printed)."""
        dirs = {"backend": [".", "src/core", "src"]}.get(self.kind, ["."])
        out = {}
        example = {n: v for n, _d, v in self.env_entries()[1]}
        for d in dirs:
            base = self.p(d)
            if not base.is_dir():
                continue
            for f in sorted(base.glob(".env*"), key=lambda x: x.name):
                if not f.is_file() or f.name.endswith((".example", ".sample", ".template")):
                    continue
                try:
                    entries = parse_env(read_file(f)[0])
                except (OSError, UnicodeDecodeError, Fatal):
                    continue
                for name, _desc, value in entries:
                    secret = SECRET_NAME.search(name) or URL_CREDENTIALS.search(value)
                    if secret and len(value) >= 8 and value != example.get(name):
                        out[(self.rel(f), name)] = value
        return out

    def workflows(self):
        out = []
        for f in self.files(".github/workflows", "*.y*ml"):
            try:
                out.append((self.rel(f), read_file(f)[0]))
            except (OSError, UnicodeDecodeError, Fatal):
                self.warnings.append(f"workflow ilegible: {self.rel(f)}")
        return out

    def gate_workflow(self):
        flows = self.workflows()
        for rel, text in flows:
            if "quality-gate" in workflow_checks(text):
                return rel, text
        return next(((rel, text) for rel, text in flows if Path(rel).stem == "quality-gate"), (None, None))

    def min_coverage(self):
        _rel, text = self.gate_workflow()
        m = re.search(r"^\s*MIN_COVERAGE:\s*[\"']?([0-9.]+)", text or "", re.M)
        value = float(m.group(1)) if m else 0.90
        return value / 100 if value > 1 else value

    def manage(self):
        return "src/manage.py" if self.has("src/manage.py") else ("manage.py" if self.has("manage.py") else None)

    def contrib_rules(self):
        """The contribution rules: .claude/rules/contribucion.md, else the equivalent agent_files.py accepts
        (.claude/rules/**/contribucion*|contributing*.md); None when there is none."""
        rules = [self.rel(f) for f in self.rglob(".claude/rules", "*.md")]
        if CONTRIB_RULES in rules:
            return CONTRIB_RULES
        return next((r for r in rules if CONTRIB_STEM.fullmatch(Path(r).stem)), None)

    def contributing(self):
        """CONTRIBUTING in the root, .github/ or docs/ (where GitHub shows it); None when there is none."""
        return next((p for p in CONTRIBUTING if self.has(p)), None)

    def package_manager(self):
        """Frontend: pnpm (the flow's) unless the repo clearly uses npm or yarn (packageManager, else its lockfile)."""
        declared = str(self.m["data"].get("packageManager") or "").split("@", 1)[0]
        if self.has(LOCKS["pnpm"]) or declared == "pnpm":
            return "pnpm"
        if declared in ("npm", "yarn"):
            return declared
        return next((pm for pm in ("npm", "yarn") if self.has(LOCKS[pm])), "pnpm")

    def lockfile(self):
        """The lockfile of the repo's package manager when it exists (None before the first install)."""
        lock = {"backend": "uv.lock", "mobile": "pubspec.lock"}.get(self.kind) or LOCKS[self.package_manager()]
        return lock if self.has(lock) else None


def git_visible(root):
    """(files, dirs) that git shows under root — tracked plus untracked not ignored — or None outside git."""
    try:
        res = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                             capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    files = {f for f in res.stdout.decode("utf-8", "replace").split("\0") if f} if res.returncode == 0 else set()
    if not files:
        return None
    dirs = {"/".join(parts[:i]) for parts in (f.split("/") for f in files) for i in range(1, len(parts))}
    return files, dirs


def split_requirement(req):
    req = req.split(";", 1)[0].strip()
    m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*(.*)$", req)
    if not m:
        return req, ""
    spec = m.group(3).strip()
    if spec.startswith("@"):
        spec = "referencia directa"
    return m.group(1) + (m.group(2) or ""), spec


def pub_spec(spec):
    if isinstance(spec, dict):
        if spec.get("sdk"):
            return f"SDK de {spec['sdk'].capitalize()}"
        if "git" in spec:
            return "git"
        if "path" in spec:
            return "local (path)"
        return str(spec.get("version") or "sin restricción")
    return str(spec) if spec not in ("", None) else "sin restricción"


def parse_env(text):
    """[(name, description, value)] in file order; the value is only used to detect leaks."""
    out, seen, comments = [], set(), []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            comments = []
            continue
        if line.startswith("#"):
            body = line.lstrip("#").strip()
            if ENV_LINE.match(body):  # a commented-out assignment holds a value: never a description
                comments = []
                continue
            if body and not re.match(r"^[-=*#~]{3,}", body):
                comments.append(body)
            continue
        m = ENV_LINE.match(raw)
        if not m:
            comments = []
            continue
        name, rest = m.group(1), m.group(2).strip()
        if rest and rest[0] in "\"'":
            end = rest.find(rest[0], 1)
            value = rest[1:end] if end != -1 else rest[1:]
            after = rest[end + 1:] if end != -1 else ""
        elif rest.startswith("#") and m.group(2)[0] in " \t":  # NAME= # comment: empty value
            value, after = "", rest   # (NAME=#value, without a space, is the value "#value" for dotenv/django-environ)
        else:
            hit = re.search(r"\s#", rest)
            value, after = (rest[:hit.start()], rest[hit.start():]) if hit else (rest, "")
        after = after.strip()
        desc = after[1:].strip() if after.startswith("#") else " ".join(comments)
        desc = redact(desc)
        if value.strip() and len(value.strip()) >= 4:
            desc = desc.replace(value.strip(), "…")
        if name not in seen:
            seen.add(name)
            out.append((name, desc, value.strip()))
        comments = []
    return out


def workflow_checks(text):
    """Job display names (status-check contexts) of a workflow."""
    names, in_jobs, job = [], False, None
    for line in text.split("\n"):
        if re.match(r"^jobs:\s*$", line):
            in_jobs = True
            continue
        if in_jobs and re.match(r"^\S", line):
            in_jobs = False
        if not in_jobs:
            continue
        m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if m:
            job = m.group(1)
            names.append(job)
            continue
        m = re.match(r"^    name:\s*(.+?)\s*$", strip_yaml_comment(line))
        if m and job and names and names[-1] == job:
            names[-1] = unquote(m.group(1))
    return names


def workflow_steps(text):
    """[(name, command | None, script_lines, condition)] of every `run` step, in order."""
    lines, steps, i = text.split("\n"), [], 0
    while i < len(lines):
        m = re.match(r"^(\s*)steps:\s*$", lines[i])
        if not m:
            i += 1
            continue
        base = len(m.group(1))
        i += 1
        items, current = [], None
        while i < len(lines):
            line = lines[i]
            ind = len(line) - len(line.lstrip())
            if line.strip() and (ind < base or (ind == base and not line.lstrip().startswith("- "))):
                break
            im = re.match(r"^(\s*)- (.*)$", line)
            if im and (current is None or len(im.group(1)) == current[0]):
                current = (len(im.group(1)), [" " * (len(im.group(1)) + 2) + im.group(2)])
                items.append(current)
            elif current is not None:
                current[1].append(line)
            i += 1
        for indent, body in items:
            steps.append(parse_step(body, indent + 2))
    return [s for s in steps if s[1] is not None or s[2]]


def parse_step(body, key_indent):
    fields, j = {}, 0
    while j < len(body):
        line = body[j]
        m = re.match(r"^(\s*)([A-Za-z_-]+):\s*(.*)$", line)
        if m and len(m.group(1)) == key_indent:
            key, value = m.group(2), strip_yaml_comment(m.group(3)).strip()
            if value and value[0] in "|>":
                block, j = [], j + 1
                while j < len(body) and (not body[j].strip() or len(body[j]) - len(body[j].lstrip()) > key_indent):
                    block.append(body[j].strip())
                    j += 1
                block = [b for b in block if b]
                fields[key] = (value[0], block)
                continue
            fields[key] = ("=", unquote(value))
        j += 1
    name = fields.get("name", ("=", ""))[1]
    cond = fields.get("if", ("=", ""))[1]
    run = fields.get("run")
    if not run:
        return name, None, 0, cond
    style, value = run
    if style == "=":
        return name, value, 0, cond
    if style == ">":
        return name, " ".join(value), 0, cond
    return (name, value[0], 0, cond) if len(value) == 1 else (name, None, len(value), cond)


def parse_routes(output):
    rows, header_seen = [], False
    for line in output.replace("\r\n", "\n").split("\n"):
        s = line.strip()
        if not s.startswith("|"):
            if header_seen and rows:
                break
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", s)[1:-1]]
        if not header_seen:
            if cells == ROUTES_HEADER:
                header_seen = True
            continue
        if all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
            continue
        if len(cells) != 4:
            return None
        rows.append(cells)
    if not header_seen:
        return None
    rows.sort(key=lambda r: (r[1], r[0], r[2], r[3]))  # path, method, view, name: the command's own order
    head = ["| " + " | ".join(ROUTES_HEADER) + " |", "|---|---|---|---|"]
    return "\n".join(head + ["| " + " | ".join(r) + " |" for r in rows])


# ── generated blocks ──────────────────────────────────────────────────────────────────────────────────────

def gen_version(ctx):
    m = ctx.m
    build = f" (build {m['build']})" if m["build"] else ""
    out = f"**Versión:** {m['version']}{build} — {code(m['source'])}"
    if ctx.has("CHANGELOG.md"):
        out += " · historial en [CHANGELOG.md](CHANGELOG.md)"
    return out


def gen_entornos(ctx):
    if ctx.project is None:
        raise Unavailable("sin --docs (estado/proyecto.json): se conserva",
                          f"Pendiente: `python3 scripts/readme_sync.py --write --kind {ctx.kind} --docs <memoria>` "
                          "llena esta tabla desde `estado/proyecto.json` de la memoria del proyecto.")
    pj = ctx.project
    ramas = pj.get("ramas") or {}
    prod, dev = ramas.get("produccion") or "main", ramas.get("desarrollo") or "develop"
    dom = pj.get("dominio")
    lines = []
    if pj.get("infraestructura") == "tercero":
        lines.append("Infraestructura de un tercero: entornos, URLs y procedimiento de despliegue en "
                     "`tecnico/despliegue.md` de la memoria del proyecto (`<proyecto>_docs`, privada).")
    elif not dom:
        lines.append("Dominio aún sin definir (`estado/proyecto.json → dominio`).")
    else:
        rows = {
            "backend": [("Producción", prod, f"https://api.{dom} · admin https://api.{dom}/admin/"),
                        ("Desarrollo", dev, f"https://api-dev.{dom}")],
            "frontend": [("Producción", prod, f"https://{dom}"), ("Desarrollo", dev, f"https://dev.{dom}")],
            "mobile": [("API de producción", prod, f"https://api.{dom}"),
                       ("API de desarrollo", dev, f"https://api-dev.{dom}")],
        }[ctx.kind]
        lines.append(table(["Entorno", "Rama", "URL"], [(e, code(b), u) for e, b, u in rows]))
        if ctx.kind == "mobile":
            lines += ["", "La app se distribuye por las tiendas: ver [Despliegue](#despliegue)."]
    if dom and pj.get("infraestructura") == "autogestionada":  # with a third party there is no docs site of ours
        docs = f"Documentación del proyecto: https://docs.{dom}"
        if ctx.brand:
            docs += f" · marca: https://docs.{dom}/marca/"
        lines += ["", docs]
    return "\n".join(lines)


def gen_stack(ctx):
    runtime, groups = ctx.deps()
    src, lock = ctx.m["source"], ctx.lockfile()
    rows = [(code(n), code(s) if s and " " not in s else (s or "sin restricción")) for n, s in runtime]
    out = [table(["Paquete", "Versión declarada"], rows) if rows
           else f"Sin dependencias de runtime declaradas en {code(src)}."]
    for group, names in groups.items():
        if names:
            out += ["", f"Desarrollo y pruebas ({code(group)}): " + ", ".join(code(n) for n in names) + "."]
    out += ["", f"Fuente: {code(src)}; " + (f"versiones exactas en {code(lock)}." if lock else "sin lockfile todavía.")]
    return "\n".join(out)


def gen_requisitos(ctx):
    d, out = ctx.m["data"], []
    if ctx.kind == "backend":
        rp = (d.get("project") or {}).get("requires-python")
        out.append(f"- Python {code(rp)} (`requires-python`)" if rp
                   else "- Python (sin `requires-python` en `pyproject.toml`)")
        if ctx.has(".python-version"):
            out[-1] += f"; versión local fijada en `.python-version`: {code(ctx.read('.python-version').strip())}"
        uvv = ((d.get("tool") or {}).get("uv") or {}).get("required-version")
        out.append("- [uv](https://docs.astral.sh/uv/)" + (f" {code(uvv)}" if uvv else "") + ": entorno y dependencias"
                   + ("" if ctx.has("requirements.txt") else " (no hay `requirements.txt`)"))
        if ctx.has("requirements.txt"):
            ctx.warnings.append("requirements.txt junto a pyproject.toml: la fuente es pyproject.toml/uv.lock "
                                "(uv export lo genera si un tercero lo pide)")
        if ctx.has_dep("psycopg"):
            out.append("- PostgreSQL accesible por `DATABASE_URL`")
    elif ctx.kind == "frontend":
        node = (d.get("engines") or {}).get("node")
        if node:
            out.append(f"- Node {code(node)} (`engines.node`)")
        elif ctx.has(".nvmrc") or ctx.has(".node-version"):
            f = ".nvmrc" if ctx.has(".nvmrc") else ".node-version"
            out.append(f"- Node {code(ctx.read(f).strip())} (`{f}`)")
        else:
            out.append("- Node (sin versión en `engines.node`)")
        pm, pnpm = ctx.package_manager(), pnpm_version(d)
        if pm != "pnpm":
            lock = ctx.lockfile()
            out.append(f"- {pm} (" + (f"`{lock}`" if lock else "`packageManager`") + ")")
            ctx.warnings.append(f"el repositorio usa {pm}: el flujo usa pnpm ≥ 11 con `packageManager` y "
                                "`pnpm-lock.yaml` (migrarlo es un item TEC)")
        elif pnpm:
            out.append(f"- pnpm {code(pnpm)} (`packageManager`, exacta: CI y `security` la usan)")
        else:
            out.append("- pnpm (sin `packageManager` en `package.json`)")
    else:
        env = d.get("environment") or {}
        if isinstance(env, dict) and env.get("flutter"):
            out.append(f"- Flutter {code(env['flutter'])} (`environment.flutter`)")
        else:
            out.append("- Flutter estable (sin `environment.flutter` en `pubspec.yaml`)")
        if isinstance(env, dict) and env.get("sdk"):
            out.append(f"- Dart {code(env['sdk'])} (`environment.sdk`)")
        if ctx.has("android"):
            out.append("- Android SDK (Android Studio) para `android/`")
        if ctx.has("ios"):
            out.append("- Xcode en macOS para `ios/`")
    out.append("- Git")
    return "\n".join(out)


def pnpm_version(package):
    pm = str(package.get("packageManager") or "")
    return pm.split("@", 1)[1].split("+")[0] if pm.startswith("pnpm@") else None


def script_cmd(pm, name):
    """How the package manager runs a package.json script."""
    return f"npm run {name}" if pm == "npm" else f"{pm} {name}"


def flavors(ctx):
    names = {f.stem[5:] for f in ctx.files("lib", "main_*.dart")}
    for gradle in ("android/app/build.gradle.kts", "android/app/build.gradle"):
        if not ctx.has(gradle):
            continue
        text = ctx.read(gradle)
        m = re.search(r"productFlavors\s*\{", text)
        if not m:
            continue
        depth, i, start = 1, m.end(), m.end()
        while i < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        body = text[start:i - 1]
        names |= set(re.findall(r"create\(\s*\"(\w+)\"\s*\)", body))
        depth = 0
        for line in body.split("\n"):
            g = re.match(r"^\s*(\w+)\s*\{", line)
            if g and depth == 0 and g.group(1) != "create":
                names.add(g.group(1))
            depth += line.count("{") - line.count("}")
    return sorted(names, key=sort_key)


def gen_puesta(ctx):
    steps = ["Clona el repositorio y entra en su carpeta."]
    env = ctx.env_example()
    if ctx.kind == "backend":
        steps.append("Instala las dependencias (runtime, desarrollo y pruebas) "
                     + ("desde `uv.lock`: " + code("uv sync --locked --all-groups") if ctx.has("uv.lock")
                        else "— aún sin `uv.lock`: " + code("uv sync --all-groups")))
        if env:
            target = env[:-len(".example")]
            note = " — `DATABASE_URL` apunta a tu PostgreSQL local" if ctx.has_dep("psycopg") else ""
            steps.append(f"Copia las variables y complétalas con los valores del equipo (`{target}` nunca se "
                         f"commitea): {code(f'cp {env} {target}')}{note}")
        manage = ctx.manage()
        if manage:
            run = f"uv run python {manage}"
            steps.append(f"Aplica las migraciones: {code(run + ' migrate')}")
            settings = [f for d in ("src/core", "src", ".") for f in ctx.files(d, "*.py")]
            if any("DatabaseCache" in ctx.read(ctx.rel(f)) for f in settings):
                steps.append(f"Crea la tabla de caché (throttling): {code(run + ' createcachetable')}")
            steps.append(f"Crea un superusuario para el admin: {code(run + ' createsuperuser')}")
            steps.append(f"Levanta el servidor: {code(run + ' runserver')} → http://localhost:8000 "
                         "(admin en `/admin/`)")
    elif ctx.kind == "frontend":
        d = ctx.m["data"]
        pm, lock = ctx.package_manager(), ctx.lockfile()
        node, pnpm = (d.get("engines") or {}).get("node"), pnpm_version(d) if pm == "pnpm" else None
        parts = ([f"Node {code(node)}"] if node else []) + ([f"pnpm {code(pnpm)}"] if pnpm else [])
        if parts:
            steps.append("Usa " + " y ".join(parts) + " (las versiones de `package.json`).")
        if lock:
            steps.append(f"Instala las dependencias desde `{lock}`: " + code(INSTALL[pm]))
        else:
            steps.append(f"Instala las dependencias — aún sin lockfile, el primer install crea `{LOCKS[pm]}` y va en "
                         "el mismo commit: " + code(f"{pm} install"))
            ctx.warnings.append(f"sin `{LOCKS[pm]}`: commitéalo con el manifiesto (CI instala con "
                                f"`{INSTALL[pm]}`)")
        if env:
            steps.append("Copia las variables (solo valores públicos: todo `VITE_*` termina en el bundle): "
                         + code("cp .env.example .env"))
        scripts = d.get("scripts") or {}
        if "dev" in scripts:
            url = " → http://localhost:5173" if ctx.has_dep("vite") else ""
            steps.append(f"Levanta el servidor de desarrollo: {code(script_cmd(pm, 'dev'))}{url}")
    else:
        if ctx.has("pubspec.lock"):
            steps.append("Instala las dependencias desde `pubspec.lock`: " + code("flutter pub get --enforce-lockfile"))
        else:
            steps.append("Instala las dependencias — aún sin `pubspec.lock`, que este comando crea y va en el mismo "
                         "commit: " + code("flutter pub get"))
            ctx.warnings.append("sin `pubspec.lock`: commitéalo con `pubspec.yaml` (CI instala con "
                                "`flutter pub get --enforce-lockfile`)")
        if env:
            steps.append("Copia las variables (solo valores públicos: se compilan en la app): "
                         + code("cp .env.example .env"))
        if ctx.has_dep("build_runner"):
            steps.append("Genera el código (Freezed, json_serializable, envied): "
                         + code("dart run build_runner build --delete-conflicting-outputs"))
        if l10n(ctx):
            steps.append("Genera las localizaciones: " + code("flutter gen-l10n"))
        fl = flavors(ctx)
        if fl:
            steps.append(f"Corre la app: {code('flutter run --flavor <flavor> -t lib/main_<flavor>.dart')} (flavors: "
                         + ", ".join(code(f) for f in fl) + ")")
        else:
            steps.append("Corre la app en un emulador o dispositivo: " + code("flutter run"))
    return "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))


def l10n(ctx):
    flutter = ctx.m["data"].get("flutter")
    return ctx.has("l10n.yaml") or (isinstance(flutter, dict) and str(flutter.get("generate")).lower() == "true")


def gen_variables(ctx):
    rel, entries = ctx.env_entries()
    if not rel:
        return ("Sin `.env.example` en el repositorio: es el contrato de variables (nombres sin valores) y se crea "
                "con el scaffold.")
    target = rel[:-len(".example")]
    out = [f"Archivo: {code(rel)} → cópialo a {code(target)}. Aquí solo van los nombres: los valores nunca se "
           "escriben en el README ni se commitean."]
    if ctx.kind == "frontend":
        out += ["", "Todo `VITE_*` es público (termina en el bundle): el quality gate solo admite la lista permitida."]
    if ctx.kind == "mobile":
        out += ["", "Todo lo de `.env` se compila en la app (envied): solo valores públicos; CI escribe `.env` desde "
                    "las variables del repositorio."]
    out += ["", table(["Variable", "Descripción"], [(code(n), d) for n, d, _v in entries]) if entries
            else f"{code(rel)} no declara variables."]
    return "\n".join(out)


MAKE_TARGET = re.compile(r"^([A-Za-z0-9][\w.-]*(?:[ \t]+[A-Za-z0-9][\w.-]*)*)[ \t]*:(?![=:])([^#\n]*?)(?:##\s*(.*))?$")


def make_targets(text):
    """{target: description}: its `## …`, the comment above it, else its first recipe line (URL credentials masked)."""
    out, lines, comment = {}, text.split("\n"), None
    for idx, line in enumerate(lines):
        if line.startswith("\t"):
            continue
        s = line.strip()
        if s.startswith("#"):
            comment = s.lstrip("#").strip() or None
            continue
        m = MAKE_TARGET.match(line)
        if m:
            desc = redact((m.group(3) or "").strip() or comment or "")
            if not desc and idx + 1 < len(lines) and lines[idx + 1].startswith("\t"):
                desc = code(redact(lines[idx + 1].strip().lstrip("@-").strip()))
            for target in m.group(1).split():
                out.setdefault(target, desc or "")
        comment = None
    return dict(sorted(out.items(), key=lambda kv: sort_key(kv[0])))


def management_commands(ctx):
    out = []
    if not ctx.has("src"):
        return out
    for f in ctx.rglob("src", "management/commands/*.py"):
        if f.name.startswith("_") or any(part in SKIP_DIRS for part in Path(ctx.rel(f)).parts):
            continue
        help_text = re.search(r"\bhelp\s*=\s*(?:_\()?\s*([\"'])(.*?)\1", ctx.read(ctx.rel(f)))
        out.append((f.stem, help_text.group(2) if help_text else "Comando del proyecto", ctx.rel(f)))
    return sorted(out, key=lambda c: sort_key(c[0]))


def gen_comandos(ctx):
    rows = []
    if ctx.has("Makefile"):
        rows += [(code(f"make {t}"), d or "—") for t, d in make_targets(ctx.read("Makefile")).items()]
    if ctx.kind == "backend":
        manage = ctx.manage()
        if manage:
            run = f"uv run python {manage}"
            rows += [(code(f"{run} runserver"), "Servidor de desarrollo"),
                     (code(f"{run} makemigrations"), "Crea migraciones tras cambiar modelos"),
                     (code(f"{run} migrate"), "Aplica las migraciones")]
            rows += [(code(f"{run} {name}"), f"{h} ({code(rel)})") for name, h, rel in management_commands(ctx)]
        if ctx.has_dep("pytest"):
            rows.append((code("uv run pytest"), "Pruebas (con cobertura: ver Pruebas y quality gate)"))
        if ctx.has_dep("ruff"):
            rows += [(code("uv run ruff format ."), "Formato"), (code("uv run ruff check ."), "Lint (`--fix` corrige)")]
        rows.append((code("uv add <paquete>"), "Agrega una dependencia de runtime (`--group dev` para desarrollo)"))
    elif ctx.kind == "frontend":
        scripts, pm = ctx.m["data"].get("scripts") or {}, ctx.package_manager()
        rows += [(code(script_cmd(pm, n)), code(redact(str(scripts[n])))) for n in sorted(scripts, key=sort_key)]
        if ctx.has("components.json"):
            dlx = "pnpm dlx" if pm == "pnpm" else "npx"
            rows.append((code(f"{dlx} shadcn@latest add <componente>"),
                         "Agrega una primitiva de shadcn/ui en `src/components/ui/`"))
        add = "npm install" if pm == "npm" else f"{pm} add"
        rows.append((code(f"{add} <paquete>"), "Agrega una dependencia (`-D` para desarrollo)"))
    else:
        rows.append((code("flutter pub get"), "Instala las dependencias"))
        if ctx.has_dep("build_runner"):
            rows.append((code("dart run build_runner build --delete-conflicting-outputs"),
                         "Código generado (Freezed, json_serializable, envied)"))
        if l10n(ctx):
            rows.append((code("flutter gen-l10n"), "Localizaciones desde `lib/l10n/*.arb`"))
        rows += [(code("dart format lib test"), "Formato"),
                 (code("flutter analyze --fatal-infos"), "Analyzer (sin infos)"),
                 (code("flutter test --coverage"), "Pruebas con cobertura"), (code("flutter run"), "Corre la app")]
    return table(["Comando", "Para qué"], rows)


MIN_COVERAGE_REF = re.compile(r"\"?(?:\$\{\{\s*env\.MIN_COVERAGE\s*\}\}|\$\{?MIN_COVERAGE\}?)\"?")


def local_command(command, minimum):
    """A workflow `run` line as it is typed locally: MIN_COVERAGE with its value (an empty shell variable would make
    test_gate.py fail on `--min ''`), without the trailing `|| true` that lets CI hand the verdict to the gate, and
    with URL credentials masked."""
    value = f"{minimum:.2f}" if abs(round(minimum, 2) - minimum) < 1e-9 else f"{minimum:g}"
    command = MIN_COVERAGE_REF.sub(value, command)
    return redact(re.sub(r"\s*\|\|\s*true\s*$", "", command))


def gen_pruebas(ctx):
    rel, text = ctx.gate_workflow()
    out = []
    if rel:
        out.append(f"Pasos de `quality-gate` ({code(rel)}), en orden; los mismos comandos sirven en local (con el "
                   "valor de `MIN_COVERAGE` ya puesto):")
        out.append("")
        n = 0
        for name, command, script, cond in workflow_steps(text):
            n += 1
            when = f" (solo si {code(cond)})" if cond else ""
            if command is None:
                out.append(f"{n}. {name or 'Script'}{when}: script de {script} líneas en el workflow")
            else:
                label = f"{name}{when}: " if name else (f"{when.strip()} " if when else "")
                out.append(f"{n}. {label}{code(local_command(command, ctx.min_coverage()))}")
        out += ["", f"Cobertura mínima: **{pct(ctx.min_coverage())}** (`MIN_COVERAGE` del workflow). Una prueba en "
                    "rojo, una omitida sin motivo permitido o una cobertura menor bloquean el merge."]
    else:
        out.append(f"Sin workflow `quality-gate`: el check obligatorio aún no existe (item `TEC Quality gate de CI`). "
                   f"Cobertura mínima del flujo: **{pct(ctx.min_coverage())}**.")
    rows = [(code(r), ", ".join(code(c) for c in workflow_checks(t)) or "—",
             "sí" if any(c in REQUIRED_CHECKS for c in workflow_checks(t)) else "no") for r, t in ctx.workflows()]
    if rows:
        out += ["", table(["Workflow", "Check", "Obligatorio en `main` y `develop`"], rows)]
    else:
        out += ["", "Sin workflows en `.github/workflows/`: faltan los checks obligatorios `quality-gate` y "
                    "`security`."]
    if ctx.project and ctx.project.get("cobertura_minima") is not None:
        try:
            recorded = float(ctx.project["cobertura_minima"])
        except (TypeError, ValueError):
            recorded = None
        recorded = recorded / 100 if recorded and recorded > 1 else recorded
        if recorded is not None and abs(recorded - ctx.min_coverage()) > 1e-9:
            ctx.warnings.append(f"cobertura_minima {pct(recorded)} de estado/proyecto.json ≠ MIN_COVERAGE "
                                f"{pct(ctx.min_coverage())} del workflow (el workflow es el que aplica CI)")
    return "\n".join(out)


BACKEND_DIRS = {"api": "URLs raíz de la API (incluye las de cada app)", "apps": "Apps de dominio (tabla abajo)",
                "common": "Código compartido: modelos abstractos, permisos, paginación, filtros, acciones masivas, "
                          "errores",
                "core": "Settings, URLs, WSGI/ASGI y middleware", "tests": "Pruebas de plataforma (línea base)",
                "templates": "Plantillas", "static": "Estáticos propios"}
FRONT_DIRS = {"app": "Entrada, providers y router", "assets": "Imágenes y recursos de origen",
              "components": "`ui/` (shadcn/ui, generado por el CLI), `shared/`, `hook-form/`, `layout/`",
              "config": "`APP_NAME` y variables públicas aprobadas", "features": "Módulos de dominio (tabla abajo)",
              "hooks": "Hooks compartidos", "lib": "Configuración de terceros (axios, query client) y `api-error.ts`",
              "routes": "Rutas, guards y `public-routes.json`", "services": "Servicios de API compartidos",
              "stores": "Stores de Zustand", "types": "Tipos compartidos", "utils": "Utilidades"}
MOBILE_DIRS = {"app": "Widget raíz y GoRouter", "core": "Red (Dio), errores, layout adaptativo, paginación, "
               "almacenamiento seguro (`TokenStore`) y tema", "features": "Módulos de dominio por capas (tabla abajo)",
               "l10n": "Traducciones `.arb`"}
ROOT_DIRS = {"scripts": "Scripts vendorizados (quality gate, README) y de build", ".github/workflows": "CI",
             "public": "Archivos públicos (`og/`, favicon)",
             "test": "Pruebas (`flutter_test`), con la línea base en `test/platform/`",
             "integration_test": "Pruebas de integración", "docs": "Documentación local del repositorio"}


def gen_estructura(ctx):
    base, known = {"backend": ("src", BACKEND_DIRS), "frontend": ("src", FRONT_DIRS),
                   "mobile": ("lib", MOBILE_DIRS)}[ctx.kind]
    rows = [(code(f"{base}/{d.name}/"), known.get(d.name, "—")) for d in ctx.subdirs(base)]
    if ctx.kind == "frontend" and ctx.has("src/index.css"):
        rows.append((code("src/index.css"), "Tokens de diseño (`:root` y `.dark`)"))
    if ctx.kind == "mobile" and ctx.has("lib/main.dart"):
        rows.append((code("lib/main.dart"), "Punto de entrada (`ProviderScope`)"))
    rows += [(code(f"{d}/"), desc) for d, desc in ROOT_DIRS.items() if ctx.is_dir(d)
             and not (ctx.kind != "mobile" and d == "test") and not (ctx.kind != "frontend" and d == "public")]
    out = [table(["Ruta", "Contenido"], rows) if rows else f"Sin `{base}/` todavía (llega con el scaffold)."]
    if ctx.kind == "backend":
        apps = []
        for d in ctx.subdirs("src/apps"):
            if ctx.shown(d / "apps.py"):
                m = re.search(r"verbose_name\s*=\s*(?:_|gettext_lazy|gettext|pgettext_lazy)?\s*\(?\s*([\"'])(.*?)\1",
                              ctx.read(ctx.rel(d / "apps.py")))
                apps.append((code(f"apps.{d.name}"), m.group(2) if m else "—"))
        if apps:
            out += ["", table(["App", "Nombre (`verbose_name`)"], apps)]
    elif ctx.kind == "frontend":
        feats = []
        for d in ctx.subdirs("src/features"):
            pages = sorted(ctx.files(ctx.rel(d / "pages"), "*Page.tsx") + ctx.files(ctx.rel(d / "pages"), "*Page.jsx"),
                           key=lambda f: sort_key(f.name))
            feats.append((code(d.name), ", ".join(code(f.stem) for f in pages) or "—"))
        if feats:
            out += ["", table(["Feature", "Pantallas (`pages/*Page.tsx`)"], feats)]
    else:
        layers = ("data", "domain", "application", "presentation")
        feats = [(code(d.name), ", ".join(layer for layer in layers if ctx.is_dir(ctx.rel(d / layer))) or "—")
                 for d in ctx.subdirs("lib/features")]
        if feats:
            out += ["", table(["Feature", "Capas"], feats)]
    return "\n".join(out)


def gen_api(ctx):
    placeholder = ("Pendiente: la tabla sale de `uv run python src/manage.py api_routes --format md` "
                   "(django-backend-conventions) al correr `readme_sync.py --write` con Django instalado.")
    if ctx.routes_cmd:
        cmd, shell = ctx.routes_cmd, True
    else:
        manage = ctx.manage()
        if not manage:
            raise Unavailable("sin manage.py: no se puede listar el URLconf", placeholder)
        # `uv run` creates .venv (and may download a Python) when the project has no environment: a check never
        # installs anything, so without one the block is kept (CI runs `uv sync` before this step)
        env_dir = os.environ.get("UV_PROJECT_ENVIRONMENT")
        if not ((ctx.root / ".venv").is_dir() or (env_dir and (ctx.root / env_dir).is_dir())):
            raise Unavailable("sin .venv: corre uv sync --locked --all-groups (no se crea un entorno para listar "
                              "rutas)", placeholder)
        cmd, shell = ["uv", "run", "--no-sync", "python", manage, "api_routes", "--format", "md"], False
    try:
        res = subprocess.run(cmd, shell=shell, cwd=ctx.root, capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=180,
                             env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
                                  "UV_PYTHON_DOWNLOADS": "never"})
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Unavailable(f"no se pudo ejecutar el comando de rutas ({e.__class__.__name__})", placeholder)
    if res.returncode:
        tail = redact((res.stderr or res.stdout or "").strip().split("\n")[-1])[:160]
        raise Unavailable(f"el comando de rutas terminó con código {res.returncode}" + (f": {tail}" if tail else ""),
                          placeholder)
    rows = parse_routes(res.stdout)
    if rows is None:
        raise Unavailable("la salida del comando de rutas no trae la tabla | Método | Ruta | Vista | Nombre |",
                          placeholder)
    return "Rutas del URLconf (comando `api_routes`), ordenadas por ruta:\n\n" + rows


def gen_rutas(ctx):
    rel = "src/routes/public-routes.json"
    if not ctx.has(rel):
        return f"Sin rutas públicas: no existe {code(rel)} (toda la app es privada)."
    try:
        data = json.loads(ctx.read(rel))
        routes = data.get("routes") or []
    except (ValueError, AttributeError) as e:
        raise Unavailable(f"{rel} ilegible ({e.__class__.__name__})", f"Pendiente: {code(rel)} no se pudo leer.")
    out = [f"Manifiesto: {code(rel)}" + (f" (sitio {data['siteUrl']})" if data.get("siteUrl") else "")
           + ". Cada ruta pública se sirve con su `<head>` estático y, si es indexable, entra en `sitemap.xml`."]
    rows = [(code(r.get("path", "?")), r.get("title", "—"), "legal" if r.get("kind") == "legal" else "página",
             "no" if r.get("indexable") is False else "sí")
            for r in sorted((r for r in routes if isinstance(r, dict)), key=lambda r: sort_key(r.get("path", "")))]
    out += ["", table(["Ruta", "Título", "Tipo", "Indexable"], rows) if rows else "El manifiesto no declara rutas."]
    private = sorted(data.get("privatePrefixes") or [], key=sort_key)
    if private:
        out += ["", "Prefijos privados (fuera del sitemap, `Disallow` en `robots.txt`): "
                + ", ".join(code(p) for p in private) + "."]
    return "\n".join(out)


def gen_pantallas(ctx):
    rows = []
    for d in ctx.subdirs("lib/features"):
        screens = ctx.files(ctx.rel(d / "presentation" / "screens"), "*.dart")
        if screens:
            rows.append((code(d.name), ", ".join(code(f.name) for f in screens)))
    out = [table(["Feature", "Pantallas (`presentation/screens/`)"], rows) if rows
           else "Sin pantallas todavía (`lib/features/*/presentation/screens/`)."]
    if ctx.has("lib/app/router.dart"):
        paths = sorted(set(re.findall(r"path:\s*['\"]([^'\"]+)['\"]", ctx.read("lib/app/router.dart"))), key=sort_key)
        if paths:
            out += ["", "Rutas de GoRouter (`lib/app/router.dart`): " + ", ".join(code(p) for p in paths) + "."]
    return "\n".join(out)


PLATFORMS = [("android", "Android", "flutter build appbundle"), ("ios", "iOS", "flutter build ipa"),
             ("web", "Web", "flutter build web"), ("macos", "macOS", "flutter build macos"),
             ("windows", "Windows", "flutter build windows"), ("linux", "Linux", "flutter build linux")]


def gen_plataformas(ctx):
    fl = flavors(ctx)
    suffix = " --flavor <flavor> -t lib/main_<flavor>.dart"
    rows = [(name, code(f"{d}/"), code(cmd + (suffix if fl and d in ("android", "ios") else "")))
            for d, name, cmd in PLATFORMS if ctx.is_dir(d)]
    out = [table(["Plataforma", "Carpeta", "Build de release"], rows) if rows
           else "Sin carpetas de plataforma (`android/`, `ios/`…): se crean con "
                "`flutter create --platforms=<lista> .`."]
    if fl:
        out += ["", "Flavors: " + ", ".join(code(f) for f in fl) + " (un `lib/main_<flavor>.dart` por flavor)."]
    return "\n".join(out)


def gen_despliegue(ctx):
    if not ctx.has("vercel.json"):
        return ("Sin `vercel.json`: este repositorio no se despliega en Vercel desde aquí. Con infraestructura de un "
                "tercero, el procedimiento está en `tecnico/despliegue.md` de la memoria del proyecto "
                "(`<proyecto>_docs`, privada).")
    try:
        data = json.loads(ctx.read("vercel.json"))
    except ValueError as e:
        raise Unavailable(f"vercel.json ilegible ({e.__class__.__name__})", "Pendiente: `vercel.json` no se pudo leer.")
    out = ["Vercel (`vercel.json`):", ""]
    enabled = (data.get("git") or {}).get("deploymentEnabled")
    if isinstance(enabled, dict):
        on = sorted((b for b, v in enabled.items() if v is True and "*" not in b), key=sort_key)
        closed = enabled.get("**") is False or enabled.get("*") is False
        rest = " (el resto de las ramas no despliega)" if closed else ""
        branches = ", ".join(code(b) for b in on) or "ninguna rama"
        out.append(f"- Despliegan: {branches}{rest} — `git.deploymentEnabled`.")
    elif enabled is False:
        out.append("- Despliegues automáticos desactivados (`git.deploymentEnabled: false`).")
    else:
        out.append("- Sin `git.deploymentEnabled`: Vercel desplegaría todas las ramas (el estándar limita a `main` y "
                   "`develop`).")
    if data.get("framework"):
        out.append(f"- Framework: {code(data['framework'])}.")
    for key, label in (("installCommand", "Instalación"), ("buildCommand", "Build")):
        if data.get(key):
            parts = [p.strip() for p in str(data[key]).split(" && ") if p.strip()]
            if len(parts) == 1:
                out.append(f"- {label}: {code(redact(parts[0]))}.")
            else:
                out.append(f"- {label}, en orden:")
                out += [f"  {i}. {code(redact(p))}" for i, p in enumerate(parts, 1)]
    if data.get("outputDirectory"):
        out.append(f"- Salida: {code(data['outputDirectory'])}.")
    for fn, conf in sorted((data.get("functions") or {}).items()):
        extras = [k for k in ("excludeFiles", "includeFiles", "maxDuration", "memory")
                  if isinstance(conf, dict) and k in conf]
        out.append(f"- Función: {code(fn)}" + (" con " + ", ".join(code(k) for k in extras) if extras else "") + ".")
    if data.get("rewrites"):
        out.append(f"- Reescrituras: {len(data['rewrites'])} (`rewrites`).")
    keys = sorted({h.get("key") for rule in data.get("headers") or [] for h in rule.get("headers") or []
                   if h.get("key")}, key=sort_key)
    if keys:
        out.append("- Cabeceras: " + ", ".join(code(k) for k in keys) + ".")
    return "\n".join(out)


def gen_documentacion(ctx):
    out = []
    rules_file, contributing = ctx.contrib_rules(), ctx.contributing()
    items = [("CHANGELOG.md", "historial de versiones"), ("CLAUDE.md", "guía de desarrollo para personas y agentes"),
             (".claude/CLAUDE.md", "guía de desarrollo para personas y agentes")]
    if rules_file:
        items.append((rules_file, "reglas de contribución"))
    rules = ctx.rglob(".claude/rules", "*.md")
    items += [(ctx.rel(f), "reglas del stack" if f.stem in KINDS + ("docs",) else f"reglas: {f.stem}")
              for f in rules if ctx.rel(f) != rules_file]
    if contributing:
        items.append((contributing, "cómo contribuir (personas y GitHub)"))
    items.append(("AGENTS.md", "punto de entrada para otros agentes"))
    out += [f"- [{p}]({p}) — {d}" for p, d in items if ctx.has(p)]
    # what the docs site really publishes (resumen, backlog, marca, propuesta, prototipo); tecnico/ is never published
    out.append("- Memoria del proyecto `<proyecto>_docs`: producto, backlog, marca y prototipo en su sitio de "
               "documentación (enlace en [Estado](#estado) cuando se publica); infraestructura, despliegue y decisiones "
               "en `tecnico/` (privado).")
    present = {".claude/CLAUDE.md": ctx.has("CLAUDE.md") or ctx.has(".claude/CLAUDE.md"),
               CONTRIB_RULES: bool(rules_file), "CONTRIBUTING.md": bool(contributing), "AGENTS.md": ctx.has("AGENTS.md")}
    work = [name for name, found in present.items() if not found]
    if work:
        ctx.warnings.append("faltan archivos de trabajo: " + ", ".join(work) + " (agent_files.py --write los crea)")
    if not ctx.has("CHANGELOG.md"):
        ctx.warnings.append("falta CHANGELOG.md (changelog.py add --project lo crea con la primera entrada)")
    return "\n".join(out)


def gen_contribucion(ctx):
    # the files that really hold the rules (an equivalent agent_files.py accepts), else where agent_files.py creates them
    rules, people = ctx.contrib_rules() or CONTRIB_RULES, ctx.contributing() or "CONTRIBUTING.md"
    return "\n".join([
        f"Este repositorio sigue el flujo de entrega del equipo. Reglas completas en [{rules}]({rules}) "
        f"(para personas: [{people}]({people})).",
        "",
        "- `main` (producción) y `develop` (integración) están protegidas: nadie sube directo; todo entra por "
        "pull request.",
        "- Se trabaja en `epica/EP-XX-<slug>` (primer flujo) o en `iteracion-N` (iteraciones), ramas creadas desde "
        "`develop`.",
        "- Un commit por historia o item (`US-XX <nombre>` o `TEC <título>`) con el código, sus pruebas, la entrada "
        "del CHANGELOG y este README al día.",
        "- El pull request a `develop` se integra solo con `quality-gate` (pruebas en verde y cobertura ≥ "
        f"{pct(ctx.min_coverage())}) y `security` en verde; los archivos del gate cambian solo como item `TEC` propio.",
        "- ¿Un cambio fuera del flujo? Abre un issue o pide un item: nunca un push directo, un force-push ni secretos "
        "en el repositorio.",
    ])


GENERATORS = {"version": gen_version, "entornos": gen_entornos, "stack": gen_stack, "requisitos": gen_requisitos,
              "puesta-en-marcha": gen_puesta, "variables": gen_variables, "comandos": gen_comandos,
              "pruebas": gen_pruebas, "estructura": gen_estructura, "api": gen_api, "rutas": gen_rutas,
              "pantallas": gen_pantallas, "plataformas": gen_plataformas, "despliegue": gen_despliegue,
              "documentacion": gen_documentacion, "contribucion": gen_contribucion}


def generate_all(ctx, require_routes=False):
    contents = {}
    for bid in BLOCKS[ctx.kind]:
        try:
            contents[bid] = (GENERATORS[bid](ctx).strip("\n"), None)
        except Unavailable as e:
            if bid == "api" and require_routes:
                raise Fatal(f"--require-routes: {e.reason}")
            contents[bid] = (None, e)
    return contents


# ── README operations ─────────────────────────────────────────────────────────────────────────────────────

class Report:
    def __init__(self, mode, kind, readme):
        self.mode, self.kind, self.readme = mode, kind, readme
        self.blocks, self.issues, self.warnings, self.inserted, self.missing_sections = {}, [], [], [], []
        self.version, self.diff, self.written = {}, "", False
        self.into_human = set()


def clean_inner(lines):
    out = [line.rstrip() for line in lines]
    while out and not out[0]:
        out.pop(0)
    while out and not out[-1]:
        out.pop()
    return out


def apply_blocks(doc, contents, rep):
    lines = list(doc.lines)
    for bid, (o, c) in sorted(doc.blocks.items(), key=lambda kv: -kv[1][0]):
        if bid not in contents:
            continue
        text, unavailable = contents[bid]
        old = lines[o + 1:c]
        if text is None:
            if clean_inner(old):
                rep.blocks[bid] = ("sin_verificar", unavailable.reason)
                continue
            text = unavailable.placeholder
            rep.blocks[bid] = ("pendiente", unavailable.reason)
        new = [""] + text.split("\n") + [""]
        if clean_inner(old) != clean_inner(new):
            lines[o + 1:c] = new
            rep.blocks.setdefault(bid, ("cambia", ""))
        else:
            rep.blocks.setdefault(bid, ("ok", ""))
    for bid in BLOCKS[rep.kind]:
        if bid not in doc.blocks:
            rep.blocks[bid] = ("falta", "")
    return "\n".join(lines)


def block_pair(bid):
    return [f"<!-- readme:auto:{bid} -->", f"<!-- /readme:auto:{bid} -->"]


def insert_missing(text, kind, rep):
    for sec in SPEC[kind]:
        for pos, bid in enumerate(sec.blocks):
            doc = Doc(text)
            if bid in doc.blocks:
                continue
            lines, heads = doc.lines, map_sections(doc, kind)
            before = [b for b in sec.blocks[:pos] if b in doc.blocks]
            after = [b for b in sec.blocks[pos + 1:] if b in doc.blocks]
            if before:
                at = doc.blocks[before[-1]][1] + 1
                lines[at:at] = [""] + block_pair(bid)
                where = f"«{sec.title}», después de «{before[-1]}»"
            elif after:
                at = doc.blocks[after[0]][0]
                lines[at:at] = block_pair(bid) + [""]
                where = f"«{sec.title}», antes de «{after[0]}»"
            elif sec.key in heads:
                idx, _lvl, title = heads[sec.key]
                ins = [""] + block_pair(bid)
                if idx + 1 < len(lines) and lines[idx + 1].strip():
                    ins.append("")
                lines[idx + 1:idx + 1] = ins
                where = f"«{title}» (al inicio de la sección)"
                rep.into_human.add(sec.key)
            else:
                at = new_section_position(doc, kind, sec, heads)
                if at is None:
                    lines, where = into_reference(doc, sec, bid), "«Referencia generada»"
                else:
                    pre = [""] if at > 0 and lines[at - 1].strip() else []
                    lines[at:at] = pre + [f"## {sec.title}", ""] + block_pair(bid) + [""]
                    where = f"nueva sección «{sec.title}»"
            text = "\n".join(lines)
            rep.inserted.append(f"{bid} → {where}")
    return text


def new_section_position(doc, kind, sec, heads):
    order = [s.key for s in SPEC[kind]]
    i = order.index(sec.key)
    anchors = {k: v for k, v in heads.items() if v[1] == 2}
    # after every section that comes earlier in the template, wherever the README put them
    ends = [doc.section_end(anchors[k][0], 2) for k in order[:i] if k in anchors]
    if ends:
        return max(ends)
    for key in order[i + 1:]:
        if key in anchors:
            return anchors[key][0]
    return None


def into_reference(doc, sec, bid):
    lines = doc.lines
    ref = next(((i, lvl) for i, lvl, t in doc.headings if norm(t) == "referencia generada"), None)
    if ref is None:
        while lines and not lines[-1].strip():
            lines.pop()
        lines += ["", "## Referencia generada", "",
                  "<!-- Bloques de readme_sync.py sin sección propia en este README: muévelos a su sección cuando "
                  "se reorganice (readme-format.md). -->", ""]
        end = len(lines)
    else:
        end = doc.section_end(*ref)
    pre = [""] if end > 0 and lines[end - 1].strip() else []
    lines[end:end] = pre + [f"### {sec.title}", ""] + block_pair(bid) + [""]
    return lines


def inspect(doc, ctx, rep, as_issue):
    """Sections, version, contribution text and leaked values; issues in --check, warnings otherwise. Generic
    contribution text is a warning in every mode: removing human text needs the user's yes (compliance DOC-RM04)."""
    add = rep.issues.append if as_issue else rep.warnings.append
    if not any(level == 1 for _i, level, _t in doc.headings):
        add("falta el título `# <Producto> — <Tipo>`")
    heads = map_sections(doc, rep.kind)
    for sec in SPEC[rep.kind]:
        if sec.key not in heads and not any(b in doc.blocks for b in sec.blocks):
            rep.missing_sections.append(sec.title)
            add(f"falta la sección «{sec.title}»")
    for bid in doc.blocks:
        if bid not in BLOCKS[rep.kind]:
            rep.warnings.append(f"bloque «{bid}» ajeno al tipo {rep.kind}: se deja igual")
    if "version" in doc.blocks and ctx.manifest is None:  # --init before the scaffold: nothing to compare yet
        rep.version = {"readme": None, "manifiesto": None, "fuente": MANIFESTS[ctx.kind]}
    elif "version" in doc.blocks:
        o, c = doc.blocks["version"]
        m = VERSION_IN_BLOCK.search("\n".join(doc.lines[o + 1:c]))
        rep.version = {"readme": m.group(1) if m else None, "manifiesto": ctx.m["version"], "fuente": ctx.m["source"]}
        if not m or m.group(1) != ctx.m["version"]:
            add(f"versión del README {m.group(1) if m else '(sin versión)'} ≠ {ctx.m['source']} {ctx.m['version']}")
    fenced = doc.fenced_lines()
    human = [(i, line) for i, line in enumerate(doc.lines) if not doc.generated(i)]
    if any(generic_contrib(line) for _i, line in human):
        rep.warnings.append("texto de contribución genérico («Fork el proyecto», feature/AmazingFeature): el flujo "
                            "real está en el bloque contribucion y en .claude/rules/contribucion.md; bórralo (con "
                            "aprobación)")
    text = "\n".join(line for _i, line in human)
    for (rel, name), value in sorted(ctx.real_env_values().items()):
        if value in text:
            add(f"el README contiene el valor de {name} de {rel}: bórralo (y rota el secreto si es real)")
    hints, seen = [], set()
    for i, line in human:
        title = (doc.heading_before(i) or (0, 0, "descripción"))[2]
        if HINT.search(line) and title not in seen:
            seen.add(title)
            hints.append(title)
    if hints:
        rep.warnings.append("por completar (<!-- COMPLETA -->): " + ", ".join(f"«{t}»" for t in hints))
    hex_lines = [i for i, line in human if HEX_COLOR.search(line)]
    if hex_lines:
        rep.warnings.append(f"colores en hex en el README (línea {hex_lines[0] + 1}): enlaza el sitio de marca, los "
                            "valores viven en los tokens")
    assigned = sorted({ASSIGNMENT.match(line).group(1) for i, line in human if i in fenced and ASSIGNMENT.match(line)})
    if assigned:
        rep.warnings.append("el README muestra valores de variables (" + ", ".join(assigned[:6])
                            + ("…" if len(assigned) > 6 else "") + "): documenta solo los nombres (bloque variables)")


def human_text_in_block_sections(doc, kind, keys):
    out, heads = [], map_sections(doc, kind)
    for sec in SPEC[kind]:
        if sec.key not in keys or sec.key not in heads:
            continue
        idx, level, title = heads[sec.key]
        end = doc.section_end(idx, level)
        extra = [i for i in range(idx + 1, end)
                 if doc.lines[i].strip() and not doc.generated(i) and not HINT.search(doc.lines[i])]
        if extra:
            out.append(f"revisa «{title}»: tiene texto previo junto al bloque generado (no se borró; quita lo "
                       "duplicado u obsoleto con aprobación)")
    return out


def find_readme(root):
    exact = root / "README.md"
    if exact.exists():
        return exact
    return next((p for p in sorted(root.iterdir(), key=lambda x: x.name)
                 if p.is_file() and p.name.lower() == "readme.md"), None)


def run(a):
    root = Path(a.repo)
    if not root.is_dir():
        raise Fatal(f"--repo {a.repo}: no es una carpeta")
    mode = next(m for m in ("write", "check", "init", "adopt") if getattr(a, m))
    ctx = Ctx(root, a.kind, a.docs, a.routes_cmd if a.kind == "backend" else None, before_scaffold=mode == "init")
    readme = find_readme(root)
    rep = Report(mode, a.kind, readme.name if readme else "README.md")
    if a.routes_cmd and a.kind != "backend":
        rep.warnings.append("--routes-cmd solo aplica al backend: se ignora")
    if mode == "check" and readme is None:
        rep.issues.append("no existe README.md (python3 <git-deploy-ops>/scripts/readme_sync.py --init)")
        return finish(a, rep, 1)
    if mode == "init":
        if readme is not None:
            raise Fatal(f"{readme.name} ya existe: usa --adopt (conserva el texto) o --write")
        tpl = Path(a.template) if a.template else SKILL_TEMPLATES / f"README.{a.kind}.md"
        if not tpl.exists():
            raise Fatal(f"plantilla no encontrada: {tpl} (corre --init desde git-deploy-ops o pasa --template)")
        man = ctx.manifest or {}
        producto = (ctx.project or {}).get("producto") or man.get("name") or root.resolve().name
        desc = (ctx.project or {}).get("descripcion") or man.get("description")
        if ctx.manifest is None:
            rep.warnings.append(f"sin {MANIFESTS[a.kind]} todavía: sus bloques quedan «Pendiente» hasta el commit del "
                                "scaffold, que corre --write")
        current = read_file(tpl)[0].replace("{{producto}}", str(producto)).replace(
            "{{descripcion}}", desc or "<!-- COMPLETA: una línea: qué hace el producto y para quién "
                                       "(estado/proyecto.json → descripcion). -->")
        original, raw, bom = "", "", False
    else:
        if readme is None:
            raise Fatal("no existe README.md: usa --init")
        original, raw, bom = read_file(readme)
        current = original
    doc = Doc(current)
    if doc.errors:
        raise Fatal("marcas readme:auto mal formadas en " + rep.readme + ": " + "; ".join(doc.errors))
    contents = generate_all(ctx, a.require_routes)
    if mode == "adopt":
        current = insert_missing(current, a.kind, rep)
        doc = Doc(current)
    new = apply_blocks(doc, contents, rep)
    if mode in ("init", "adopt") or not new.strip():
        new = new.rstrip("\n") + "\n"
    rep.warnings += [w for w in ctx.warnings if w not in rep.warnings]
    rep.blocks = {b: rep.blocks[b] for b in sorted(rep.blocks, key=BLOCKS[a.kind].index)}
    for bid, (status, note) in rep.blocks.items():
        if status == "sin_verificar" and bid != "entornos":
            rep.warnings.append(f"bloque «{bid}» sin verificar: {note}")
    if mode == "check":
        inspect(doc, ctx, rep, as_issue=True)
        stale = [b for b, (s, _n) in rep.blocks.items() if s in ("cambia", "pendiente")]
        missing = [b for b, (s, _n) in rep.blocks.items() if s == "falta"]
        if stale:
            rep.issues.append("bloques desactualizados: " + ", ".join(stale))
        if missing:
            rep.issues.append("faltan bloques: " + ", ".join(missing) + " (usa --adopt)")
    else:
        inspect(Doc(new), ctx, rep, as_issue=False)
        if mode == "adopt":
            rep.warnings += human_text_in_block_sections(Doc(new), a.kind, rep.into_human)
        missing = [b for b, (s, _n) in rep.blocks.items() if s == "falta"]
        if missing:
            rep.issues.append("faltan bloques: " + ", ".join(missing) + " (usa --adopt)")
    target = f"{rep.readme} (readme_sync --{'write' if mode == 'check' else mode})"
    rep.diff = "".join(difflib.unified_diff(original.splitlines(keepends=True) if original else [],
                                            new.splitlines(keepends=True), fromfile=rep.readme, tofile=target))
    if mode == "check":
        return finish(a, rep, 1 if rep.issues else 0)
    changed = new != original
    if a.dry_run:
        return finish(a, rep, 1 if changed or rep.issues or rep.missing_sections else 0)
    if changed:
        write_file(root / rep.readme, new, raw, bom)
        rep.written = True
    return finish(a, rep, 1 if rep.issues else 0)


def finish(a, rep, code_):
    if a.json:
        print(json.dumps({"modo": rep.mode, "tipo": rep.kind, "readme": rep.readme,
                          "bloques": {b: {"estado": s, "nota": n} for b, (s, n) in rep.blocks.items()},
                          "problemas": rep.issues, "avisos": rep.warnings, "insertados": rep.inserted,
                          "secciones_faltantes": rep.missing_sections, "version": rep.version,
                          "escrito": rep.written, "diff": rep.diff, "exit": code_}, ensure_ascii=False, indent=2))
        return code_
    label = {"ok": "ok", "cambia": "desactualizado" if rep.mode == "check" else "actualizado",
             "sin_verificar": "sin verificar", "pendiente": "pendiente", "falta": "FALTA"}
    print(f"readme_sync --{rep.mode} · {rep.kind} · {rep.readme}")
    for status in ("ok", "cambia", "pendiente", "sin_verificar", "falta"):
        ids = [b for b, (s, _n) in rep.blocks.items() if s == status]
        if ids:
            print(f"  {label[status]:<15} " + ", ".join(sorted(ids, key=BLOCKS[rep.kind].index)))
    for line in rep.inserted:
        print(f"  insertado       {line}")
    for line in rep.issues:
        print(f"  PROBLEMA        {line}")
    for line in rep.warnings:
        print(f"  AVISO           {line}")
    if rep.mode == "check":
        print("README sincronizado" if code_ == 0 else
              f"README desactualizado: {len(rep.issues)} problema(s) → python3 scripts/readme_sync.py --write "
              f"--kind {rep.kind} [--docs <memoria>] (bloques) o --adopt (bloques que faltan); las secciones curadas "
              "se escriben a mano")
    elif a.dry_run:
        print("simulación: no se escribió nada")
    else:
        print(f"{rep.readme} {'escrito' if rep.written else 'sin cambios'}")
    if rep.diff and (rep.mode == "check" or a.dry_run):
        print(rep.diff, end="" if rep.diff.endswith("\n") else "\n")
    return code_


def main(argv=None):
    ap = argparse.ArgumentParser(description="README.md sincronizado con sus fuentes (formato de la casa)")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="regenera los bloques readme:auto")
    mode.add_argument("--check", action="store_true", help="exit 1 si el README no está sincronizado (CI)")
    mode.add_argument("--init", action="store_true", help="crea README.md desde la plantilla del tipo")
    mode.add_argument("--adopt", action="store_true", help="README existente: inserta los bloques sin borrar texto")
    ap.add_argument("--kind", required=True, choices=KINDS)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--docs", help="memoria del proyecto (<proyecto>_docs): estado/proyecto.json")
    ap.add_argument("--routes-cmd", help="comando que imprime la tabla de rutas de la API (backend)")
    ap.add_argument("--require-routes", action="store_true", help="exit 2 si la tabla de la API no se puede generar")
    ap.add_argument("--template", help="plantilla para --init (default: assets/readme/README.<kind>.md del skill)")
    ap.add_argument("--dry-run", action="store_true", help="no escribe: muestra el reporte y el diff")
    ap.add_argument("--json", action="store_true", help="reporte en JSON")
    a = ap.parse_args(argv)
    try:
        return run(a)
    except Fatal as e:
        if a.json:
            print(json.dumps({"modo": next(m for m in ("write", "check", "init", "adopt") if getattr(a, m)),
                              "tipo": a.kind, "error": str(e), "exit": 2}, ensure_ascii=False, indent=2))
        else:
            print(f"readme_sync: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
