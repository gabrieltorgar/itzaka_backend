<!--
Plantilla de git-deploy-ops (assets/agents/AGENTS.md): puntero en la raíz para los agentes que leen AGENTS.md (Codex,
Cursor, Copilot, Gemini y otros). Claude Code no lo lee cuando existe CLAUDE.md o .claude/CLAUDE.md, así que nada se
carga dos veces. No copies reglas aquí: cambia la fuente.
-->
# Instrucciones para agentes — Itzaka (backend)

Las reglas de este repositorio viven en un solo lugar. Léelas antes de cambiar algo y síguelas:

1. [`.claude/CLAUDE.md`](.claude/CLAUDE.md) — guía de desarrollo: prioridades, protocolo antes y durante el cambio, TDD, seguridad, Git y entrega.
2. [`.claude/rules/contribucion.md`](.claude/rules/contribucion.md) — ramas, commits, pull requests y quality gate.
3. [`.claude/rules/backend.md`](.claude/rules/backend.md) — comandos reales y reglas no negociables del stack.

Los archivos de `.claude/rules/` con `paths:` en su encabezado aplican a los archivos que coinciden con esos patrones; los que no lo tienen, a todo el repositorio. En lo propio de su stack, esas reglas mandan sobre la guía.
