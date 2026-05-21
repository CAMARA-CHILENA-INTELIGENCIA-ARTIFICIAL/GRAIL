"""
Static HTML viewer template.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.

We embed the graph payload as ``window.GRAPH_DATA`` and pull Sigma.js +
Graphology from a CDN. The result is a single self-contained .html file that
opens in any modern browser and renders even when shared via email.

If you need a fully offline (CDN-less) build, set ``cdn=False`` in
:func:`render_html` — that path is left as a future enhancement; today it
falls back to the CDN URLs.
"""
from __future__ import annotations

import datetime
import html
import json
from typing import Any


# Pinned versions — bump deliberately when upstream releases stabilise.
SIGMA_CDN = "https://cdn.jsdelivr.net/npm/sigma@3.0.1/dist/sigma.min.js"
GRAPHOLOGY_CDN = "https://cdn.jsdelivr.net/npm/graphology@0.26.0/dist/graphology.umd.min.js"
FA2_CDN = "https://cdn.jsdelivr.net/npm/graphology-layout-forceatlas2@0.10.1/build/graphology-layout-forceatlas2.umd.min.js"
# Noverlap is a tiny library that nudges overlapping nodes apart — we run it
# once on load to clean up label collisions left over from the server-side layout.
NOVERLAP_CDN = "https://cdn.jsdelivr.net/npm/graphology-layout-noverlap@0.4.2/build/graphology-layout-noverlap.umd.min.js"


def render_html(
    graph_payload: dict[str, Any],
    *,
    title: str = "GRAIL Knowledge Graph",
    project_name: str = "",
    run_id: str = "",
) -> str:
    """Render the standalone HTML viewer."""
    safe_title = html.escape(title)
    safe_project = html.escape(project_name)
    safe_run = html.escape(run_id)
    generated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    data_json = json.dumps(graph_payload, ensure_ascii=False, default=_json_default)

    return _TEMPLATE.format(
        title=safe_title,
        project=safe_project,
        run_id=safe_run,
        generated_at=generated_at,
        data_json=data_json,
        sigma_cdn=SIGMA_CDN,
        graphology_cdn=GRAPHOLOGY_CDN,
        fa2_cdn=FA2_CDN,
        noverlap_cdn=NOVERLAP_CDN,
    )


def _json_default(obj: Any) -> Any:
    """Make numpy scalars / ndarrays / pandas types JSON-serialisable."""
    if hasattr(obj, "tolist"):
        return obj.tolist()
    if hasattr(obj, "item"):
        return obj.item()
    return str(obj)


# ── The template ─────────────────────────────────────────────────────────────
# We use ``str.format`` with curly-brace literals, so every literal ``{`` and
# ``}`` in CSS/JS must be doubled.

_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
  :root {{
    --bg:          #0b0d12;
    --bg-panel:    #131722;
    --bg-elevated: #1b2030;
    --border:      #262c3b;
    --text:        #e7eaf0;
    --text-dim:    #8a93a6;
    --text-faint:  #5a6273;
    --accent:      #7c5cff;
    --accent-dim:  #4a3b9e;
    --danger:      #f87171;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{
    margin: 0; padding: 0;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    line-height: 1.45;
    height: 100vh;
    overflow: hidden;
    -webkit-font-smoothing: antialiased;
  }}
  #app {{
    display: grid;
    grid-template-rows: 44px 1fr 28px;
    grid-template-columns: 1fr 360px;
    height: 100vh;
  }}

  /* ── Header ────────────────────────────────────────── */
  header {{
    grid-column: 1 / 3;
    display: flex;
    align-items: center;
    padding: 0 16px;
    background: var(--bg-panel);
    border-bottom: 1px solid var(--border);
    gap: 12px;
  }}
  header .logo {{
    font-weight: 700;
    letter-spacing: 0.6px;
    color: var(--text);
    font-size: 14px;
  }}
  header .logo .grail {{ color: var(--accent); }}
  header .project {{
    color: var(--text-dim);
    font-size: 12px;
  }}
  header .project::before {{ content: "·"; margin: 0 8px; color: var(--text-faint); }}
  header .run {{
    margin-left: auto;
    color: var(--text-faint);
    font-size: 11px;
    font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  }}

  /* ── Graph canvas ──────────────────────────────────── */
  #graph {{
    background: radial-gradient(ellipse at center, #15192a 0%, var(--bg) 70%);
    position: relative;
  }}
  #graph canvas {{ display: block; }}
  #zoom-controls {{
    position: absolute;
    bottom: 16px;
    left: 16px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }}
  .zbtn {{
    width: 32px; height: 32px;
    background: var(--bg-panel);
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: 6px;
    cursor: pointer;
    font-size: 16px;
    display: flex; align-items: center; justify-content: center;
    transition: background 0.15s;
  }}
  .zbtn:hover {{ background: var(--bg-elevated); border-color: var(--accent-dim); }}

  /* ── Side panel ────────────────────────────────────── */
  aside {{
    background: var(--bg-panel);
    border-left: 1px solid var(--border);
    overflow-y: auto;
    padding: 16px;
  }}
  aside::-webkit-scrollbar {{ width: 8px; }}
  aside::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 4px; }}

  .section {{
    margin-bottom: 18px;
  }}
  .section-title {{
    text-transform: uppercase;
    font-size: 10px;
    letter-spacing: 1px;
    color: var(--text-faint);
    margin: 0 0 8px 0;
    font-weight: 600;
  }}

  /* Stats */
  .stats {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
  .stat {{
    background: var(--bg-elevated);
    border-radius: 8px;
    padding: 10px 12px;
  }}
  .stat .v {{ font-size: 18px; font-weight: 600; color: var(--text); }}
  .stat .k {{ font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-top: 2px; }}

  /* Search */
  .search-box {{
    position: relative;
  }}
  .search-box input {{
    width: 100%;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 8px 10px;
    border-radius: 6px;
    font-size: 12px;
    outline: none;
    transition: border-color 0.15s;
  }}
  .search-box input:focus {{ border-color: var(--accent); }}
  .search-results {{
    position: absolute;
    top: calc(100% + 4px);
    left: 0; right: 0;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: 6px;
    max-height: 200px;
    overflow-y: auto;
    z-index: 10;
    display: none;
  }}
  .search-results.open {{ display: block; }}
  .search-results .row {{
    padding: 6px 10px;
    cursor: pointer;
    font-size: 12px;
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .search-results .row:hover {{ background: var(--bg-panel); }}
  .search-results .row .dot {{
    width: 8px; height: 8px; border-radius: 50%;
    flex-shrink: 0;
  }}
  .search-results .row .type {{
    margin-left: auto;
    font-size: 10px;
    color: var(--text-faint);
    text-transform: uppercase;
  }}

  /* Mode toggle */
  .toggle {{
    display: flex;
    background: var(--bg-elevated);
    border-radius: 6px;
    padding: 3px;
    gap: 2px;
  }}
  .toggle button {{
    flex: 1;
    padding: 6px 8px;
    background: transparent;
    border: 0;
    color: var(--text-dim);
    border-radius: 4px;
    cursor: pointer;
    font-size: 11px;
    font-weight: 500;
    transition: all 0.15s;
  }}
  .toggle button.active {{ background: var(--accent); color: white; }}
  .toggle button:not(.active):hover {{ color: var(--text); }}

  /* Layers (node-kind toggles) */
  .layers {{ display: flex; flex-direction: column; gap: 4px; }}
  .layer {{
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 8px;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: 6px;
    cursor: pointer;
    user-select: none;
    font-size: 12px;
    transition: opacity 0.15s, background 0.15s;
  }}
  .layer:hover {{ background: var(--bg-panel); }}
  .layer.off {{ opacity: 0.4; }}
  .layer .swatch {{
    width: 12px; height: 12px; border-radius: 3px;
    flex-shrink: 0;
  }}
  .layer.kind-document .swatch {{ border-radius: 2px; }}
  .layer.kind-community .swatch {{ border-radius: 50%; }}
  .layer .name {{ flex: 1; text-transform: capitalize; }}
  .layer .count {{ color: var(--text-dim); font-size: 11px; font-variant-numeric: tabular-nums; }}

  /* Legend */
  .legend {{ display: flex; flex-wrap: wrap; gap: 4px; }}
  .chip {{
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 4px 8px;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: 999px;
    font-size: 11px;
    cursor: pointer;
    user-select: none;
    transition: opacity 0.15s, transform 0.1s;
  }}
  .chip:hover {{ transform: translateY(-1px); }}
  .chip.hidden {{ opacity: 0.35; }}
  .chip .dot {{
    width: 8px; height: 8px; border-radius: 50%;
  }}
  .chip .count {{ color: var(--text-dim); font-size: 10px; }}

  /* Detail panel */
  .detail-empty {{
    color: var(--text-faint);
    font-size: 12px;
    font-style: italic;
    padding: 16px;
    text-align: center;
    border: 1px dashed var(--border);
    border-radius: 8px;
  }}
  .detail-card {{
    background: var(--bg-elevated);
    border-radius: 8px;
    padding: 12px;
  }}
  .detail-card .name {{
    font-size: 14px;
    font-weight: 600;
    margin-bottom: 4px;
    word-break: break-word;
  }}
  .detail-card .badges {{
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-bottom: 10px;
  }}
  .detail-card .badge {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 7px;
    border-radius: 999px;
    font-size: 10px;
    font-weight: 500;
    background: var(--bg-panel);
    border: 1px solid var(--border);
  }}
  .detail-card .badge .dot {{ width: 6px; height: 6px; border-radius: 50%; }}
  .detail-card .description {{
    color: var(--text-dim);
    font-size: 12px;
    line-height: 1.55;
    margin-bottom: 10px;
    max-height: 240px;
    overflow-y: auto;
  }}
  .detail-card .sources {{
    border-top: 1px solid var(--border);
    padding-top: 10px;
  }}
  .detail-card .sources .label {{
    font-size: 10px;
    color: var(--text-faint);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 4px;
  }}
  .detail-card .sources ul {{
    list-style: none;
    padding: 0;
    margin: 0;
  }}
  .detail-card .sources li {{
    font-size: 11px;
    color: var(--text);
    padding: 2px 0;
    word-break: break-word;
  }}
  .detail-card .sources li::before {{ content: "▸ "; color: var(--text-faint); }}

  /* ── Footer ────────────────────────────────────────── */
  footer {{
    grid-column: 1 / 3;
    display: flex;
    align-items: center;
    padding: 0 16px;
    background: var(--bg-panel);
    border-top: 1px solid var(--border);
    color: var(--text-faint);
    font-size: 11px;
    gap: 12px;
  }}
  footer .spacer {{ flex: 1; }}
  footer button {{
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text-dim);
    padding: 3px 10px;
    border-radius: 4px;
    font-size: 11px;
    cursor: pointer;
    transition: all 0.15s;
  }}
  footer button:hover {{ color: var(--text); border-color: var(--accent-dim); }}
  footer .status {{ font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }}

  /* ── Loading state ─────────────────────────────────── */
  #loading {{
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg);
    z-index: 100;
    transition: opacity 0.3s;
  }}
  #loading.hidden {{ opacity: 0; pointer-events: none; }}
  #loading .spinner {{
    width: 32px; height: 32px;
    border: 3px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }}
  @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
</style>
</head>
<body>
<div id="app">
  <header>
    <span class="logo"><span class="grail">GRAIL</span> · Knowledge Graph</span>
    <span class="project">{project}</span>
    <span class="run">{run_id}</span>
  </header>

  <div id="graph">
    <div id="loading"><div class="spinner"></div></div>
    <div id="zoom-controls">
      <button class="zbtn" id="zoom-in" title="Zoom in">+</button>
      <button class="zbtn" id="zoom-out" title="Zoom out">−</button>
      <button class="zbtn" id="zoom-reset" title="Reset view">⊙</button>
    </div>
  </div>

  <aside>
    <div class="section">
      <div class="stats" id="stats"></div>
    </div>

    <div class="section">
      <h3 class="section-title">Search</h3>
      <div class="search-box">
        <input id="search" type="text" placeholder="Find a node..." autocomplete="off">
        <div class="search-results" id="search-results"></div>
      </div>
    </div>

    <div class="section">
      <h3 class="section-title">Layers</h3>
      <div class="layers" id="layers"></div>
    </div>

    <div class="section">
      <h3 class="section-title">Color entities by</h3>
      <div class="toggle" id="color-toggle">
        <button data-mode="community" class="active">Community</button>
        <button data-mode="type">Entity type</button>
      </div>
    </div>

    <div class="section">
      <h3 class="section-title">Entity types</h3>
      <div class="legend" id="legend"></div>
    </div>

    <div class="section">
      <h3 class="section-title">Selected</h3>
      <div id="detail">
        <div class="detail-empty">Click a node for details</div>
      </div>
    </div>
  </aside>

  <footer>
    <span>Generated by GRAIL — {generated_at}</span>
    <span class="spacer"></span>
    <span class="status" id="hover-status"></span>
    <button id="relayout" title="Re-run ForceAtlas2 layout in the browser">Re-layout</button>
  </footer>
</div>

<script src="{graphology_cdn}"></script>
<script src="{sigma_cdn}"></script>
<script src="{fa2_cdn}"></script>
<script src="{noverlap_cdn}"></script>
<script>
// ─────────────────────────────────────────────────────────────────────
//   Embedded graph payload — produced by grail/viz/exporter.py
// ─────────────────────────────────────────────────────────────────────
const GRAPH_DATA = {data_json};

// ─────────────────────────────────────────────────────────────────────
//   Build the Graphology graph
// ─────────────────────────────────────────────────────────────────────
const graph = new graphology.Graph({{type: "undirected", multi: false}});
GRAPH_DATA.nodes.forEach(n => graph.addNode(n.key, n.attributes));
GRAPH_DATA.edges.forEach(e => {{
  if (graph.hasNode(e.source) && graph.hasNode(e.target) && !graph.hasEdge(e.source, e.target)) {{
    graph.addEdge(e.source, e.target, e.attributes);
  }}
}});

// ─────────────────────────────────────────────────────────────────────
//   Renderer
// ─────────────────────────────────────────────────────────────────────
const container = document.getElementById("graph");
const renderer = new Sigma(graph, container, {{
  renderEdgeLabels: false,
  labelColor:        {{color: "#d4dae8"}},
  labelSize:         11,
  labelWeight:       "500",
  labelFont:         "-apple-system, BlinkMacSystemFont, sans-serif",
  // Only label nodes with rendered size >= this threshold — keeps the canvas
  // legible. Smaller nodes still reveal their label on hover.
  labelRenderedSizeThreshold: 9,
  labelDensity:      1.0,
  labelGridCellSize: 70,
  defaultEdgeColor:  "#5b6478",
  edgeColor:         "default",
  zIndex:            true,
  allowInvalidContainer: true,
  // Don't render edges thinner than this — keeps faint relationships visible.
  minEdgeThickness:  0.8,
}});

// ─────────────────────────────────────────────────────────────────────
//   State + reducers (hover highlight, hidden types, color mode)
// ─────────────────────────────────────────────────────────────────────
// Initialize per-kind visibility from the meta payload's recommended defaults.
const defaultVisibleKinds = new Set(GRAPH_DATA.meta.default_visible_kinds || ["entity"]);
const allKinds = Object.keys(GRAPH_DATA.meta.kind_palette || {{}});
const hiddenKinds = new Set(allKinds.filter(k => !defaultVisibleKinds.has(k)));

const state = {{
  hovered:        null,           // node key
  hoveredNeighbors: new Set(),
  selected:       null,           // node key
  hiddenTypes:    new Set(),      // entity-type filter
  hiddenKinds:    hiddenKinds,    // node-kind filter (document/chunk/entity/community/finding)
  searchMatches:  null,           // Set or null (null = no active search)
  // Communities are the primary visual grouping — default the color mode
  // accordingly. Toggle in the sidebar to switch to entity-type coloring.
  colorMode:      "community",    // 'community' | 'type'
}};

renderer.setSetting("nodeReducer", (node, data) => {{
  const res = {{...data}};
  // Kind visibility — quickest reject; hides everything else for this node.
  if (state.hiddenKinds.has(data._kind)) {{
    res.hidden = true;
    return res;
  }}
  // Color mode applies only to entities; other kinds keep their kind-color.
  if (data._kind === "entity") {{
    res.color = (state.colorMode === "community") ? data.communityColor : data.typeColor;
    res.zIndex = 1;  // entities always render above background kinds
  }} else if (data._kind === "community") {{
    // Communities sit behind entities and stay semi-transparent so they read
    // as landmarks, not as the primary nodes.
    res.color = (data.communityColor || data.color) + "aa";
    res.zIndex = 0;
  }} else if (data._kind === "document") {{
    res.zIndex = 0;
  }} else if (data._kind === "chunk" || data._kind === "finding") {{
    res.zIndex = 0;
  }}
  // Entity-type filter (only affects entities).
  if (data._kind === "entity" && state.hiddenTypes.has(data._type)) {{
    res.hidden = true;
    return res;
  }}
  // Search filter
  if (state.searchMatches && !state.searchMatches.has(node)) {{
    res.label = "";
    res.color = "#2a2f3a";
    res.size  = Math.max(2, data.size * 0.5);
    return res;
  }}
  // Hover highlight
  if (state.hovered) {{
    if (node === state.hovered) {{
      res.zIndex = 2;
      res.highlighted = true;
    }} else if (state.hoveredNeighbors.has(node)) {{
      res.zIndex = 1;
    }} else {{
      res.label = "";
      res.color = res.color + "33"; // append alpha → translucent
    }}
  }}
  // Selected
  if (node === state.selected) {{
    res.zIndex = 3;
    res.highlighted = true;
  }}
  return res;
}});

renderer.setSetting("edgeReducer", (edge, data) => {{
  const res = {{...data}};
  const [src, tgt] = graph.extremities(edge);
  const srcKind = graph.getNodeAttribute(src, "_kind");
  const tgtKind = graph.getNodeAttribute(tgt, "_kind");
  // Hide if either endpoint's kind is currently hidden.
  if (state.hiddenKinds.has(srcKind) || state.hiddenKinds.has(tgtKind)) {{
    res.hidden = true;
    return res;
  }}
  // MENTIONS is a synthetic doc↔entity shortcut — only useful when chunks are
  // hidden. When the user turns chunks on, hide MENTIONS so we don't duplicate
  // the Doc→Chunk→Entity path.
  if (data._kind === "MENTIONS" && !state.hiddenKinds.has("chunk")) {{
    res.hidden = true;
    return res;
  }}
  // Entity-type filter (only relevant for RELATED edges between entities).
  if (srcKind === "entity" && tgtKind === "entity" &&
      (state.hiddenTypes.has(graph.getNodeAttribute(src, "_type")) ||
       state.hiddenTypes.has(graph.getNodeAttribute(tgt, "_type")))) {{
    res.hidden = true;
    return res;
  }}
  // Hover: only show edges incident to the hovered node, in accent color.
  if (state.hovered) {{
    if (src === state.hovered || tgt === state.hovered) {{
      res.color = "#a78bfa";
      res.size  = Math.max(data.size + 0.5, 2.0);
      res.zIndex = 1;
    }} else {{
      res.hidden = true;
    }}
  }} else if (data._kind === "RELATED" && state.colorMode === "community") {{
    // Intra-community RELATED edges glow softly in the cluster color.
    const srcComm = graph.getNodeAttribute(src, "_community");
    const tgtComm = graph.getNodeAttribute(tgt, "_community");
    if (srcComm && srcComm === tgtComm) {{
      const palette = GRAPH_DATA.meta.community_palette;
      res.color = (palette[srcComm] || "#5b6478") + "55";
    }}
  }}
  return res;
}});

// ─────────────────────────────────────────────────────────────────────
//   Events
// ─────────────────────────────────────────────────────────────────────
renderer.on("enterNode", ({{node}}) => {{
  state.hovered = node;
  state.hoveredNeighbors = new Set(graph.neighbors(node));
  document.getElementById("hover-status").textContent = node;
  container.style.cursor = "pointer";
  renderer.refresh();
}});

renderer.on("leaveNode", () => {{
  state.hovered = null;
  state.hoveredNeighbors = new Set();
  document.getElementById("hover-status").textContent = "";
  container.style.cursor = "default";
  renderer.refresh();
}});

renderer.on("clickNode", ({{node}}) => {{
  state.selected = node;
  showDetail(node);
  renderer.refresh();
}});

renderer.on("clickStage", () => {{
  state.selected = null;
  showDetail(null);
  renderer.refresh();
}});

// ─────────────────────────────────────────────────────────────────────
//   UI: stats
// ─────────────────────────────────────────────────────────────────────
function renderStats() {{
  const m = GRAPH_DATA.meta;
  const cells = [
    {{k: "Entities",      v: m.n_entities}},
    {{k: "Relationships", v: m.n_relationships}},
    {{k: "Communities",   v: m.n_communities}},
    {{k: "Documents",     v: m.n_documents}},
  ];
  document.getElementById("stats").innerHTML = cells.map(
    c => `<div class="stat"><div class="v">${{c.v}}</div><div class="k">${{c.k}}</div></div>`
  ).join("");
}}

// ─────────────────────────────────────────────────────────────────────
//   UI: layers (per-kind visibility)
// ─────────────────────────────────────────────────────────────────────
const KIND_ORDER = ["document", "chunk", "entity", "community", "finding"];

function renderLayers() {{
  const counts  = GRAPH_DATA.meta.kind_counts  || {{}};
  const palette = GRAPH_DATA.meta.kind_palette || {{}};
  const html = KIND_ORDER
    .filter(k => (counts[k] || 0) > 0)
    .map(k => {{
      const isOff = state.hiddenKinds.has(k);
      return `
      <div class="layer kind-${{k}} ${{isOff ? 'off' : ''}}" data-kind="${{k}}">
        <span class="swatch" style="background:${{palette[k]}}"></span>
        <span class="name">${{k}}s</span>
        <span class="count">${{counts[k]}}</span>
      </div>`;
    }})
    .join("");
  document.getElementById("layers").innerHTML = html;
  document.querySelectorAll(".layer").forEach(row => {{
    row.addEventListener("click", () => {{
      const k = row.dataset.kind;
      if (state.hiddenKinds.has(k)) {{
        state.hiddenKinds.delete(k);
        row.classList.remove("off");
      }} else {{
        state.hiddenKinds.add(k);
        row.classList.add("off");
      }}
      renderer.refresh();
    }});
  }});
}}

// ─────────────────────────────────────────────────────────────────────
//   UI: legend
// ─────────────────────────────────────────────────────────────────────
function renderLegend() {{
  const palette = GRAPH_DATA.meta.type_palette;
  const counts  = GRAPH_DATA.meta.type_counts;
  const entries = Object.entries(palette).sort((a, b) => (counts[b[0]] || 0) - (counts[a[0]] || 0));
  const html = entries.map(([t, color]) => `
    <span class="chip" data-type="${{t}}" title="Click to toggle">
      <span class="dot" style="background:${{color}}"></span>
      <span>${{t}}</span>
      <span class="count">${{counts[t] || 0}}</span>
    </span>
  `).join("");
  document.getElementById("legend").innerHTML = html;
  document.querySelectorAll(".chip").forEach(chip => {{
    chip.addEventListener("click", () => {{
      const t = chip.dataset.type;
      if (state.hiddenTypes.has(t)) {{
        state.hiddenTypes.delete(t);
        chip.classList.remove("hidden");
      }} else {{
        state.hiddenTypes.add(t);
        chip.classList.add("hidden");
      }}
      renderer.refresh();
    }});
  }});
}}

// ─────────────────────────────────────────────────────────────────────
//   UI: search
// ─────────────────────────────────────────────────────────────────────
const searchInput = document.getElementById("search");
const searchResults = document.getElementById("search-results");

searchInput.addEventListener("input", () => {{
  const q = searchInput.value.trim().toLowerCase();
  if (!q) {{
    state.searchMatches = null;
    searchResults.classList.remove("open");
    renderer.refresh();
    return;
  }}
  const palette = GRAPH_DATA.meta.type_palette;
  const matches = [];
  graph.forEachNode((node, attrs) => {{
    if (attrs.label.toLowerCase().includes(q)) {{
      matches.push({{node, label: attrs.label, type: attrs._type, color: palette[attrs._type] || "#888"}});
    }}
  }});
  state.searchMatches = new Set(matches.map(m => m.node));

  searchResults.innerHTML = matches.slice(0, 25).map(m => `
    <div class="row" data-node="${{m.node}}">
      <span class="dot" style="background:${{m.color}}"></span>
      <span>${{m.label}}</span>
      <span class="type">${{m.type}}</span>
    </div>
  `).join("") || `<div class="row" style="color:var(--text-faint)">No matches</div>`;
  searchResults.classList.add("open");
  renderer.refresh();
}});

searchResults.addEventListener("click", (e) => {{
  const row = e.target.closest(".row");
  if (!row || !row.dataset.node) return;
  const node = row.dataset.node;
  state.selected = node;
  searchResults.classList.remove("open");
  searchInput.value = graph.getNodeAttribute(node, "label");
  state.searchMatches = null;
  centerOnNode(node);
  showDetail(node);
  renderer.refresh();
}});

document.addEventListener("click", (e) => {{
  if (!e.target.closest(".search-box")) {{
    searchResults.classList.remove("open");
  }}
}});

// ─────────────────────────────────────────────────────────────────────
//   UI: color mode toggle
// ─────────────────────────────────────────────────────────────────────
document.querySelectorAll("#color-toggle button").forEach(btn => {{
  btn.addEventListener("click", () => {{
    document.querySelectorAll("#color-toggle button").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    state.colorMode = btn.dataset.mode;
    renderer.refresh();
  }});
}});

// ─────────────────────────────────────────────────────────────────────
//   UI: entity detail
// ─────────────────────────────────────────────────────────────────────
function showDetail(node) {{
  const elt = document.getElementById("detail");
  if (!node) {{
    elt.innerHTML = `<div class="detail-empty">Click a node for details</div>`;
    return;
  }}
  const a = graph.getNodeAttributes(node);
  const kindPalette = GRAPH_DATA.meta.kind_palette || {{}};
  const kindColor = a.color || kindPalette[a._kind] || "#888";

  let bodyHtml = "";
  if (a._kind === "entity") {{
    const palette = GRAPH_DATA.meta.type_palette;
    const commPalette = GRAPH_DATA.meta.community_palette;
    const typeColor = palette[a._type] || "#888";
    const commColor = commPalette[a._community] || "#888";
    const docs = (a._documents || []).map(d => `<li>${{escapeHtml(d)}}</li>`).join("");
    bodyHtml = `
      <div class="badges">
        <span class="badge"><span class="dot" style="background:${{typeColor}}"></span>${{a._type}}</span>
        ${{a._community ? `<span class="badge"><span class="dot" style="background:${{commColor}}"></span>Community ${{a._community}}</span>` : ""}}
        <span class="badge">Degree ${{a._degree}}</span>
      </div>
      <div class="description">${{escapeHtml(a._description || "—")}}</div>
      ${{docs ? `<div class="sources"><div class="label">Sources</div><ul>${{docs}}</ul></div>` : ""}}
    `;
  }} else if (a._kind === "document") {{
    bodyHtml = `
      <div class="badges">
        <span class="badge"><span class="dot" style="background:${{kindColor}}"></span>Document</span>
        <span class="badge">${{a._n_text_units}} chunks</span>
      </div>
      <div class="description">${{escapeHtml(a._path || "—")}}</div>
    `;
  }} else if (a._kind === "chunk") {{
    bodyHtml = `
      <div class="badges">
        <span class="badge"><span class="dot" style="background:${{kindColor}}"></span>Chunk</span>
        <span class="badge">${{a._n_tokens}} tokens</span>
      </div>
      <div class="description">${{escapeHtml(a._text || "—")}}</div>
    `;
  }} else if (a._kind === "community") {{
    bodyHtml = `
      <div class="badges">
        <span class="badge"><span class="dot" style="background:${{kindColor}}"></span>Community ${{a._community_id}}</span>
        <span class="badge">${{a._size}} entities</span>
        ${{a._rank > 0 ? `<span class="badge">Rank ${{a._rank.toFixed(1)}}</span>` : ""}}
        ${{a._n_findings ? `<span class="badge">${{a._n_findings}} findings</span>` : ""}}
      </div>
      <div class="description">${{escapeHtml(a._summary || "—")}}</div>
    `;
  }} else if (a._kind === "finding") {{
    bodyHtml = `
      <div class="badges">
        <span class="badge"><span class="dot" style="background:${{kindColor}}"></span>Finding</span>
        <span class="badge">Community ${{a._community_id}}</span>
      </div>
      <div class="description"><strong>${{escapeHtml(a._summary)}}</strong><br><br>${{escapeHtml(a._explanation)}}</div>
    `;
  }}

  elt.innerHTML = `
    <div class="detail-card">
      <div class="name">${{escapeHtml(a.label)}}</div>
      ${{bodyHtml}}
    </div>
  `;
}}

function escapeHtml(s) {{
  return String(s).replace(/[&<>"']/g, c => ({{
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }}[c]));
}}

// ─────────────────────────────────────────────────────────────────────
//   Camera controls
// ─────────────────────────────────────────────────────────────────────
function centerOnNode(node) {{
  const {{x, y}} = graph.getNodeAttributes(node);
  renderer.getCamera().animate({{x, y, ratio: 0.4}}, {{duration: 600}});
}}

document.getElementById("zoom-in").addEventListener("click", () => {{
  renderer.getCamera().animatedZoom({{factor: 1.5}});
}});
document.getElementById("zoom-out").addEventListener("click", () => {{
  renderer.getCamera().animatedUnzoom({{factor: 1.5}});
}});
document.getElementById("zoom-reset").addEventListener("click", () => {{
  renderer.getCamera().animatedReset();
}});

// ─────────────────────────────────────────────────────────────────────
//   Re-layout (ForceAtlas2 in the browser)
// ─────────────────────────────────────────────────────────────────────
document.getElementById("relayout").addEventListener("click", () => {{
  if (!window.graphologyLibrary || !window.graphologyLibrary.layoutForceAtlas2) {{
    if (typeof forceAtlas2 === "undefined") {{
      alert("ForceAtlas2 layout library failed to load (CDN unreachable).");
      return;
    }}
  }}
  const fa2 = (window.graphologyLibrary && window.graphologyLibrary.layoutForceAtlas2) || window.forceAtlas2;
  const settings = fa2.inferSettings(graph);
  settings.gravity = 1;
  settings.scalingRatio = 10;
  document.getElementById("loading").classList.remove("hidden");
  setTimeout(() => {{
    fa2.assign(graph, {{iterations: 150, settings}});
    renderer.refresh();
    renderer.getCamera().animatedReset();
    document.getElementById("loading").classList.add("hidden");
  }}, 20);
}});

// ─────────────────────────────────────────────────────────────────────
//   Boot
// ─────────────────────────────────────────────────────────────────────
renderStats();
renderLayers();
renderLegend();

// ForceAtlas2 produces the natural "social-graph" look — clusters emerge from
// edge density rather than being arranged on a ring. We seed it with the
// community-aware spring positions so the final layout still respects the
// community structure but flows organically. Cheap for the quickstart (~382
// nodes) — a few hundred ms.
function runForceAtlas2(iterations) {{
  const lib = window.graphologyLibrary && window.graphologyLibrary.layoutForceAtlas2;
  const fa2 = lib || window.forceAtlas2;
  if (!fa2) return;
  try {{
    const settings = fa2.inferSettings(graph);
    settings.gravity         = 1.5;
    settings.scalingRatio    = 12;
    settings.slowDown        = 8;
    settings.barnesHutOptimize = graph.order > 1000;
    settings.outboundAttractionDistribution = true;
    fa2.assign(graph, {{iterations: iterations || 200, settings}});
  }} catch (e) {{ console.warn("ForceAtlas2 failed:", e); }}
}}

// One pass of noverlap nudges any remaining overlapping nodes apart so labels
// don't collide.
function runNoverlap() {{
  const lib = window.graphologyLibrary && window.graphologyLibrary.layoutNoverlap;
  const fn  = lib || window.noverlap;
  if (!fn) return;
  try {{
    fn.assign(graph, {{
      maxIterations: 60,
      settings: {{margin: 4, ratio: 1.1, expansion: 1.1, gridSize: 30, speed: 3}},
    }});
  }} catch (e) {{ console.warn("Noverlap failed:", e); }}
}}

window.addEventListener("load", () => {{
  // Use the next animation frame so the spinner has a chance to render.
  requestAnimationFrame(() => {{
    runForceAtlas2(200);
    runNoverlap();
    renderer.refresh();
    renderer.getCamera().animatedReset();
    document.getElementById("loading").classList.add("hidden");
  }});
}});
</script>
</body>
</html>
"""
