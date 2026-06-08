# Contribuir a GRAIL

> 🇬🇧 Read this in [English](CONTRIBUTING.md).

Gracias por tu interés en contribuir a GRAIL. Este es un framework open-source desarrollado bajo la comisión de la [Cámara Chilena de Inteligencia Artificial](https://cchia.cl), con mantenimiento de [Nirvai](https://nirvana-ai.com). Aceptamos contribuciones en nueve categorías bien definidas — cada una con un flujo estructurado de propuesta-a-merge.

## TL;DR

```
1. Abre un issue en la plantilla de la categoría correcta
2. Espera el label `status:approved` del equipo
3. Abre un PR que referencie el issue aprobado
4. Los reviewers lo verifican contra el checklist de la categoría
5. Merge cuando CI esté en verde y el review apruebe
```

**Sin PR sin issue aprobado.** Esta regla existe para ahorrarte tiempo — queremos darte feedback de diseño *antes* de que escribas código, no después.

---

## El flujo de dos pasos

### Paso 1 · Abre un issue en una plantilla de categoría

Las contribuciones a GRAIL caen en una de **nueve categorías**. Cada una tiene su propia plantilla de issue que te pregunta lo que importa desde el inicio:

| # | Categoría | Ejemplos |
|---|---|---|
| 01 | [Proveedores de inferencia](.github/ISSUE_TEMPLATE/01-inference-provider.yml) | Nuevo endpoint LLM (Fireworks, Hugging Face, OpenAI-compat custom) |
| 02 | [Capacidades multimodales](.github/ISSUE_TEMPLATE/02-multimodal.yml) | Visión, audio, video — GRAIL es text-only hoy, esto es funcionalidad nueva |
| 03 | [Lógica agéntica](.github/ISSUE_TEMPLATE/03-agentic-logic.yml) | Nueva tool de agente, update del system prompt, heurísticas de selección |
| 04 | [Métodos de búsqueda](.github/ISSUE_TEMPLATE/04-search-method.yml) | Nuevo modo más allá de local · cascade · global · document · agent · recall |
| 05 | [Métodos de indexación](.github/ISSUE_TEMPLATE/05-indexing-method.yml) | Nuevo chunker, extractor, algoritmo de comunidades, generador de reportes |
| 06 | [Vector stores](.github/ISSUE_TEMPLATE/06-vector-store.yml) | Nuevo backend `BaseVectorStore` — Qdrant, Weaviate, Milvus, Pinecone |
| 07 | [Integraciones cloud](.github/ISSUE_TEMPLATE/07-cloud-integration.yml) | Nuevo `StorageBackend`, target de deploy, vault de secretos |
| 08 | [Agregar librerías](.github/ISSUE_TEMPLATE/08-library-addition.yml) | Nueva dependencia Python — runtime, extra opcional, dev-only |
| 09 | [Apps visuales](.github/ISSUE_TEMPLATE/09-visual-app.yml) | UI web de chat, TUI de terminal, dashboards, viz del grafo |

**Para cualquier cosa que no calza en una categoría** (preguntas abiertas, discusiones de diseño, "¿qué les parece X?") usa [GitHub Discussions](https://github.com/CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/GRAIL/discussions).

> Nota: las plantillas de issue están en inglés porque los campos son identificadores técnicos (provider name, distance metric, etc.). Puedes rellenarlas en español — el equipo lee ambos idiomas.

### Paso 2 · Espera `status:approved`

Una vez que abres el issue, un mantenedor:

- Aplica el label `category:*` correspondiente (auto-aplicado por la plantilla)
- Revisa la propuesta y hace preguntas si hace falta
- Aplica **`status:approved`** si la propuesta está bien formulada y queremos esto en GRAIL
- O aplica `status:declined` con una razón — a veces una propuesta es buena pero no calza con el alcance de GRAIL; vamos a ser honestos del por qué

Esto suele tomar unos días. Si no tienes respuesta en una semana, hace un ping al issue.

### Paso 3 · Abre un PR

Una vez que tu issue tiene `status:approved`, abre un PR. La [plantilla de PR](.github/PULL_REQUEST_TEMPLATE.md) te va a guiar por un checklist específico de tu categoría. Tu descripción de PR debe:

- Incluir `Closes #NNN` referenciando el issue aprobado
- Marcar la casilla de la categoría que corresponde
- Marcar el checklist específico de la categoría a medida que completas cada ítem

### Paso 4 · Review y merge

Un mantenedor:

- Verifica que el CI pase (`Build (ES + EN)`, gate de publicación, tests)
- Revisa que el checklist de la categoría esté marcado honestamente
- Hace code review
- Mergea cuando esté listo

Si necesitas cambios, hace push de más commits a la rama del PR — usamos squash-merge por default, así que el historial a nivel de PR queda limpio.

---

## Labels

GRAIL usa tres familias de labels:

### `category:*` — qué tipo de cambio

- `category:inference-providers`
- `category:multimodal`
- `category:agentic-logic`
- `category:search-methods`
- `category:indexing-methods`
- `category:vector-stores`
- `category:cloud-integrations`
- `category:library-addition`
- `category:visual-apps`

Auto-aplicados por las plantillas de issue. Se mantienen en el PR como contexto.

### `status:*` — dónde está en el flujo

- `status:proposed` — abierto, esperando review del mantenedor
- `status:approved` — los mantenedores quieren esto; puedes empezar el PR
- `status:declined` — no va a proceder; razón en el comentario
- `status:in-progress` — hay un PR abierto
- `status:blocked` — esperando algo externo
- `status:needs-approval` — PR abierto sin issue aprobado

### `priority:*` (opcional)

- `priority:high` · `priority:medium` · `priority:low`

Se usan para triage del backlog.

---

## Setup local

Python 3.12 + [uv](https://github.com/astral-sh/uv) es la ruta recomendada:

```bash
git clone git@github.com:CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/GRAIL.git
cd GRAIL
uv venv --python 3.12
uv pip install -e ".[dev]"
cp .env.example .env
# Rellena DEEPINFRA_API_KEY o OPENAI_API_KEY (lo que vayas a usar)
```

Verificación:

```bash
uv run grail --help
uv run pytest
```

Para el sitio de docs:

```bash
cd docs-site
npm install
npm start -- --port 3001    # el puerto 3000 puede estar en uso localmente
```

---

## Convenciones de código

Estas son firmes — por favor mátchealas para que tu PR no se traba en estilo:

| Convención | Ejemplo |
|---|---|
| Módulos snake_case, clases PascalCase | `entities_relationships.py`, `class GRAIL` |
| **Sin prefijo `Nirvana` en las clases** | `MemoryProject`, no `NirvanaMemoryProject` |
| Async por default para rutas de I/O | `async def index(self) -> dict` |
| Facades sync envuelven `asyncio.run` cuando sirve | (raro hoy día) |
| Tipos de entidad SIEMPRE `UPPER_SNAKE_CASE` | `PERSON`, `ORGANIZATION`, `CLINICAL_STUDY` |
| Comentarios solo cuando el **por qué** no es obvio | No repitas lo que el código ya dice |
| Endpoint y modelo son campos **separados** en config | `llm.endpoint: openai` + `llm.model: gpt-4o-mini` — nunca `openai\|gpt-4o-mini` en config |
| Dependencias opcionales viven en `[extras]` | `[s3]`, `[ui]`, `[dev]` — no en el install core |
| Cada módulo lleva el header del autor | `"""Provided by Nirvai (Nirvana). Author: Benjamín González Guerrero."""` |

---

## Testing

- `uv run pytest` — la suite de tests unitarios (160+ tests al día de hoy). Todos los tests deben quedar en verde.
- Para features nuevas, agrega tests unitarios bajo `tests/unit/`.
- Para cambios end-to-end (modos de búsqueda, métodos de indexación), agrega cobertura bajo `tests/integration/`.
- Para cambios de schema, agrega fixtures y tests de migración.

El workflow de CI (`.github/workflows/`) corre la suite de tests + el build del sitio de docs en cada PR. Los PRs no pueden mergear con CI en rojo.

---

## Estilo de commits

Sigue el log existente:

```
feat: <qué cambió>            # nueva feature
fix: <qué se rompía>          # bug fix
docs: <qué cambió>            # solo documentación
ci: <qué cambió>              # cambios de CI/CD
refactor: <qué cambió>        # sin cambio de comportamiento
test: <qué cambió>            # agregar tests
chore: <qué cambió>           # todo lo demás
```

Mantén el subject line bajo 72 caracteres. Body es opcional pero recomendable para cambios no triviales.

---

## Dev prompts (handoff entre sesiones)

GRAIL se desarrolla parcialmente con sesiones asistidas por IA. Para features que abarcan múltiples sesiones de trabajo, la convención es escribir un **dev prompt** bajo [`dev_prompts/`](dev_prompts/) que capture la discusión de diseño completa para que una sesión fresca pueda retomar en frío. Ejemplos existentes:

- `dev_prompts/prompt_grail_agentic_memory_design.md` — diseño del modo memoria
- `dev_prompts/prompt_grail_benchmark.md` — metodología del benchmark
- `dev_prompts/prompt_grail_skill_design.md` — formato del skill para agentes

Si tu cambio es lo suficientemente sustancial como para que otro contribuidor (humano o IA) se beneficie del contexto completo, por favor agrega uno.

---

## Documentación

Dos superficies, ambas objetivo de contribuciones:

| Superficie | Audiencia | Dónde |
|---|---|---|
| **`docs-site/`** (Docusaurus) | Usuarios finales | La documentación oficial en [grail-docs.vercel.app](https://grail-docs.vercel.app/) |
| **`docs/`** (markdown) | Contribuidores | Notas técnicas internas — arquitectura, decisiones de diseño, internals de módulos |

Cambios visibles para el usuario (nueva feature, nuevo modo, nuevo endpoint) van a `docs-site/` y **deben incluir versiones en ES y EN** — ve las páginas existentes para la estructura de i18n.

Notas internas / de arquitectura (contratos de parser, diagramas de schema, decisiones de scratch) van a `docs/`.

---

## Lo que te pedimos NO hacer

- ❌ No abras un PR sin issue aprobado (lo vamos a cerrar y a pedirte que abras uno)
- ❌ No agregues una dependencia runtime sin pasar por la plantilla de library-addition
- ❌ No agregues una ruta con vendor lock-in — GRAIL es agnóstico al proveedor por diseño
- ❌ No commitees secrets — ni siquiera temporalmente. Rotamos las llaves pero el historial es para siempre
- ❌ No agregues telemetría / phone-home / analytics — GRAIL es local-first, sin excepciones

---

## Autor y comisión

GRAIL es autoría y mantenimiento de **Benjamín González Guerrero**, fundador de [Nirvai (Nirvana)](https://nirvana-ai.com), bajo la comisión open-source de la **[Cámara Chilena de Inteligencia Artificial](https://cchia.cl)**.

Para preguntas fuera del flujo de issue / PR:

- 💬 [GitHub Discussions](https://github.com/CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/GRAIL/discussions) para preguntas abiertas de diseño
- 🔗 [LinkedIn](https://www.linkedin.com/in/bgg-ai/) para contacto directo con el autor

---

Gracias por ayudar a mejorar GRAIL.
