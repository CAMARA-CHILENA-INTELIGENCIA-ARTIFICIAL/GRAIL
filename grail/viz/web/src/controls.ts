/**
 * Sidebar / controls — plain DOM, no framework.
 *
 * Provided by Nirvai (Nirvana). Author: Benjamín González Guerrero.
 *
 * Renders the stats panel, search box, layer toggles, color-mode toggle,
 * entity-type legend, and kind-aware detail card on the right side of the
 * viewer. Subscribes to the renderer's state and updates incrementally.
 */

import type { EdgeAttrs, NodeAttrs, NodeKind, Renderer } from "./types";

const KIND_LABELS: Record<NodeKind, string> = {
  entity: "Entities",
  document: "Documents",
  chunk: "Chunks",
  community: "Communities",
  finding: "Findings",
};

const KIND_ORDER: NodeKind[] = ["entity", "community", "document", "chunk", "finding"];

interface SidebarHandle {
  destroy(): void;
}

export function mountSidebar(container: HTMLElement, renderer: Renderer): SidebarHandle {
  const meta = renderer.payload.meta;
  container.classList.add("grail-viz-sidebar");
  container.innerHTML = `
    <section class="gv-section gv-stats">
      <h3>Stats</h3>
      <dl class="gv-stats-grid"></dl>
    </section>

    <section class="gv-section">
      <h3>Search</h3>
      <input class="gv-search-input" type="search" placeholder="Find an entity…" autocomplete="off" />
      <ul class="gv-search-results"></ul>
    </section>

    <section class="gv-section">
      <h3>Layers</h3>
      <div class="gv-layers"></div>
    </section>

    <section class="gv-section">
      <h3>Color entities by</h3>
      <div class="gv-color-toggle">
        <button data-mode="community" class="gv-pill">Community</button>
        <button data-mode="type" class="gv-pill">Type</button>
      </div>
    </section>

    <section class="gv-section gv-types">
      <h3>Entity types</h3>
      <ul class="gv-type-list"></ul>
    </section>

    <section class="gv-section gv-selected">
      <h3>Selected</h3>
      <div class="gv-detail">
        <p class="gv-detail-empty">Click a node or edge to see details.</p>
      </div>
    </section>
  `;

  // Stats ----------------------------------------------------------------
  const statsGrid = container.querySelector<HTMLDListElement>(".gv-stats-grid")!;
  const stats: [string, number][] = [
    ["Entities", meta.n_entities],
    ["Relationships", meta.n_relationships],
    ["Communities", meta.n_communities],
    ["Documents", meta.n_documents],
    ["Chunks", meta.n_chunks],
    ["Findings", meta.n_findings],
  ];
  statsGrid.innerHTML = stats
    .map(([k, v]) => `<dt>${k}</dt><dd>${v.toLocaleString()}</dd>`)
    .join("");

  // Layers ---------------------------------------------------------------
  const layersBox = container.querySelector<HTMLDivElement>(".gv-layers")!;
  layersBox.innerHTML = KIND_ORDER.map((kind) => {
    const count = meta.kind_counts?.[kind] ?? 0;
    const isOn = renderer.getState().visibleKinds.has(kind);
    return `
      <label class="gv-layer">
        <input type="checkbox" data-kind="${kind}" ${isOn ? "checked" : ""} ${count === 0 ? "disabled" : ""} />
        <span class="gv-layer-swatch" data-kind="${kind}"></span>
        <span class="gv-layer-name">${KIND_LABELS[kind]}</span>
        <span class="gv-layer-count">${count.toLocaleString()}</span>
      </label>
    `;
  }).join("");
  // Color the swatches from the kind palette.
  for (const sw of container.querySelectorAll<HTMLElement>(".gv-layer-swatch")) {
    const k = sw.dataset.kind ?? "";
    sw.style.background = meta.kind_palette?.[k] ?? "#7c5cff";
  }
  for (const cb of container.querySelectorAll<HTMLInputElement>('.gv-layer input[type="checkbox"]')) {
    cb.addEventListener("change", () => {
      renderer.setKindVisible(cb.dataset.kind as NodeKind, cb.checked);
    });
  }

  // Color mode -----------------------------------------------------------
  const colorButtons = container.querySelectorAll<HTMLButtonElement>(".gv-color-toggle button");
  const refreshColorMode = () => {
    const mode = renderer.getState().colorMode;
    for (const b of colorButtons) {
      b.classList.toggle("active", b.dataset.mode === mode);
    }
  };
  for (const b of colorButtons) {
    b.addEventListener("click", () => {
      renderer.setColorMode(b.dataset.mode as "community" | "type");
    });
  }
  refreshColorMode();

  // Types legend ---------------------------------------------------------
  const typeList = container.querySelector<HTMLUListElement>(".gv-type-list")!;
  const types = Object.entries(meta.type_counts ?? {}).sort((a, b) => b[1] - a[1]);
  if (types.length === 0) {
    typeList.innerHTML = `<li class="gv-empty">No typed entities</li>`;
  } else {
    typeList.innerHTML = types
      .map(
        ([t, count]) => `
        <li class="gv-type" data-type="${escapeAttr(t)}">
          <span class="gv-type-swatch" style="background:${meta.type_palette?.[t] ?? "#7c5cff"}"></span>
          <span class="gv-type-name">${escapeText(t)}</span>
          <span class="gv-type-count">${count.toLocaleString()}</span>
        </li>
      `,
      )
      .join("");
  }
  // Click a type to filter; click an active type to clear it.
  const activeTypes = new Set<string>();
  for (const li of typeList.querySelectorAll<HTMLLIElement>("li.gv-type")) {
    li.addEventListener("click", () => {
      const t = li.dataset.type ?? "";
      if (activeTypes.has(t)) activeTypes.delete(t);
      else activeTypes.add(t);
      for (const x of typeList.querySelectorAll<HTMLLIElement>("li.gv-type")) {
        x.classList.toggle("active", activeTypes.has(x.dataset.type ?? ""));
      }
      renderer.setTypeFilter(activeTypes);
    });
  }

  // Search ---------------------------------------------------------------
  const searchInput = container.querySelector<HTMLInputElement>(".gv-search-input")!;
  const searchResults = container.querySelector<HTMLUListElement>(".gv-search-results")!;
  let searchTimer: number | undefined;
  searchInput.addEventListener("input", () => {
    if (searchTimer != null) window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      const q = searchInput.value;
      const hits = renderer.searchNodes(q, 10);
      if (hits.length === 0) {
        searchResults.innerHTML = q ? `<li class="gv-empty">No matches</li>` : "";
        return;
      }
      searchResults.innerHTML = hits
        .map(
          (h) => `
          <li class="gv-search-hit" data-key="${escapeAttr(h.key)}">
            <span class="gv-hit-swatch" style="background:${h.attributes.communityColor}"></span>
            <span class="gv-hit-name">${escapeText(h.attributes.label)}</span>
            ${h.attributes._type ? `<span class="gv-hit-type">${escapeText(h.attributes._type)}</span>` : ""}
          </li>
        `,
        )
        .join("");
      for (const li of searchResults.querySelectorAll<HTMLLIElement>("li.gv-search-hit")) {
        li.addEventListener("click", () => {
          const key = li.dataset.key ?? "";
          renderer.focusNode(key);
        });
      }
    }, 80);
  });

  // Detail card ----------------------------------------------------------
  const detail = container.querySelector<HTMLDivElement>(".gv-detail")!;
  const renderDetail = (selection: {
    node: NodeAttrs | null;
    edge: EdgeAttrs | null;
    edgeEndpoints?: { source: NodeAttrs; target: NodeAttrs } | null;
  }) => {
    if (selection.node) {
      detail.innerHTML = renderNodeDetail(selection.node);
      return;
    }
    if (selection.edge) {
      detail.innerHTML = renderEdgeDetail(selection.edge, selection.edgeEndpoints ?? null);
      return;
    }
    detail.innerHTML = `<p class="gv-detail-empty">Click a node or edge to see details.</p>`;
  };

  // Wire up selection updates via the existing onSelectionChange callback
  // is not possible from inside the sidebar (the renderer was already
  // constructed). Instead we poll renderer.getState() in the subscribe loop.
  let lastSelectedNode: string | null = null;
  let lastSelectedEdge: string | null = null;
  const nodeByKey = new Map(renderer.payload.nodes.map((n) => [n.key, n.attributes]));
  const edgeByKey = new Map(renderer.payload.edges.map((e) => [e.key, e]));
  const unsub = renderer.subscribe((state) => {
    if (state.selectedNode !== lastSelectedNode || state.selectedEdge !== lastSelectedEdge) {
      lastSelectedNode = state.selectedNode;
      lastSelectedEdge = state.selectedEdge;
      if (state.selectedNode) {
        const attrs = nodeByKey.get(state.selectedNode);
        renderDetail({ node: attrs ?? null, edge: null });
      } else if (state.selectedEdge) {
        const e = edgeByKey.get(state.selectedEdge);
        if (e) {
          const src = nodeByKey.get(e.source);
          const tgt = nodeByKey.get(e.target);
          renderDetail({
            node: null,
            edge: e.attributes,
            edgeEndpoints: src && tgt ? { source: src, target: tgt } : null,
          });
        } else {
          renderDetail({ node: null, edge: null });
        }
      } else {
        renderDetail({ node: null, edge: null });
      }
    }
    refreshColorMode();
  });

  return {
    destroy() {
      unsub();
      container.innerHTML = "";
      container.classList.remove("grail-viz-sidebar");
    },
  };
}

// ── Detail-card renderers ───────────────────────────────────────────────

function renderNodeDetail(n: NodeAttrs): string {
  switch (n._kind) {
    case "entity":
      return `
        ${badge(n._type ?? "ENTITY", n.typeColor)}
        ${n._community ? badge("Community " + n._community, n.communityColor, "ghost") : ""}
        <h4>${escapeText(n.label)}</h4>
        ${row("Degree", String(n._degree ?? 0))}
        ${n._description ? section("Description", escapeText(n._description)) : ""}
        ${docList(n._documents)}
      `;
    case "document":
      return `
        ${badge("DOCUMENT", n.color)}
        <h4>${escapeText(n._title ?? n.label)}</h4>
        ${n._path ? row("Path", escapeText(n._path)) : ""}
        ${row("Chunks", String(n._n_text_units ?? 0))}
      `;
    case "chunk":
      return `
        ${badge("CHUNK", n.color)}
        <h4>${escapeText(n.label)}</h4>
        ${row("Tokens", String(n._n_tokens ?? 0))}
        ${n._text ? section("Preview", escapeText(n._text)) : ""}
      `;
    case "community":
      return `
        ${badge("COMMUNITY", n.color)}
        <h4>${escapeText(n._title ?? n.label)}</h4>
        ${row("Level", String(n._level ?? 0))}
        ${row("Members", String(n._size ?? 0))}
        ${row("Rank", (n._rank ?? 0).toFixed(2))}
        ${row("Findings", String(n._n_findings ?? 0))}
        ${n._summary ? section("Summary", escapeText(n._summary)) : ""}
      `;
    case "finding":
      return `
        ${badge("FINDING", n.color)}
        <h4>${escapeText(n._summary ?? n.label)}</h4>
        ${n._community_id ? row("Community", escapeText(n._community_id)) : ""}
        ${n._explanation ? section("Explanation", escapeText(n._explanation)) : ""}
      `;
  }
}

function renderEdgeDetail(
  e: EdgeAttrs,
  endpoints: { source: NodeAttrs; target: NodeAttrs } | null,
): string {
  const triple = endpoints
    ? `<p class="gv-edge-triple">
         <span>${escapeText(endpoints.source.label)}</span>
         <strong>${escapeText(e.label ?? e._kind)}</strong>
         <span>${escapeText(endpoints.target.label)}</span>
       </p>`
    : "";
  return `
    ${badge(e._kind, e.color)}
    <h4>Relationship</h4>
    ${triple}
    ${e._description ? section("Description", escapeText(e._description)) : ""}
    ${row("Weight", (e._weight ?? 0).toFixed(2))}
    ${row("Rank", (e._rank ?? 0).toFixed(2))}
  `;
}

// ── Tiny HTML helpers ───────────────────────────────────────────────────

function badge(text: string, color: string, variant: "solid" | "ghost" = "solid"): string {
  if (variant === "ghost") {
    return `<span class="gv-badge gv-badge-ghost" style="color:${color};border-color:${color}">${escapeText(text)}</span>`;
  }
  return `<span class="gv-badge" style="background:${color}">${escapeText(text)}</span>`;
}

function row(label: string, value: string): string {
  return `<p class="gv-row"><span>${escapeText(label)}</span><span>${value}</span></p>`;
}

function section(title: string, body: string): string {
  return `<div class="gv-section-block"><h5>${escapeText(title)}</h5><p>${body}</p></div>`;
}

function docList(docs: string[] | undefined): string {
  if (!docs || docs.length === 0) return "";
  return `
    <div class="gv-section-block">
      <h5>Documents</h5>
      <ul class="gv-doc-list">
        ${docs.map((d) => `<li>${escapeText(d)}</li>`).join("")}
      </ul>
    </div>
  `;
}

function escapeText(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(s: string): string {
  return escapeText(s).replace(/'/g, "&#39;");
}
