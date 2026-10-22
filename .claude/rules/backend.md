---
paths:
  - "src/**/*.py"
  - "pyproject.toml"
  - "uv.lock"
  - "src/**/*.html"
  - ".env.example"
  - "src/core/.env.example"
  - "vercel.json"
  - "Makefile"
---
<!--
Plantilla de git-deploy-ops (assets/agents/rules/backend.md) → .claude/rules/backend.md. Claude Code la carga al leer
o editar un archivo de paths:. Corta a propósito: comandos reales (los del quality gate) y lo no negociable; el detalle
vive en la skill django-backend-conventions. test_agent_files.py compara los comandos con assets/quality-gate-backend.yml.
-->
# Backend — Django + DRF (uv)

Detalle y recetas: skill `django-backend-conventions`; pruebas: `qa-tdd-testing`. Si algo de aquí choca con ellas, mandan ellas.

## Comandos

- Entorno: `uv sync --locked --all-groups`. Dependencia nueva (de la lista permitida y con el sí de una persona): `uv add <paquete>`; herramientas de desarrollo y pruebas: `uv add --group dev <paquete>`.
- Formato y lint: `uv run ruff format .` y `uv run ruff check .` (nunca black ni isort).
- Pruebas como el quality gate: `uv run pytest --junitxml=reports/junit.xml --cov --cov-report=xml:reports/coverage.xml`, luego `python3 scripts/test_gate.py --junit reports/junit.xml --cobertura reports/coverage.xml --min 0.90 --allow-skip-reason 'got empty parameter set'` (`--min` = el `MIN_COVERAGE` del workflow si es mayor).
- Migraciones: `uv run python src/manage.py makemigrations` y revísalas antes de commitear; `migrate` solo contra tu base local.
- README: `python3 scripts/readme_sync.py --write --kind backend` en cada commit que cambie comandos, variables, dependencias, apps o endpoints; `--check` antes del pull request.

## No negociables

- Capas view → serializer → service → model: la lógica de negocio solo en `services.py` (`@transaction.atomic`), las lecturas complejas en `selectors.py`; las vistas solo orquestan.
- Todo modelo de `apps/` registrado con un `ModelAdmin` de Unfold; estáticos con WhiteNoise (`collectstatic` nunca en el build de Vercel).
- `get_queryset` siempre acotado al usuario o la empresa (registro ajeno → 404); serializers con campos explícitos (nunca `"__all__"` ni `exclude`) y `read_only_fields` para dueño, empresa, rol, estado y montos.
- Contrato de API: listas paginadas (20, máx. 100) con `filterset_class`, `search_fields` y `ordering_fields` explícitos; errores con la forma de DRF vía `api_exception_handler`; un endpoint publicado conserva sus parámetros y formas.
- Sesión web con JWT en cookies HttpOnly + CSRF (nunca tokens en el cuerpo); no hay app móvil (sin rutas `/api/auth/mobile/`).
- Código en inglés (endpoints incluidos) y `verbose_name` localizado; imports desde `apps.`, `common.`, `core.` o `api.`, nunca `src.`; sin `print()` (logger `apps`); configuración con `django-environ` (`DATABASE_URL`), sin secretos en el código.
