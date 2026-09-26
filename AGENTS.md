# AGENTS.md — flujo multi-agente de HomeAI

Este proyecto usa Claude Code con un **coordinador** y **5 especialistas** definidos
en `.claude/agents/*.md`. El objetivo es que cada tarea consuma solo el contexto que
necesita, en vez de que cada cambio dispare una relectura completa del repositorio.

## Roles

| Agente | Archivo | Se ocupa de |
|---|---|---|
| Coordinador | `.claude/agents/coordinator.md` | Decide qué especialistas hacen falta, reparte contexto, integra, evita duplicar trabajo |
| Architect | `.claude/agents/architect.md` | Arquitectura JS/CSS, el scope global compartido entre los 11 `<script>`, deuda técnica, cuándo merece la pena una migración |
| UX/UI | `.claude/agents/ux-ui.md` | Diseño visual, responsive, accesibilidad, estados vacíos/carga/error, consistencia entre las 9 hojas de estilo |
| AI Engineer | `.claude/agents/ai-engineer.md` | OCR (Tesseract), detección de muros, maqueta 3D conceptual, y cualquier función generativa/IA nueva |
| QA | `.claude/agents/qa.md` | Tests existentes, regresiones visuales con Playwright, navegadores/tamaños, validación antes de aceptar un cambio |
| Security | `.claude/agents/security.md` | Secretos/API keys, XSS, dependencias, privacidad (todo el proyecto es cliente-solo, sin backend propio) |

## Reglas del flujo

El coordinador debe, en este orden:

1. Leer `AGENTS.md` (este archivo), `PROJECT.md` y `CURRENT_STATE.md` antes de decidir nada.
2. Determinar qué especialistas son necesarios para la tarea concreta — casi nunca son los 5 a la vez.
3. Darle a cada especialista solo los archivos y el contexto relacionados con su parte (no "revisa todo el proyecto").
4. Evitar que dos especialistas analicen o toquen lo mismo sin necesidad.
5. Permitir trabajo en paralelo únicamente cuando las tareas no dependan entre sí (p. ej. UX/UI y AI Engineer pueden trabajar a la vez sobre una función nueva; QA y Security van siempre después, nunca en paralelo con quien todavía está cambiando código).
6. Integrar los cambios y resolver cualquier conflicto entre lo que propuso cada especialista.
7. Ejecutar QA al final de todo cambio de código (`npm test`, `npm run lint`, y el barrido visual con Playwright — ver `PROJECT.md`), y Security cuando la tarea toque autenticación, almacenamiento de datos, dependencias o cualquier llamada a un servicio externo nuevo.
8. Actualizar `CURRENT_STATE.md` con lo que se hizo, lo que queda pendiente y cualquier deuda nueva detectada.

Ningún agente debe escanear todo el repositorio salvo que la tarea lo requiera
explícitamente (p. ej. una auditoría general). Por defecto, cada especialista
trabaja solo sobre los archivos que el coordinador le indique.

## Cosas específicas de este repo que todo agente debe respetar

- **No hay módulos ES ni bundler en producción.** Los 11 archivos `.js` se cargan
  con `<script defer>` y comparten un único scope global (ver `PROJECT.md`). Antes
  de renombrar o eliminar una función/variable, comprobar en qué otros archivos se
  usa (y actualizar `eslint.config.mjs` si la lista de globals cambia).
- **Las 9 hojas de CSS se cargan en un orden fijo y se re-tematizan a propósito
  unas a otras** (ver `CSS_AUDIT.md`). No "limpiar" selectores duplicados entre
  archivos sin leer ese documento primero — es intencional, no un bug.
- **`styles.css` tiene 70 selectores duplicados dentro del propio archivo**,
  documentados como deuda conocida en `CSS_AUDIT.md`. No tocarlos sin una razón
  concreta y sin verificar visualmente antes/después con Playwright.
- **No hay backend.** Todo vive en `localStorage`/IndexedDB del navegador. El login
  "Continuar con ChatGPT" solo controla el acceso al sitio publicado, no sincroniza
  datos con esa cuenta.
- **Ningún agente hace `git push` ni crea/gestiona el repositorio remoto.** Ese paso
  lo hace Juan manualmente contra `https://github.com/JuanCopado/HOMEAI.git`; este
  entorno no tiene credenciales de git que funcionen para eso.
- **Todo cambio en `.js` o `.css` se considera incompleto sin**: `npm test`,
  `npm run lint`, y una verificación visual (Playwright, varias vistas y anchos) —
  es el estándar ya establecido en `CHANGELOG_CLAUDE.md`.
