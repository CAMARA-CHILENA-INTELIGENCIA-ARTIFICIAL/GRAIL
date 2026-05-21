# Graph visualization (`grail viz`)

> **Scope.** Turning an indexed GRAIL project into a self-contained HTML graph
> explorer. Configures: nothing yet (uses sensible defaults). Code: ``grail/viz/``.

The viz feature is intentionally **isolated from the main indexing/query
pipelines** — it only reads parquet artefacts off disk and emits a single
self-contained `.html` file. It has zero new runtime dependencies beyond what
GRAIL already ships (`pandas`, `networkx`, stdlib). All client-side rendering
happens via three MIT-licensed libraries loaded from a CDN at view time:

| Library | Role |
|---|---|
| [Sigma.js v3](https://www.sigmajs.org/) | WebGL renderer |
| [Graphology](https://graphology.github.io/) | In-memory graph object + layout algorithms |
| [graphology-layout-forceatlas2](https://graphology.github.io/standard-library/layout-forceatlas2.html) | ForceAtlas2 (organic clustering) |
| [graphology-layout-noverlap](https://graphology.github.io/standard-library/layout-noverlap.html) | Label-collision fix |

The HTML is shareable: send a teammate the `.html` file and they see exactly
your graph as long as they have an internet connection (for the CDN libs).
Graph data is embedded inline as JSON; the file is typically 500 KB – 1 MB.

---

## CLI

```bash
grail viz <project_dir> [--output PATH] [--no-open] [--seed 42] [--iterations 200]
```

| Flag | Default | Effect |
|---|---|---|
| `--output / -o` | `<project>/graph.html` | Where to write the file. |
| `--open / --no-open` | `--open` | Open in the default browser when done. |
| `--seed` | `42` | Layout seed. Same seed + same data → same layout. |
| `--iterations` | `200` | Spring-layout iterations (more = tighter clusters, slower). |

The command auto-resolves to the **active run** via `output/current.json`, so
it always visualises the latest index/append/edit/delete result without
manual path handling.

---

## Data model — mirrors Neo4j

The viewer encodes the same 5-kind graph used by the legacy Neo4j Bloom
notebook, with Covariate omitted (GRAIL doesn't currently produce covariates):

```
┌──────────┐  PART_OF      ┌──────┐  HAS_ENTITY   ┌────────┐  RELATED   ┌────────┐
│ Document │ ─────────────►│Chunk │ ────────────► │ Entity │ ◄─────────►│ Entity │
└──────────┘               └──────┘               └────────┘            └────────┘
     │                                                 │
     │ MENTIONS (synth, hides when Chunk shown)        │ IN_COMMUNITY
     └───────────────────────────────────────►   ┌───────────┐  HAS_FINDING  ┌─────────┐
                                                 │ Community │ ─────────────►│ Finding │
                                                 └───────────┘               └─────────┘
```

### Node kinds

| Kind | Source parquet | Key attributes | Default visible |
|---|---|---|---|
| **`document`** | `final_docs` | `_title, _path, _n_text_units, _doc_id` | off |
| **`chunk`** | `final_text_units` | `_text, _n_tokens, _document_ids, _chunk_id` | off |
| **`entity`** | `final_entities` | `_type, _community, _degree, _description, _documents` + `typeColor`, `communityColor` | **on** |
| **`community`** | `final_communities` + `final_community_reports` | `_community_id, _level, _size, _rank, _title, _summary, _n_findings` | off |
| **`finding`** | rows from `community_reports.findings[]` | `_summary, _explanation, _community_id` | off |

Defaults are configured in `grail/viz/exporter.py`:

```python
DEFAULT_VISIBLE_KINDS = ["entity"]
DEFAULT_VISIBLE_EDGE_KINDS = ["RELATED"]
```

The user toggles other kinds on via the "Layers" panel in the sidebar — they
load instantly because the data is already in the embedded payload.

### Edge kinds

| Edge | From → To | Source | Default visible |
|---|---|---|---|
| `RELATED` | Entity ↔ Entity | `final_relationships` | **on** |
| `PART_OF` | Chunk → Document | `text_units.document_ids` | when both kinds visible |
| `HAS_ENTITY` | Chunk → Entity | inverted from `entities.text_unit_ids` | when chunks visible |
| `IN_COMMUNITY` | Entity → Community | `nodes_df.community` | when community visible |
| `HAS_FINDING` | Community → Finding | enumerated from `reports.findings[]` | when finding visible |
| `MENTIONS` | Document → Entity (synth) | `entities.document_ids` | when documents visible **and** chunks hidden |

`MENTIONS` is a synthetic shortcut emitted so that when the user shows
Documents but hides Chunks, every entity still has a visible connection to
its source document. The edge reducer hides `MENTIONS` whenever Chunks become
visible, to avoid double-bridging Doc → Chunk → Entity AND Doc → Entity.

---

## Pipeline

```
parquet artefacts  ──►  Visualizer.build()  ──►  graph.html
                            │
                            ├── build_sigma_graph()    (exporter.py)
                            │     • read parquets
                            │     • build per-kind nodes
                            │     • emit edges by kind
                            │     • compute community + type palettes
                            │
                            ├── compute_hierarchical_layout()   (layout.py)
                            │     • community-aware spring layout for entities
                            │     • community nodes at member centroids
                            │     • documents on an outer ring
                            │     • chunks at the midpoint of (doc, mentioned entities)
                            │     • findings in a small inner ring inside their community
                            │
                            └── render_html()         (template.py)
                                  • embed payload as window.GRAPH_DATA
                                  • inline CSS + JS
                                  • return one big string
```

Public API:

```python
from grail.viz import build_visualization
out = build_visualization(project_dir="examples/quickstart")
# out → Path to graph.html
```

---

## Layout algorithm

GRAIL ships a **two-stage hierarchical layout** computed server-side in
Python, then runs **ForceAtlas2 client-side on load** to refine it.

### Stage 1 — entities by community (Python, `layout.py`)

`compute_community_layout`:

1. Bucket entities by community id (from `final_nodes.parquet`).
2. For each community, run NetworkX `spring_layout` on the *subgraph* of
   that community — gives a tight, locally-correct embedding.
3. Place community centres on a ring whose radius scales with the largest
   cluster + an inter-cluster gap factor.
4. Translate each community's sub-layout to its centre.

This guarantees each community renders as a visible cluster, instead of
collapsing into one ball as a single-stage spring layout would do for
strongly-connected graphs.

### Stage 2 — other kinds (Python)

`compute_hierarchical_layout` extends the entity layout with positions for
the other kinds:

* **Community nodes**: each sits at the centroid of its member entities.
* **Document nodes**: on a wide outer ring around the entity galaxy.
* **Chunk nodes**: at the midpoint between their document(s) and the
  entities they mention.
* **Finding nodes**: small inner ring inside their parent community.

### Stage 3 — ForceAtlas2 + noverlap (JavaScript, on load)

The browser re-runs the layout on top of the precomputed positions:

```javascript
// in the HTML template, fires on window.load
runForceAtlas2(200);   // 200 iterations of FA2 — organic clustering
runNoverlap();         // small nudges to spread overlapping nodes
```

Settings:

```javascript
settings.gravity = 1.5;
settings.scalingRatio = 12;
settings.slowDown = 8;
settings.outboundAttractionDistribution = true;
settings.barnesHutOptimize = graph.order > 1000;
```

This is what gives the final layout its "social-graph" feel — edges
determine the shape, community colours emerge as visual clusters, no
node sits visibly on top of another. The Re-layout button at the bottom of
the page re-runs both passes if you want to shake things up.

---

## Visual encoding

### Colors

Two palettes ship in `grail/viz/colors.py`:

**Entity-type palette** — secondary signal, coordinated muted tones so a 10-type
mix doesn't shout. Each of GRAIL's 10 default entity types has a fixed
hand-picked colour; unknown types fall back to a deterministic 16-colour
fallback palette.

**Community palette** — primary signal, 20 vivid jewel tones inspired by D3
`schemeCategory10` + ColorBrewer. Adjacent community ids get distinct hues.
Wraps around past 20 communities.

**Color mode** is user-toggleable in the sidebar; defaults to **community**
because clusters carry the story. Entity-type mode is a click away.

### Sizes

Configured in `grail/viz/exporter.py`:

```python
NODE_MIN_SIZE = 3.0       # smallest entity (degree 0)
NODE_MAX_SIZE = 22.0      # largest entity (max-degree hub)
KIND_SIZE = {
    "document":  12.0,
    "chunk":     5.0,
    "entity":    None,    # log-scaled by degree
    "community": 14.0,    # + min(8, n_members * 0.08)
    "finding":   4.0,
}
```

Entities use a **log-scaled** size derived from their `degree`. Communities
grow gently with member count — never large enough to swallow their member
entities. Documents and chunks stay visually quiet because they're
infrastructure, not the story.

### Edges

* Default colour: `#5b6478` (brighter than the previous `#3a3f4a` so edges
  are visible against the dark canvas without dominating).
* Size: log-scaled by `weight`, range `0.6` – `3.5`.
* **In community-colour mode**, intra-community `RELATED` edges glow softly
  in the cluster's colour (alpha `55`) — gives each community a visual
  backbone.
* On hover, edges incident to the hovered node light up in accent purple;
  non-incident edges hide. This makes neighbour discovery instant.

### Z-order

Entities render above community nodes (which are semi-transparent halos
behind their members) and above documents (which are visual anchors, not the
primary content). The node reducer sets `zIndex`:

```
entity:    1    (above)
community: 0    (behind)
document:  0    (behind)
chunk:     0    (behind)
finding:   0    (behind)
```

---

## Sidebar interactions

| Section | What it does |
|---|---|
| **Stats** | Counts of entities / relationships / communities / documents. |
| **Search** | Live entity-name search with autocomplete; click a result to zoom to that node. |
| **Layers** | Per-kind visibility toggles. Click `documents` / `chunks` / `communities` / `findings` to show/hide that whole node kind. Edge visibility follows automatically. |
| **Color entities by** | Toggle between community colour (default) and entity-type colour. |
| **Entity types** | Legend chips, click to filter entities of that type. |
| **Selected** | Kind-aware detail panel. Click any node: |
| | • **Entity** → type badge, community badge, degree, description, source documents |
| | • **Document** → path, chunk count |
| | • **Chunk** → preview text, token count |
| | • **Community** → summary, rank, member count, finding count |
| | • **Finding** → summary, full explanation (citations preserved) |

The bottom-right footer has a **Re-layout** button that re-runs ForceAtlas2
client-side. Use it if the initial layout settles badly for your particular
graph.

---

## Data the indexer must produce

The viz reads, in order of importance:

| File | Required | Used for |
|---|---|---|
| `final_entities.parquet` | **yes** | Entity nodes. If empty, viz errors with "Run `grail index` first". |
| `final_relationships.parquet` | yes (can be empty) | `RELATED` edges. |
| `final_nodes.parquet` | yes (for community colouring) | `entity_name → community_id` mapping. |
| `final_docs.parquet` | optional | Document nodes + source citations on entities. |
| `final_text_units.parquet` | optional | Chunk nodes + HAS_ENTITY edges. |
| `final_communities.parquet` | optional | Community member counts. |
| `final_community_reports.parquet` | optional | Community titles, summaries, ranks, findings. |

**Important**: the viz colours and labels community nodes using
`final_community_reports.parquet` (title, rank, summary). When community
report generation fails (e.g. truncated LLM output, see
[indexing.md](indexing.md) and [llm.md](llm.md) for the
reasoning-mode trap), communities still render — but with fallback titles
like `Community 7` and rank `0.0`. That's a *symptom of bad upstream data*,
not a viz bug.

Common upstream issues that make the viz look worse than it is:

| Symptom in viz | Upstream cause |
|---|---|
| Many isolated dots scattered around | `final_entities` has entities with `degree=0` — LLM extracted entities but no relationships between them. Typical for list-mention text. |
| Empty community labels | `final_community_reports.parquet` has `title=""` and `rank=0.0` — community report generation failed (often truncation from reasoning-mode LLMs). |
| Duplicate-looking entities clustered together | LLM emitted both `"EANO"` and `"European Association of Neuro-Oncology (EANO)"` as separate entities. No disambiguation pass in the extractor yet. |
| One giant cluster swallowing 80%+ of nodes | Leiden produced a single dominant community. Tune `community.max_cluster_size` and `community.min_community_size` in `community.yaml`. |

---

## Layout of the generated HTML

```html
<!doctype html>
<html>
<head>
  <title>GRAIL — {project}</title>
  <style>…dark theme…</style>
</head>
<body>
  <div id="app">
    <header>…GRAIL · Knowledge Graph · project · run_id…</header>
    <div id="graph"><div id="loading">…</div></div>
    <aside>…stats, search, layers, color toggle, legend, detail…</aside>
    <footer>…timestamp + Re-layout button…</footer>
  </div>

  <script src="https://cdn.jsdelivr.net/npm/graphology@0.26.0/…"></script>
  <script src="https://cdn.jsdelivr.net/npm/sigma@3.0.1/…"></script>
  <script src="https://cdn.jsdelivr.net/npm/graphology-layout-forceatlas2@0.10.1/…"></script>
  <script src="https://cdn.jsdelivr.net/npm/graphology-layout-noverlap@0.4.2/…"></script>

  <script>
    const GRAPH_DATA = { nodes: […], edges: […], meta: {…} };
    // …reducers, event handlers, layer toggles, search, detail panel, FA2 boot…
  </script>
</body>
</html>
```

`GRAPH_DATA.meta` carries every palette, count, and default-visibility list
so the sidebar UI can render itself without phoning home.

---

## How to extend

* **New entity type** with a custom colour: add it to
  `DEFAULT_TYPE_PALETTE` in `grail/viz/colors.py`. Unknown types fall back
  to `FALLBACK_PALETTE` deterministically.
* **New node kind**: add it to `KIND_PALETTE`, `KIND_SIZE`, and create a
  rendering branch in the template's `nodeReducer` + `showDetail` switch.
  Wire up an exporter loop that produces nodes of the new kind.
* **Different layout**: replace `compute_hierarchical_layout` in
  `grail/viz/layout.py`. The contract is `{(kind, id): (x, y)}`.
* **Different palette**: swap `DEFAULT_TYPE_PALETTE` and `COMMUNITY_PALETTE`
  in `colors.py`. Re-run `grail viz` — the new colours apply on next render.
* **Offline / CDN-less**: today the libs come from jsDelivr. To inline
  them, fetch the four `.min.js` files at build time and embed them as
  `<script>…</script>` blocks in `template.py`. ~600 KB extra per file.

---

## Tests

`tests/unit/test_viz.py` covers:

* **colors.py**: known-type stability, unknown-type fallback, deterministic
  hashing, community palette generation.
* **layout.py**: seed determinism, empty graph, community-aware separation
  (asserts 3× cluster separation vs. within-cluster spread), isolate
  handling.
* **exporter.py**: all five kinds emitted, kind-counts match inputs, edge
  kinds present, default-visibility flags, kind-specific attribute
  completeness, self-loop suppression, unknown-type fallback colouring,
  document resolution on entities.
* **template.py**: HTML renders, payload parses back, title escaping,
  numpy array serialisation.

Run with:

```bash
uv run pytest tests/unit/test_viz.py -v
```

---

## Known limitations

1. **No streaming layout** — full layout is computed in Python before the
   HTML is written. For graphs > 50 K nodes consider precomputing positions
   once and embedding them, or switching to a deferred server-side layout.
2. **CDN dependency at view time** — sharing the HTML to an air-gapped
   environment requires inlining the libs (see "How to extend").
3. **Chunk kind explodes with large corpora** — toggling Chunks on for a
   project with thousands of text units will be visually noisy and slow.
   Default is off; we may add a "Chunks: visible if N < threshold" toggle
   later.
4. **No multi-level community navigation yet** — Leiden produces a hierarchy
   (`level: 0, 1, 2…`), but the viz currently shows the deepest level
   only. A future "Community level" slider would let users zoom in/out
   across the dendrogram.
5. **Empty community reports render as `Community N` placeholders** — the
   viz doesn't try to mask the upstream failure; surfacing it makes
   reasoning-mode truncation and similar bugs visible instead of hidden.

---

## Quick reference for future sessions

* **Code lives in**: `grail/viz/` — `__init__.py`, `builder.py`, `colors.py`,
  `exporter.py`, `layout.py`, `template.py`.
* **CLI command**: `grail/cli/main.py:viz`.
* **Tests**: `tests/unit/test_viz.py`.
* **Public API**: `from grail.viz import build_visualization` or
  `from grail.viz import Visualizer`.
* **The HTML file is self-contained** — no GRAIL runtime needed to view it.
* **Zero new runtime deps** beyond what GRAIL already pulls in.

When debugging a "weird looking" graph, **always check the parquets first**.
The viz is a faithful reflection of `final_*.parquet` — if it looks wrong,
the data is almost certainly the cause. The viz only fails closed (errors
when entities are empty); it never fabricates or silently drops data.
