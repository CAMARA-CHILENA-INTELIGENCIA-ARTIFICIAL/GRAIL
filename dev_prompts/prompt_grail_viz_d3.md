# GRAIL Knowledge-Graph Visualization — D3.js Redesign

> **Purpose**: This prompt gives a fresh Claude Code session full context to replace GRAIL's Sigma.js-based viz with a D3.js-based viz that ships in **two** surfaces (self-contained HTML + embedded chat-UI route) from one shared TypeScript core. Read this before touching any viz code.

> **Author intent recap**: The Neo4j alternative works but requires the user to create an account. The current Sigma.js viz is "the approach is wrong and it doesn't work properly nor the visual is good." Zep's [`zep-graph-visualization`](https://github.com/getzep/zep-graph-visualization) (Next.js + D3 v7) was identified as the aesthetic target. We keep GRAIL's richer data model (entities, relationships, communities, IDs, descriptions, findings, documents, chunks) and replace only the renderer.

---

## 0. Decisions already taken

1. **Two delivery surfaces, one renderer core**:
   - A. Self-contained `grail viz` HTML (replaces today's Sigma template).
   - B. Embedded React route inside the chat UI (`grail/apps/chat/frontend/`).
   - Both surfaces consume the **same JSON payload** emitted by `grail/viz/exporter.py` (no changes to data contract this iteration).
2. **Drop the Python hierarchical layout** (`grail/viz/layout.py`). Layout is computed client-side by D3's force simulation. The exporter no longer emits `x, y` for nodes — leave the fields off (or set them to `null`) and let D3 initialise them.
3. **Keep the rich data**: every node still carries `_kind`, `_type`, `_community`, `_degree`, `_description`, `_documents`, `_title`, `_summary`, `_text`, `_n_tokens`, `_explanation`, `_n_findings`, `_community_id`, `_level`, `_size`, `_rank` — exactly what `exporter.py:184-339` already produces. Every edge still carries `_kind`, `_description`, `_weight`, `_rank`, `label`.
4. **Preserve current UX features**: layer toggles for 5 node kinds, color-by toggle (community vs. type), live search, click-to-detail panel, community-colored intra-cluster edges, Re-layout button.
5. **Aesthetic targets stolen from Zep**: drag-to-pin with simulation reheat, multi-edge curve fan-out, self-loop ellipses, click-to-zoom-to-neighbourhood, isolated-node gravity well, popovers instead of an always-on side panel (optional — see §6.4).

---

## 1. Current state

### Code lives in `grail/viz/`

| File | Lines | Role | Action |
|---|---|---|---|
| `__init__.py` | 24 | Public API: `build_visualization`, `Visualizer` | unchanged |
| `builder.py` | 130 | Orchestrator: read parquets → `build_sigma_graph` → `render_html` → write | rename internal calls (no public API change) |
| `exporter.py` | 553 | Parquet → JSON payload (5 node kinds, 6 edge kinds) | **strip layout-emission lines (`x, y` keys); keep everything else** |
| `layout.py` | 315 | `compute_hierarchical_layout`: spring per community + outer rings | **delete** (and its caller in `exporter.py:160-176`) |
| `colors.py` | 127 | `KIND_PALETTE`, `build_community_palette`, `build_type_palette`, `hash_color` | **keep as-is** — palettes still drive client-side |
| `template.py` | 1015 | Monolithic Sigma+Graphology+FA2+Noverlap HTML | **delete and replace** |

### CLI command (`grail/cli/main.py:1178-1233`)

```python
@app.command("viz")
def viz(project_dir, output, open_browser=True, layout_seed=42, layout_iterations=200):
    from grail.viz import build_visualization
    out_path = build_visualization(project_dir, output_path=output, ..., layout_seed=..., layout_iterations=...)
```

The `--seed` and `--iterations` flags become **client-side** force-simulation knobs (sent through the JSON `meta` block). Keep the flags; deprecate `--iterations` (replace with `--alpha-decay` or drop entirely — see §5.2).

### Docs to update after the work lands

| File | Why |
|---|---|
| `docs/viz.md` | Switch from "Sigma.js v3 / Graphology / FA2 / Noverlap" to "D3.js v7"; update Pipeline diagram (no Stage 1/2 Python layout); update Tests list to match new test files. |
| `docs-site/docs/guides/visualization.mdx` | **Already drifted** — says "vis.js" today. Rewrite section by section against the new implementation. |

### What the current Sigma template does well (preserve)

- Hover-highlight: edges incident to hovered node light up in accent purple; non-incident edges hide.
- Layers panel: toggle node kinds → matching edges auto-toggle via `_kind` reducer.
- Search-as-you-type entity name autocomplete → zoom-to-node.
- Detail panel renders per `_kind` (entity/document/chunk/community/finding).
- Color mode toggle (community ↔ type) flips entity fill in place.

These behaviours must survive the rewrite — they are good UX, just married to a renderer that looks bad.

---

## 2. Target architecture

```
┌───────────────────────────────────────────────────────────────┐
│  grail/viz/exporter.py            (Python, parquet → JSON)    │
│  • Same payload shape as today.                                │
│  • No x/y in node attributes.                                  │
│  • Adds: meta.force_settings (seed, alphaDecay, charge, …)     │
└──────────────────────────────┬────────────────────────────────┘
                               │ same JSON
            ┌──────────────────┴──────────────────┐
            ▼                                     ▼
┌──────────────────────────┐     ┌──────────────────────────────────┐
│ A. Self-contained HTML   │     │ B. Chat UI React route           │
│   grail/viz/template.py  │     │   grail/apps/chat/frontend/      │
│   • <script src=d3 CDN>  │     │   • npm i d3 + @types/d3         │
│   • Embeds GRAPH_DATA    │     │   • Fetches /api/viz/graph       │
│   • Imports renderer as  │     │   • Imports renderer as ESM      │
│     IIFE bundle (inlined)│     │     (vite resolves)              │
└──────────────┬───────────┘     └──────────────┬───────────────────┘
               │                                │
               └──────────┬─────────────────────┘
                          ▼
            ┌──────────────────────────────────────────┐
            │   Shared TS renderer core                │
            │   grail/viz/web/                         │
            │   • renderer.ts  (D3 force sim, nodes,   │
            │                    edges, drag, zoom)    │
            │   • controls.ts  (layer toggles, search, │
            │                    color-mode, detail)   │
            │   • types.ts     (Node, Edge, Meta)      │
            │   • palettes.ts  (read meta.*_palette)   │
            │   • styles.css   (dark + light tokens)   │
            │   • build.ts     (vite lib mode →        │
            │                    UMD + ESM bundles)    │
            └──────────────────────────────────────────┘
```

### Why a shared TS core (not just two copies)

- Today's `template.py` is 1015 lines of inlined JS+CSS as a Python f-string. Iterating on it is painful (escaping, no type-checking, no IDE help).
- A TS core checked in under `grail/viz/web/` gives us: types, ESLint, a single source of truth, and vite-built bundles that both surfaces consume.
- The Python `template.py` becomes ~100 lines: read the prebuilt `renderer.umd.js` + `styles.css` from `grail/viz/web/dist/`, inline into HTML.
- The chat frontend imports the same module via `import { mount } from "@grail/viz"` (set up as a path alias in `vite.config.ts`).

---

## 3. Data contract (unchanged from today, minus x/y)

`grail/viz/exporter.py:build_sigma_graph` returns:

```ts
{
  nodes: Array<{
    key: string,
    attributes: {
      label: string,
      size: number,                  // KEEP — log-scaled by degree for entities
      color: string,                 // initial color (community default)
      typeColor: string,             // for color-mode toggle
      communityColor: string,        // for color-mode toggle
      _kind: "entity" | "document" | "chunk" | "community" | "finding",

      // entity-only
      _type?: string, _community?: string, _degree?: number,
      _description?: string, _documents?: string[],

      // document-only
      _title?: string, _path?: string, _n_text_units?: number, _doc_id?: string,

      // chunk-only
      _text?: string, _n_tokens?: number, _document_ids?: string[], _chunk_id?: string,

      // community-only
      _community_id?: string, _level?: number, _size?: number, _rank?: number,
      _summary?: string, _n_findings?: number,

      // finding-only
      _summary?: string, _explanation?: string, _community_id?: string,
    }
  }>,

  edges: Array<{
    key: string,
    source: string,
    target: string,
    attributes: {
      size: number,                  // log-scaled by weight
      color: string,
      _kind: "RELATED" | "PART_OF" | "HAS_ENTITY" | "IN_COMMUNITY" | "HAS_FINDING" | "MENTIONS",
      label?: string,                // truncated description for RELATED
      _description?: string,
      _weight?: number,
      _rank?: number,
    }
  }>,

  meta: {
    n_entities: number, n_relationships: number, n_communities: number,
    n_documents: number, n_chunks: number, n_findings: number,
    kind_counts: Record<string, number>,
    edge_kind_counts: Record<string, number>,
    kind_palette: Record<string, string>,
    type_palette: Record<string, string>,
    type_counts: Record<string, number>,
    community_palette: Record<string, string>,
    community_counts: Record<string, number>,
    default_visible_kinds: string[],
    default_visible_edge_kinds: string[],

    // NEW — force-sim knobs piped through from CLI flags
    force_settings: {
      seed: number,           // for d3.randomLcg
      linkDistance: number,   // default 200
      linkStrength: number,   // default 0.2
      chargeStrength: number, // default -3000
      collideRadius: number,  // default 50
      centerStrength: number, // default 0.05
      isolatedRadius: number, // default 100
      isolatedStrength: number, // default 0.15
      alphaDecay: number,     // default 0.05
    }
  }
}
```

**Self-loop and dup-edge handling**:

- `_add_edge` already skips self-loops (`exporter.py:347`). Keep that.
- Multi-edges between the same `(source, target)` may occur for typed relationships once that feature is more widely used. Renderer groups them by ordered pair and fans curve strength `−0.2 → +0.2` à la `Graph.tsx:556-562`.

---

## 4. Force-simulation strategy (kind-aware)

Zep's force config is tuned for one-kind triplet graphs. GRAIL has five kinds with very different roles. The renderer applies a **base** simulation Zep-style, then adds **per-kind force modifiers**:

```ts
const simulation = d3.forceSimulation(nodes)
  .force("link",   d3.forceLink(links).id(d => d.key)
                     .distance(meta.force_settings.linkDistance)
                     .strength(d => kindLinkStrength(d)))
  .force("charge", d3.forceManyBody()
                     .strength(d => kindCharge(d))
                     .distanceMin(20).distanceMax(500).theta(0.8))
  .force("center", d3.forceCenter(width/2, height/2)
                     .strength(meta.force_settings.centerStrength))
  .force("collide", d3.forceCollide()
                     .radius(d => d.size + 8)
                     .strength(0.3).iterations(5))
  // Outer ring for documents — keeps the doc layer visually outside.
  .force("docRing", d3.forceRadial(
    Math.min(width, height) * 0.42, width/2, height/2)
    .strength(d => d._kind === "document" ? 0.25 : 0))
  // Community nodes sit behind their members (light pull to centroid).
  .force("commCentroid", communityCentroidForce(name_to_community_centroid))
  // Findings orbit their parent community.
  .force("findingOrbit", findingOrbitForce(community_centroids, radius=40))
  // Isolated entities get a gentle gravity well, Zep-style.
  .force("isolated", d3.forceRadial(100, width/2, height/2)
                       .strength(d => isolatedIds.has(d.key) ? 0.15 : 0.01))
  .velocityDecay(0.4)
  .alphaDecay(meta.force_settings.alphaDecay)
  .alphaMin(0.001);

function kindCharge(d) {
  if (d._kind === "community") return -800;   // soft — should sit behind
  if (d._kind === "document")  return -2000;
  if (d._kind === "chunk")     return -300;
  if (d._kind === "finding")   return -200;
  return isolatedIds.has(d.key) ? -500 : -3000;  // entity
}

function kindLinkStrength(link) {
  if (link._kind === "IN_COMMUNITY") return 0.05;  // ghostly anchor
  if (link._kind === "HAS_FINDING")  return 0.4;
  if (link._kind === "HAS_ENTITY")   return 0.15;
  if (link._kind === "PART_OF")      return 0.2;
  if (link._kind === "MENTIONS")     return 0.1;
  return 0.3;  // RELATED
}
```

**Reheat-on-toggle**: when a user flips a layer on or off, call `simulation.alpha(0.5).restart()` so the new constraint set settles.

---

## 5. CLI surface

### 5.1 Keep

```
grail viz <project_dir> [--output FILE.html] [--open/--no-open] [--seed N]
```

### 5.2 Replace `--iterations` with force-tuning flags

Old `--iterations 200` was a Python spring-layout knob that no longer applies. Replace with:

```
--alpha-decay FLOAT    Default 0.05. Lower = settles slower, looks prettier.
--charge INT           Default -3000. More negative = nodes repel harder.
--link-distance INT    Default 200. Larger = airier layout.
```

These flow into `meta.force_settings` and the renderer reads them on first simulation start.

For backward-compat, accept `--iterations` but emit a deprecation warning and ignore it.

### 5.3 NEW: `grail viz --serve`

Run a tiny FastAPI app on `localhost:8766` that serves the React route (B-surface) directly, without needing the full chat UI. This is convenient for users who want the interactive viz but haven't authenticated into the chat app. Out of scope for v1 — leave a TODO.

---

## 6. Implementation phases

### Phase 1 — TS renderer core (`grail/viz/web/`)

> Goal: a vite library-mode build that emits `dist/grail-viz.umd.js`, `dist/grail-viz.es.js`, `dist/grail-viz.css`.

1. `package.json` (separate from chat frontend; pinned `d3@^7`, `typescript@^5.8`, `vite@^6.3`).
2. `src/types.ts` — `NodeAttrs`, `EdgeAttrs`, `Meta`, `GraphPayload`. Mirrors §3.
3. `src/renderer.ts` — exports `mount(container: HTMLElement, payload: GraphPayload, opts?: MountOpts): Renderer`. Owns SVG, force sim, drag, zoom, hover, click.
4. `src/controls.ts` — exports `mountSidebar(container, payload, renderer)`. Renders layers panel, search box, color-mode toggle, detail card, footer with Re-layout button. Plain DOM (no framework) so it works in both surfaces.
5. `src/palettes.ts` — `colorForKind(kind)`, `colorForCommunity(cid, meta)`, `colorForType(type, meta)`. All driven by `meta` payload.
6. `src/styles.css` — dark + light tokens; copy `:root` block from current `template.py:79-90` for continuity.
7. `vite.config.ts` — `build.lib = { entry: src/index.ts, name: "GrailViz", formats: ["umd", "es"] }`.
8. **No React dependency** in this package — keeps it embeddable in vanilla HTML.

**Acceptance check for Phase 1**: a stub `examples/dev.html` page loads `grail-viz.umd.js`, calls `GrailViz.mount(...)` with a hand-rolled fixture payload, and renders.

### Phase 2 — Wire up surface A (self-contained HTML)

1. Build `grail/viz/web/` (gets `dist/grail-viz.umd.js` + `.css`).
2. Rewrite `grail/viz/template.py` (~100 lines):
   - Read prebuilt `grail-viz.umd.js` and `grail-viz.css` from `grail/viz/web/dist/` at runtime.
   - Inline them into the HTML between `<script>` and `<style>` tags (offline by default — drop the CDN dependency entirely).
   - Embed `GRAPH_DATA` as `window.__GRAIL_VIZ_PAYLOAD__`.
   - On `DOMContentLoaded`, call `GrailViz.mount(document.getElementById("graph"), window.__GRAIL_VIZ_PAYLOAD__)` and `GrailViz.mountSidebar(...)`.
3. **Build-time step** for packaging: `pyproject.toml` includes `grail/viz/web/dist/**` so wheels carry the prebuilt JS. Add a `build` hook (or document a `npm --prefix grail/viz/web run build` precondition) in `CONTRIBUTING.md`.
4. Delete `grail/viz/layout.py`. Strip layout calls from `exporter.py:160-176`. Drop `x, y` from node attributes.

**Acceptance check for Phase 2**: `uv run grail viz examples/quickstart --no-open` produces `graph.html`; opening it offline shows a force-directed graph with community colors and layer toggles. File size <1.5 MB.

### Phase 3 — Wire up surface B (chat UI route)

1. Add `d3` to `grail/apps/chat/frontend/package.json` (`d3@^7`, `@types/d3` dev).
2. Add path alias in `grail/apps/chat/frontend/vite.config.ts`:
   ```ts
   resolve: { alias: { "@grail/viz": resolve(__dirname, "../../../viz/web/src") } }
   ```
   This compiles the TS source directly — no separate build step needed.
3. New backend endpoint in `grail/apps/chat/server.py`:
   ```python
   @app.get("/api/viz/graph")
   async def viz_graph(current_user: dict = Depends(get_current_user)) -> dict:
       from grail.viz.exporter import build_sigma_graph
       from grail.query.retrieval import load_artifacts_for_search
       grail = _get_grail()
       artifacts = load_artifacts_for_search(grail.storage, grail._output_folder())
       sigma = build_sigma_graph(
           entities_df=artifacts.entities,
           relationships_df=artifacts.relationships,
           nodes_df=artifacts.nodes,
           documents_df=artifacts.documents,
           text_units_df=artifacts.text_units,
           communities_df=artifacts.communities,
           reports_df=artifacts.community_reports,
       )
       return sigma.to_dict()
   ```
4. New React route `grail/apps/chat/frontend/src/components/KnowledgeGraphView.tsx`:
   - Uses `useEffect` to call `mount(ref.current, payload)` on mount and `renderer.destroy()` on unmount.
   - Layout: full-bleed canvas + sidebar (reuse `controls.ts` via `mountSidebar`).
5. Add a "Graph" nav item to `Sidebar.tsx` that routes to `/graph` (the SPA router is hash-based today — add a simple route check in `App.tsx`).

**Acceptance check for Phase 3**: `uv run grail ui examples/quickstart` → log in → click "Graph" → see the same viz embedded inside the chat app, sharing the SPA's auth and theme.

### Phase 4 — Tests + docs

1. Replace `tests/unit/test_viz.py` (currently asserts Sigma-style payload; mostly survives because the payload shape is unchanged):
   - Delete `layout.py` tests.
   - Keep `colors.py` tests.
   - Update `exporter.py` tests to assert absence of `x, y` and presence of `meta.force_settings`.
   - Update `template.py` tests to assert `GrailViz` global is set and `<style>` block embeds CSS.
2. Add a Playwright smoke test (optional) for Surface B that loads `/graph` after auth and asserts the SVG has `circle` and `path` elements.
3. Rewrite `docs/viz.md` and `docs-site/docs/guides/visualization.mdx` (in Spanish; also create an English mirror if the doc-site supports it — current `viz.md` is English-only in `docs/`, but the docs-site copy is Spanish).
4. Update README "What works" line under §4 of `CLAUDE.md` once the renderer ships.

---

## 7. UX details ported from Zep + GRAIL existing template

### 7.1 Interaction map

| Action | Behaviour | Source idea |
|---|---|---|
| **Hover node** | Connected edges glow accent purple; non-incident edges fade to `#1a1d24`. | GRAIL current edge reducer |
| **Hover edge** | Edge label shows; both endpoints brighten to selected color. | GRAIL current node reducer |
| **Click node** | (a) Detail card in sidebar opens; (b) animated zoom-to-bounding-box of node + neighbours via `d3.zoomIdentity.translate().scale()` + transition (750ms `easeCubicInOut`). | Zep `Graph.tsx:642-754` |
| **Click edge** | Detail card shows source → label → target; zoom-to-edge-bounds. | Zep `Graph.tsx:454-549` |
| **Click empty canvas** | Reset selection, reset all colors, close detail card. | both |
| **Drag node** | Pin to mouse; `velocityDecay 0.4→0.7`, `alphaDecay 0.05→0.1`, `alphaTarget 0.1`, reheat sim. On release, set `fx, fy` to pin in place. | Zep `Graph.tsx:281-336` |
| **Wheel zoom** | `d3.zoom().scaleExtent([0.1, 4])`, applied to outer `<g>`. | Zep |
| **Layer toggle** | Hide nodes of that kind + edges with `_kind` matching that kind's edge set; reheat sim. | GRAIL current sidebar |
| **Color-mode toggle** | Flip `fill` on entity circles between `communityColor` and `typeColor`. Cross-fade 200ms. | GRAIL current |
| **Search box** | Live entity-name fuzzy match → click result → animated zoom-to-node. | GRAIL current |
| **Re-layout button** | `simulation.alpha(1).restart()`. Optionally re-seed RNG. | GRAIL current |

### 7.2 Curved + fan-out edges

Group edges by ordered pair `${src}-${tgt}` (with reverse-key dedup). For each group of `n` edges, assign `curveStrength = -baseStrength + index * (baseStrength * 2 / (n-1))`. Render each edge as a quadratic Bézier with control point offset normal to the segment, magnitude `dr * curveStrength`. Self-loops render as an ellipse above the node (Zep `Graph.tsx:799-842`).

### 7.3 Edge label positioning

For each edge, compute midpoint of its Bézier with `path.getPointAtLength(pathLength/2)`. Rotate label group to the edge angle, but flip 180° when the angle exits `[-90, 90]` so text never reads upside-down (Zep `Graph.tsx:880-906`).

### 7.4 Sidebar layout (preserve current GRAIL behaviour)

The Zep reference uses popovers because it has only nodes + edges to inspect. GRAIL has five inspection kinds and rich text (descriptions, summaries, findings). **Keep the always-visible right-side panel** from today's `template.py:325-339` — popovers would force users to chase floating cards across the canvas for what should be persistent context.

Sidebar sections (same as current):
1. **Stats** — entity / relationship / community / document / chunk / finding counts.
2. **Search** — entity-name fuzzy search with autocomplete.
3. **Layers** — toggle entities / relationships / documents / chunks / communities / findings.
4. **Color entities by** — community ↔ type radio.
5. **Entity types legend** — type chips with counts; click to filter.
6. **Selected** — kind-aware detail card (see `viz.md` table at line 263-271).

### 7.5 Theme tokens

Reuse the dark palette from `template.py:79-90`:
```css
--bg: #0b0d12;       --bg-panel: #131722;   --bg-elevated: #1b2030;
--border: #262c3b;   --text: #e7eaf0;       --text-dim: #8a93a6;
--text-faint: #5a6273; --accent: #7c5cff;   --accent-dim: #4a3b9e;
--danger: #f87171;
```

Add a light theme as a `[data-theme="light"]` overlay so Surface B can hot-swap when the chat UI's theme toggles.

---

## 8. Out of scope (defer)

- Multi-level community navigation (Leiden produces a hierarchy; viz shows deepest level only). Add a `level` slider later.
- Streaming layout for >50K nodes — for now we cap at the natural breaking point of D3 in the browser (~10K).
- Offline-via-CDN packaging — Phase 2 already inlines bundles, so this is solved.
- `grail viz --serve` (mentioned §5.3). Leave a TODO.
- Persistence of layer-toggle preferences across sessions.
- Per-edge type colors (today they're a single `EDGE_COLOR #5b6478`). If users start using typed relationships heavily, give each type its own color via a hash + palette lookup.

---

## 9. Quick reference for the implementing session

```
START HERE:
  1. Read this prompt + grail/viz/exporter.py + tests/unit/test_viz.py.
  2. Bring up examples/quickstart (uv run grail index examples/quickstart).
  3. Phase 1: create grail/viz/web/, get `npm run build` to emit dist/.
  4. Phase 2: rewrite grail/viz/template.py against the dist artefacts.
  5. Phase 3: add chat UI route + backend endpoint.
  6. Phase 4: tests + docs.

KEY FILES TO TOUCH:
  grail/viz/exporter.py          — strip x/y, add force_settings to meta
  grail/viz/layout.py            — DELETE
  grail/viz/template.py          — REWRITE (~100 lines)
  grail/viz/web/**               — NEW (the renderer)
  grail/cli/main.py:1178-1233    — swap --iterations for new force flags
  grail/apps/chat/server.py      — add /api/viz/graph
  grail/apps/chat/frontend/      — new KnowledgeGraphView route
  tests/unit/test_viz.py         — update assertions
  docs/viz.md                    — rewrite
  docs-site/docs/guides/visualization.mdx — rewrite (currently wrong)

DON'T:
  • Don't break the JSON payload shape (Surfaces A + B both depend on it).
  • Don't add a Python-side dependency (zero new runtime deps; npm deps are dev-time).
  • Don't introduce React inside grail/viz/web/ — keep it framework-agnostic.
  • Don't kill the layer-toggle UX; it's what makes GRAIL's viz informative vs. Zep's.
  • Don't push without explicit user confirmation (project convention).
```

---

## 10. Open follow-ups (capture as TODOs while implementing)

- [ ] Decide whether `grail.viz.web` ships **prebuilt artefacts** committed to the repo, or whether wheels carry the source and the user's `npm` builds it. Recommended: commit prebuilt `dist/` (read-only, regenerated by maintainer) so end users don't need Node to use `grail viz`.
- [ ] Decide whether to honour `--seed` with a deterministic D3 RNG (`d3.randomLcg(seed)`) — yes, do this, so layouts are reproducible.
- [ ] Decide on the chat UI route name: `/graph`, `/viz`, or `/knowledge-graph`. Bias: `/graph`.
- [ ] Confirm whether the chat UI should fetch the graph payload eagerly (on first nav) or lazily (only when the route is opened). Bias: lazy + cache for the session.
- [ ] Confirm whether the `grail viz` HTML should embed only entity+community+RELATED by default (current behaviour) or all kinds. Bias: keep current default — clean is better than noisy on first open.
