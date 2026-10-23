<!--
Plantilla de git-deploy-ops (assets/agents/CLAUDE.md). scripts/agent_files.py la instala como .claude/CLAUDE.md solo
cuando el repo no tiene CLAUDE.md ni .claude/CLAUDE.md, y nunca la reemplaza sin un --overwrite explícito por archivo.
Notas para mantenedores solo en comentarios HTML: Claude Code los quita antes de cargar el archivo.
Menos de 200 líneas, concreta y verificable; lo de un stack va en .claude/rules/<stack>.md (con paths:).
Es contexto, no un control: las garantías duras viven en CI (quality-gate, security, README sincronizado, gate_guard).
Los bloques marcados para repos de código o para el repo de documentación los resuelve agent_files.py por tipo de repo.
-->
# Guía de desarrollo para agentes — CUOTREKA (backend)

Reglas universales de comportamiento e ingeniería para cualquier persona o agente que toque este repositorio, independientes del stack. Las reglas del stack (estructura, nombres, patrones, comandos) y el flujo de contribución viven en `.claude/rules/`; en lo que es propio de su stack, esas mandan.

Compromiso: esta guía prioriza la cautela sobre la velocidad. En tareas triviales (un typo, renombrar una variable local) usa el criterio: no hace falta plan ni preguntas.

## 1. Prioridad cuando las reglas chocan

1. Seguridad, privacidad y requisitos legales.
2. Requisitos explícitos y decisiones confirmadas por una persona.
3. Correctitud, integridad de datos y compatibilidad.
4. Convenciones y arquitectura del proyecto (`.claude/rules/`, linter, formateador).
5. Legibilidad, mantenibilidad y simplicidad.
6. Rendimiento, solo si está medido o es un requisito.
7. Preferencias de estilo.

Si dos instrucciones se contradicen, no elijas en silencio: nombra el conflicto y pregunta.

## 2. Antes de cambiar nada

No asumas. No escondas la confusión. Expón las alternativas.

- Lee esta guía, `.claude/rules/`, el README y el código relacionado; sigue sus convenciones salvo que haya una razón justificada para proponer otra.
- Ubica el US o item que pide el cambio (`US-03`, `iteracion-N #K`) y sus criterios: escenarios Gherkin y criterios de seguridad (`SEC-02`, `VAL-01`…) del backlog en la memoria `cuotreka_docs`. Sin US ni item no hay cambio (reglas de contribución).
- Antes de modificar una solución existente, identifica qué problema resuelve y por qué está así (pruebas, historial, decisiones registradas). No la reemplaces por preferencia personal.
- No asumas que un archivo, función, dependencia, comando o variable existe: compruébalo.
- Identifica la fuente de verdad de cada dato o configuración; no crees otra que pueda divergir.
- Evalúa el impacto en interfaces públicas, contratos de API, modelos, migraciones, integraciones y consumidores.
- Declara tus suposiciones. Si hay varias interpretaciones con resultados distintos, preséntalas.
- Si existe un enfoque más simple que el pedido, dilo. Contradice cuando haya motivo.
- Pregunta antes de decidir sobre arquitectura, datos, seguridad, alcance, UX o costos. Si algo no está claro, detente, nombra qué te confunde y pregunta.
- Define el cambio mínimo correcto y cómo lo vas a verificar.

## 3. Simplicidad primero

El mínimo código que resuelve el problema. Nada especulativo.

- Nada de funcionalidades, configurabilidad o "flexibilidad" que no se pidió.
- Nada de abstracciones para código de un solo uso ni para necesidades hipotéticas.
- No dupliques reglas de negocio, pero no fuerces una abstracción común si el parecido es superficial.
- Maneja los errores que pueden ocurrir; no inventes manejo para escenarios imposibles ni conviertas un error en un resultado "válido".
- Legible antes que ingenioso. Breve no es lo mismo que simple.
- No optimices sin un cuello de botella medido o un requisito explícito.
- La prueba: ¿un ingeniero senior diría que esto está sobrecomplicado? Si sí, simplifica.

## 4. Cambios quirúrgicos

Toca solo lo necesario. Limpia solo tu propio desorden.

- No "mejores" código, comentarios o formato adyacentes. No refactorices lo que no está roto.
- Imita el estilo existente aunque tú lo harías distinto.
- Código muerto que no es tuyo: menciónalo, no lo borres.
- Sí elimina imports, variables o funciones que TUS cambios dejaron sin uso.
- Conserva el comportamiento existente salvo que cambiarlo sea un requisito confirmado.
- Si un refactor es necesario, sepáralo del cambio funcional (es su propio item).
- NUNCA sobrescribas ni descartes trabajo de otras personas: cambios sin commitear, ramas o archivos que no hiciste.
- La prueba: cada línea modificada se rastrea directamente al US o item.

## 5. TDD y ejecución guiada por objetivos

Define criterios de éxito. Itera hasta verificarlos.

- Primero una prueba que falla por la razón correcta (RED); después el mínimo código de producción que la pone en verde (GREEN); al final, limpieza con todo en verde. Sin prueba en rojo no hay código de producción.
- Cada escenario Gherkin del US da al menos una prueba; cada criterio de seguridad del US, sus pruebas negativas con el id en el docstring (`"""SEC-02 · US-07"""`): así cuentan como evidencia y quedan protegidas.
- "Agrega validación" → pruebas para entradas inválidas, luego hazlas pasar. "Corrige el bug" → una prueba que lo reproduzca, luego hazla pasar. "Refactoriza X" → las mismas pruebas pasan antes y después.
- En tareas de varios pasos, declara un plan breve:

  ```
  1. [Paso] → verificar: [comprobación]
  2. [Paso] → verificar: [comprobación]
  ```

- Elige prueba unitaria, de integración o E2E según el alcance y el riesgo. Cubre el caso normal, los límites y los errores relevantes; agrega regresión para cada bug.
- NUNCA debilites, saltes ni borres una prueba para que pase (`skip`, `xfail`, `.only`, `--deselect`, exclusiones de cobertura). Si está obsoleta, explica por qué y corrígela.
- Revisar el código a ojo no es verificarlo.

## 6. Comunicación y honestidad

- Responde en el idioma de la persona, claro y directo; explica un tecnicismo solo si importa.
- No inventes hechos, requisitos, archivos, resultados de pruebas ni capacidades.
- Distingue siempre lo comprobado, lo supuesto y lo propuesto.
- NUNCA afirmes haber ejecutado pruebas, builds, migraciones, merges o despliegues que no ejecutaste o no confirmaste.
- Si algo falla o te bloquea, repórtalo con su consecuencia; no lo maquilles.
- Una suite en verde no garantiza ausencia de defectos: dilo cuando importe.

## 7. Entradas, permisos y seguridad

- Valida en los límites de confianza; las validaciones críticas van en el servidor.
- Verifica autorización en cada operación protegida, por registro y entre usuarios u organizaciones.
- NUNCA confíes en IDs, precios, roles o propietarios enviados por el cliente.
- Devuelve solo los datos que el contrato requiere. Minimiza la recolección de datos personales.
- Usa consultas parametrizadas u ORM; previene inyección, XSS, CSRF y manipulación de campos.
- Archivos recibidos: valida tipo real, tamaño, extensión y contenido.
- Considera entradas vacías, malformadas, duplicadas y fuera de rango; y concurrencia, reintentos e idempotencia cuando aplique.
- NUNCA pongas secretos en código, logs, commits, pruebas ni documentación. No leas ni copies valores de `.env`: los nombres van en `.env.example`, sin valores.
- Errores para el usuario sin trazas ni detalles internos; logs con contexto suficiente y sin datos sensibles.
- NUNCA desactives un control de seguridad para que una prueba o implementación funcione.

<!--
Opcional para el equipo (no se instala): .claude/settings.json con
"permissions": {"deny": ["Read(./.env)", "Read(./**/.env)"]}. No uses "Read(./.env.*)": bloquearía también .env.example.
-->

## 8. Datos y migraciones

- Genera migraciones con el mecanismo del framework y revísalas.
- NUNCA edites migraciones ya aplicadas ni el estado de migraciones para ocultar inconsistencias.
- Evalúa el impacto en datos existentes y en versiones desplegadas; evita cambios de esquema incompatibles con versiones que siguen en uso.
- Antes de una operación con posible pérdida de datos, identifica el respaldo y la forma de recuperación.
- Tras cambiar modelos o relaciones, verifica que los permisos y restricciones de acceso se mantienen.

## 9. Dependencias

- Antes de añadir una, verifica si lo existente ya lo resuelve; evalúa necesidad, mantenimiento, licencia, seguridad, compatibilidad, tamaño y costo. Solo de la lista permitida del stack; otra se propone y espera el sí.
- No actualices por actualizar: cada actualización es su propio item (`TEC Actualiza <paquete> a <versión>`); los pull requests de Dependabot no se fusionan tal cual.
- El lockfile cambia en el mismo commit que el manifiesto y se instala en modo estricto (comandos en `.claude/rules/`).

## 10. Git y entrega

El detalle (ramas, asuntos, pull requests, archivos de gate) está en `.claude/rules/contribucion.md`. Lo mínimo:

- `main` y `develop` están protegidas: nunca commit ni push directo; todo entra por pull request desde `epica/EP-XX-<slug>` o `iteracion-N`.
- Un commit por US o item con su código, sus pruebas en verde, su entrada de `CHANGELOG.md` y el README actualizado, juntos.
- Un pull request se fusiona solo con el quality gate en verde (todas las pruebas pasan y la cobertura de líneas llega al mínimo del proyecto: 90 % o `cobertura_minima`, si es mayor) y el check `security` en verde.
- Stage preciso (`git add <rutas>`, nunca `git add -A` a ciegas) y revisa `git diff --staged` antes de cada commit.
- Ante un conflicto, entiende ambas partes antes de resolverlo; no descartes la otra.
- No afirmes integrado, publicado o desplegado sin verificarlo (estado del pull request y de sus checks).

## 11. Acciones que requieren un "sí" explícito de una persona

- Borrar tablas, columnas o datos; correr migraciones destructivas; tocar entornos compartidos o producción.
- Operaciones destructivas de Git: `reset --hard`, `push --force`, reescribir historia, borrar ramas, `clean` o `checkout --` sobre cambios ajenos.
- Commits, merges, publicaciones o despliegues que el flujo del proyecto no autorice ya.
- Editar `.env`, secretos, lockfiles o configuración de CI/CD; tocar un archivo de gate (workflows, scripts del gate, configuración de cobertura, pruebas base), que además viaja como su propio item `TEC`.
- Agregar o actualizar dependencias.
- Cambiar alcance, experiencia de usuario, costos o comportamiento visible del producto.
- Cambiar esta guía o las reglas de `.claude/rules/`.

## 12. Estilo y documentación

- La fuente de verdad del estilo es el formateador, linter, tipado y reglas del stack. Úsalos.
- Esta guía NO impone longitud de línea, indentación, prefijos de booleanos, orden de miembros ni límite de líneas por función: eso lo define cada stack.
- Nombres que expresen intención; sin abreviaturas ambiguas; unidades explícitas si hay ambigüedad.
- Constantes con nombre para reglas de negocio y configuración; no números ni cadenas mágicas.
- Documenta lo que no es evidente desde el código y las decisiones técnicas con sus alternativas.
- Si cambia la instalación, configuración, ejecución o uso, actualiza la documentación en el mismo commit (en código, el README; en la memoria, el documento dueño).
- README: los bloques `<!-- readme:auto:… -->` los regenera su script, nunca a mano; las secciones curadas se actualizan en el mismo commit cuando cambia lo que describen (comandos, variables, dependencias, módulos, rutas, integraciones, despliegue).
- NUNCA inventes comandos, variables de entorno ni procedimientos en la documentación; indica si un procedimiento no fue verificado.
- La versión del producto la calcula el flujo (commit `Versión X.Y.Z`); no la cambies a mano en manifiestos ni en el CHANGELOG.

## 13. Antes de entregar

1. Revisa el diff completo: sin cambios accidentales, secretos, datos reales, artefactos ni archivos sobrantes.
2. Lee `.claude/rules/backend.md` aunque no hayas abierto un archivo de sus `paths:`, corre las verificaciones que piden `.claude/rules/` (en código: pruebas con cobertura y quality gate, linter, tipos, build, README sincronizado) y registra el resultado real.
3. Confirma los criterios de éxito del inicio y los escenarios del US o item.

Lista de revisión: cumple los requisitos confirmados · respeta reglas y arquitectura · dentro del alcance · nombres y estructuras comprensibles · sin duplicaciones ni abstracciones innecesarias · entradas y permisos validados · datos, secretos y límites de acceso protegidos · errores, límites, reintentos y concurrencia considerados · pruebas incluidas o actualizadas · migraciones y contratos compatibles o justificados · documentación al día (CHANGELOG y README, o registros y sitio) · riesgos y pendientes comunicados.

Reporta con esta estructura:

- **Qué cambió:** archivos y motivo.
- **Qué se verificó:** comando y resultado.
- **Qué no se verificó:** y por qué.
- **Riesgos y pendientes:** incluidas las decisiones que necesitan a una persona.

Señales de que la guía funciona: diffs sin cambios innecesarios, menos reescrituras por sobrecomplicación y preguntas de aclaración antes de implementar, no después de un error.

**Principio final.** El objetivo no es escribir la menor cantidad de código ni aplicar reglas mecánicamente, sino entregar software correcto, seguro, comprensible, verificable y mantenible por la siguiente persona que trabaje en él.
