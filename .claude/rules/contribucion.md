<!--
Plantilla de git-deploy-ops (assets/agents/rules/contribucion.md), instalada como .claude/rules/contribucion.md.
Sin frontmatter paths: Claude Code la carga siempre. Es la fuente única de las reglas de contribución: CONTRIBUTING.md
(raíz, para GitHub) solo apunta aquí. Los bloques de código o de docs los resuelve agent_files.py por tipo de repo.
Resume references/git-conventions.md y versioning-release.md de git-deploy-ops: si cambian, actualiza esta plantilla.
-->
# Reglas de contribución — Itzaka (backend)

Cómo entra un cambio a este repositorio, para personas y agentes. Es la única fuente: `CONTRIBUTING.md` apunta aquí.

## Ramas

- `main` = producción y `develop` = integración: protegidas, nadie hace commit ni push directo.
- Se trabaja solo en `epica/EP-XX-<slug>` (primer flujo, una por épica) o en `iteracion-N` (una por iteración), creadas desde `develop` al día. No hay otras ramas de trabajo.
- `develop` llega a `main` solo con el pull request de promoción `Versión X.Y.Z`, después de GATE PRODUCCIÓN.

## Commits

- Uno por US (primer flujo) o por item (iteración). Asunto: `US-03 Registro con correo y OTP`; varias US: `US-03 Registro con correo y OTP · US-07 Perfil de usuario` (solo ids si pasa de ~72 caracteres); item sin US: `TEC <título del item>`; especiales: `Scaffold de plataforma` y `Versión X.Y.Z`.
- Sin prefijos `feat:` ni `fix:`: el tipo va en el cuerpo (`Tipo: bug | cambio | nueva`, `Épica: EP-01` o `Item: iteracion-N #K`, `Refs: US-03`).
- Cada commit lleva junto: el código, sus pruebas en verde (escritas primero en rojo), su entrada en el bloque `[Unreleased]` de `CHANGELOG.md` y el README al día (bloques con `python3 scripts/readme_sync.py --write --kind backend`, más la sección curada que cambió).
- `Versión X.Y.Z` es el último commit de la rama antes de su pull request: manifiestos, CHANGELOG y README, con `readme_sync.py --check` en verde.
- Stage preciso (`git add <rutas>`); nunca `.env`, llaves ni cadenas de conexión reales: `.env.example` lleva solo nombres.
- Nada de commits vacíos o especulativos, ni de un US o item que no esté en verde.

## Pull requests

- A `develop`: uno por épica (título y merge commit `EP-01 Autenticación`) o por iteración (`iteracion-N`), con merge commit; nunca squash ni rebase.
- Antes de abrirlo, en la rama: la suite con cobertura y `python3 scripts/test_gate.py` (todas las pruebas pasan y la cobertura llega al mínimo del proyecto, 90 % por defecto), `python3 scripts/readme_sync.py --check --kind backend` y `python3 scripts/gate_guard.py --base origin/develop`.
- Se fusiona solo con `quality-gate` y `security` en verde; si CI falla, se corrige en la misma rama con un commit nuevo.
- Cuerpo: los US o items (id + nombre), la línea del quality gate local, la línea `README sincronizado`, la revisión de compliance, el bloque del CHANGELOG y, si la hubo, la aprobación citada de un cambio de gate o de un archivo de trabajo sobrescrito.

## Archivos de gate

Los workflows de `.github/`, `dependabot.yml`, `CODEOWNERS`, los scripts del gate (`scripts/test_gate.py`, `security_audit.py`, `gate_guard.py`, `readme_sync.py`), `.security-exceptions`, `.gitleaksignore`, la configuración de cobertura y de pruebas, las pruebas base de plataforma y los `headers` de `vercel.json`. Un cambio a ellos es su propio item `TEC` (con él viajan solo su entrada del CHANGELOG y el README regenerado), aprobado por una persona en el chat y nunca dentro de un US; `gate_guard.py` lo detecta.

## Prohibido

- Push directo a una rama protegida, `--force`, reescribir historia publicada, `--amend` de commits empujados, borrar ramas protegidas.
- Fusionar con pruebas en rojo, cobertura bajo el mínimo o `security` en rojo.
- Fusionar un pull request de Dependabot tal cual: cada uno se vuelve el item `TEC Actualiza <paquete> a <versión>` de la siguiente iteración.
- Commitear secretos. Si se filtró uno, primero se rota (lo hace una persona); la historia no se reescribe.
- Sobrescribir o descartar trabajo de otra persona.

## Proponer un cambio fuera del flujo

¿No estás dentro de una épica o iteración abierta? No hagas push ni abras un pull request por tu cuenta: abre un issue (o avisa al responsable del proyecto) con qué cambiar, por qué y el comportamiento esperado. Se clasifica como item (`bug`, `cambio` o `nueva`) de la siguiente iteración y entra por `iteracion-N`. Un agente que encuentra algo fuera de su alcance lo reporta; no lo corrige de paso.
