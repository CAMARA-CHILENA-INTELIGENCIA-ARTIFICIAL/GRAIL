/**
 * D3 force-graph renderer.
 *
 * Provided by Nirvai (Nirvana). Author: Benjamín González Guerrero.
 *
 * The renderer owns one SVG, one D3 force simulation, and the drag + zoom
 * behaviours. It exposes an imperative API the sidebar consumes via
 * the Renderer interface in types.ts.
 */

import * as d3 from "d3";
import type {
  EdgeKind,
  GraphPayload,
  MountOptions,
  NodeAttrs,
  NodeKind,
  RawNode,
  Renderer,
  RendererState,
  SimEdge,
  SimNode,
} from "./types";
import { pickNodeColor } from "./palettes";

// ── Tunables ──────────────────────────────────────────────────────────────

const ZOOM_EXTENT: [number, number] = [0.05, 6];
const DEFAULT_FORCE = {
  seed: 42,
  linkDistance: 200,
  linkStrength: 0.2,
  chargeStrength: -3000,
  collideRadius: 50,
  centerStrength: 0.05,
  isolatedRadius: 100,
  isolatedStrength: 0.15,
  alphaDecay: 0.05,
};

const EDGE_BASE_CURVE = 0.22;
const EDGE_LABEL_MAX_CHARS = 60;
const SELECTED_STROKE = "#7c5cff";
const HOVER_STROKE = "#a78bfa";
const DIM_OPACITY = 0.35;
const DEFAULT_EDGE_OPACITY = 0.85;
const DIM_NODE_OPACITY = 0.4;
// Visual minimum so thin edges remain readable against the dark canvas.
const EDGE_MIN_RENDER_WIDTH = 1.2;
// Brighter than the exporter's "#5b6478" — applied when the edge has no
// custom color (i.e. the default RELATED color from the exporter).
const DEFAULT_EDGE_COLOR = "#8b94a8";
const EXPORTER_DEFAULT_EDGE_COLOR = "#5b6478";
// Show edge labels for every visible edge once the user zooms in past this
// scale. Below it, only selected / hovered edges show their label, so the
// overview stays readable.
const EDGE_LABEL_ZOOM_THRESHOLD = 1.5;
// Hide node labels when zoomed out below this scale (they overlap into noise).
const NODE_LABEL_ZOOM_THRESHOLD = 0.45;

// ── Renderer factory ──────────────────────────────────────────────────────

export function createRenderer(
  container: HTMLElement,
  payload: GraphPayload,
  opts: MountOptions = {},
): Renderer {
  const force = { ...DEFAULT_FORCE, ...(payload.meta.force_settings ?? {}) };

  // Deterministic layout — D3's prng uses Math.random by default; override
  // so the same seed always yields the same layout.
  const rng = d3.randomLcg(force.seed / 0xffffffff);

  // Replace the global Math.random for d3.forceX / d3.forceSimulation's
  // initial jitter. d3 v7 exposes per-force `.randomSource`, but the
  // simulation's initial position jitter uses Math.random directly. We
  // approximate determinism by setting initial positions ourselves.
  const width = container.clientWidth || 800;
  const height = container.clientHeight || 600;

  // ── SVG scaffold ────────────────────────────────────────────────────────
  const svg = d3
    .select(container)
    .append("svg")
    .attr("class", "grail-viz-svg")
    .attr("width", "100%")
    .attr("height", "100%")
    .attr("viewBox", `0 0 ${width} ${height}`)
    .style("display", "block")
    .style("cursor", "grab");

  // Group that pans/zooms.
  const root = svg.append("g").attr("class", "grail-viz-root");
  const linksLayer = root.append("g").attr("class", "links");
  const nodesLayer = root.append("g").attr("class", "nodes");

  // ── Prepare data ────────────────────────────────────────────────────────
  const nodes: SimNode[] = payload.nodes.map((n) => {
    const angle = rng() * Math.PI * 2;
    const radius = 200 + rng() * 200;
    return {
      key: n.key,
      attrs: n.attributes,
      x: width / 2 + Math.cos(angle) * radius,
      y: height / 2 + Math.sin(angle) * radius,
      isolated: false,
    } as SimNode;
  });
  const nodeByKey = new Map(nodes.map((n) => [n.key, n]));

  // Group edges by ordered pair to fan multi-edges with curve strength.
  const edgeGroupSize = new Map<string, number>();
  for (const e of payload.edges) {
    const a = e.source < e.target ? e.source : e.target;
    const b = e.source < e.target ? e.target : e.source;
    const k = `${a}|${b}`;
    edgeGroupSize.set(k, (edgeGroupSize.get(k) ?? 0) + 1);
  }
  const edgeGroupIndex = new Map<string, number>();
  const edges: SimEdge[] = payload.edges.map((e) => {
    const a = e.source < e.target ? e.source : e.target;
    const b = e.source < e.target ? e.target : e.source;
    const groupKey = `${a}|${b}`;
    const total = edgeGroupSize.get(groupKey) ?? 1;
    const idx = edgeGroupIndex.get(groupKey) ?? 0;
    edgeGroupIndex.set(groupKey, idx + 1);
    const curveStrength =
      total > 1 ? -EDGE_BASE_CURVE + (idx * 2 * EDGE_BASE_CURVE) / (total - 1) : 0;
    return {
      key: e.key,
      source: nodeByKey.get(e.source) ?? e.source,
      target: nodeByKey.get(e.target) ?? e.target,
      attrs: e.attributes,
      curveStrength,
      isSelfLoop: e.source === e.target,
    } as SimEdge;
  });

  // ── State ───────────────────────────────────────────────────────────────
  const state: RendererState = {
    visibleKinds: new Set(
      (payload.meta.default_visible_kinds.length > 0
        ? payload.meta.default_visible_kinds
        : ["entity"]) as NodeKind[],
    ),
    visibleEdgeKinds: new Set(
      (payload.meta.default_visible_edge_kinds.length > 0
        ? payload.meta.default_visible_edge_kinds
        : ["RELATED"]) as EdgeKind[],
    ),
    typeFilter: new Set<string>(),
    colorMode: opts.colorMode ?? "community",
    selectedNode: null,
    selectedEdge: null,
    hoveredNode: null,
    hoveredEdge: null,
  };

  const listeners = new Set<(s: RendererState) => void>();
  const notify = () => listeners.forEach((l) => l({ ...state }));

  // ── Visibility helpers ──────────────────────────────────────────────────
  const isNodeVisible = (n: SimNode): boolean => {
    if (!state.visibleKinds.has(n.attrs._kind)) return false;
    if (n.attrs._kind === "entity" && state.typeFilter.size > 0) {
      return state.typeFilter.has(n.attrs._type ?? "");
    }
    return true;
  };

  const isEdgeVisible = (e: SimEdge): boolean => {
    if (!state.visibleEdgeKinds.has(e.attrs._kind)) return false;
    const src = typeof e.source === "string" ? nodeByKey.get(e.source) : e.source;
    const tgt = typeof e.target === "string" ? nodeByKey.get(e.target) : e.target;
    if (!src || !tgt) return false;
    return isNodeVisible(src) && isNodeVisible(tgt);
  };

  // MENTIONS edges hide when chunks are visible (avoid Doc→Entity AND
  // Doc→Chunk→Entity double-bridging — same rule as the legacy viz).
  const effectiveVisibleEdgeKinds = (): Set<EdgeKind> => {
    const out = new Set(state.visibleEdgeKinds);
    if (state.visibleKinds.has("chunk") && state.visibleKinds.has("document")) {
      out.delete("MENTIONS");
    }
    return out;
  };

  // ── Edge-kind visibility rule: follow node kinds ────────────────────────
  // When a node kind toggles, auto-update the matching edge kinds so users
  // don't need to manage edges manually.
  const syncEdgeVisibility = () => {
    const eff = new Set<EdgeKind>();
    if (state.visibleKinds.has("entity")) eff.add("RELATED");
    if (state.visibleKinds.has("entity") && state.visibleKinds.has("community"))
      eff.add("IN_COMMUNITY");
    if (state.visibleKinds.has("chunk") && state.visibleKinds.has("document"))
      eff.add("PART_OF");
    if (state.visibleKinds.has("chunk") && state.visibleKinds.has("entity"))
      eff.add("HAS_ENTITY");
    if (state.visibleKinds.has("community") && state.visibleKinds.has("finding"))
      eff.add("HAS_FINDING");
    if (
      state.visibleKinds.has("document") &&
      state.visibleKinds.has("entity") &&
      !state.visibleKinds.has("chunk")
    )
      eff.add("MENTIONS");
    state.visibleEdgeKinds = eff;
  };
  syncEdgeVisibility();

  // ── Compute isolated nodes (no visible edges) ───────────────────────────
  const computeIsolation = () => {
    const eff = effectiveVisibleEdgeKinds();
    const linked = new Set<string>();
    for (const e of edges) {
      if (!eff.has(e.attrs._kind)) continue;
      const sKey = typeof e.source === "string" ? e.source : e.source.key;
      const tKey = typeof e.target === "string" ? e.target : e.target.key;
      linked.add(sKey);
      linked.add(tKey);
    }
    for (const n of nodes) {
      n.isolated = !linked.has(n.key);
    }
  };
  computeIsolation();

  // ── Force simulation ────────────────────────────────────────────────────
  const linkForce = d3
    .forceLink<SimNode, SimEdge>(edges)
    .id((d) => d.key)
    .distance(force.linkDistance)
    .strength((e: SimEdge) => kindLinkStrength(e.attrs._kind, force.linkStrength));

  const chargeForce = d3
    .forceManyBody<SimNode>()
    .strength((n: SimNode) =>
      n.isolated
        ? -Math.abs(force.chargeStrength) / 6
        : kindCharge(n.attrs._kind, force.chargeStrength),
    )
    .distanceMin(20)
    .distanceMax(900)
    .theta(0.8);

  const collideForce = d3
    .forceCollide<SimNode>()
    .radius((n) => (n.attrs.size ?? 6) + 8)
    .strength(0.3)
    .iterations(4);

  const centerForce = d3
    .forceCenter<SimNode>(width / 2, height / 2)
    .strength(force.centerStrength);

  // Documents prefer the outer ring.
  const docRingRadius = Math.min(width, height) * 0.42;
  const docRingForce = d3
    .forceRadial<SimNode>(docRingRadius, width / 2, height / 2)
    .strength((n: SimNode) => (n.attrs._kind === "document" ? 0.18 : 0));

  // Isolated nodes get pulled toward a smaller inner ring so they don't fly off.
  const isolatedRingForce = d3
    .forceRadial<SimNode>(force.isolatedRadius, width / 2, height / 2)
    .strength((n: SimNode) => (n.isolated ? force.isolatedStrength : 0.005));

  const simulation = d3
    .forceSimulation<SimNode, SimEdge>(nodes)
    .force("link", linkForce)
    .force("charge", chargeForce)
    .force("center", centerForce)
    .force("collide", collideForce)
    .force("docRing", docRingForce)
    .force("isolated", isolatedRingForce)
    .velocityDecay(0.4)
    .alphaDecay(force.alphaDecay)
    .alphaMin(0.001);

  // ── Zoom + pan ──────────────────────────────────────────────────────────
  // Tracked so label visibility can respond to zoom level.
  let currentScale = 1;
  const zoom = d3
    .zoom<SVGSVGElement, unknown>()
    .scaleExtent(ZOOM_EXTENT)
    .on("zoom", (e: d3.D3ZoomEvent<SVGSVGElement, unknown>) => {
      root.attr("transform", e.transform.toString());
      const prev = currentScale;
      currentScale = e.transform.k;
      // Crossing either threshold flips global label visibility; only restyle
      // when the regime actually changed to avoid thrash on every wheel tick.
      const edgeFlip =
        (prev >= EDGE_LABEL_ZOOM_THRESHOLD) !==
        (currentScale >= EDGE_LABEL_ZOOM_THRESHOLD);
      const nodeFlip =
        (prev >= NODE_LABEL_ZOOM_THRESHOLD) !==
        (currentScale >= NODE_LABEL_ZOOM_THRESHOLD);
      if (edgeFlip || nodeFlip) updateStyling();
    });

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (svg as any).call(zoom);

  // ── Render selections ───────────────────────────────────────────────────
  const linkSel = linksLayer
    .selectAll<SVGGElement, SimEdge>("g.link")
    .data(edges, (d) => d.key)
    .join((enter) => {
      const g = enter.append("g").attr("class", "link");
      g.append("path")
        .attr("fill", "none")
        .attr("stroke", (d) => baseEdgeColor(d.attrs.color))
        .attr("stroke-opacity", DEFAULT_EDGE_OPACITY)
        .attr("stroke-width", (d) =>
          Math.max(EDGE_MIN_RENDER_WIDTH, d.attrs.size ?? 1),
        )
        .attr("stroke-linecap", "round")
        .attr("data-key", (d) => d.key)
        .style("cursor", "pointer")
        .on("click", (event, d) => {
          event.stopPropagation();
          selectEdge(d.key);
        });
      // Label group only for edges that may ever display text — saves a
      // huge amount of DOM on graphs dominated by IN_COMMUNITY / MENTIONS
      // / HAS_ENTITY edges, which never carry meaningful labels.
      g.filter((d) => hasMeaningfulLabel(d.attrs.label, d.attrs._kind)).each(
        function () {
          const lbl = d3
            .select(this)
            .append("g")
            .attr("class", "link-label")
            .style("opacity", 0)
            .style("pointer-events", "none");
          lbl.append("rect").attr("rx", 4).attr("ry", 4);
          lbl
            .append("text")
            .attr("text-anchor", "middle")
            .attr("dominant-baseline", "middle");
        },
      );
      return g;
    });

  const nodeSel = nodesLayer
    .selectAll<SVGGElement, SimNode>("g.node")
    .data(nodes, (d) => d.key)
    .join((enter) => {
      const g = enter.append("g").attr("class", "node").style("cursor", "pointer");
      g.append("circle")
        .attr("r", (d) => Math.max(3, d.attrs.size ?? 6))
        .attr("fill", (d) => pickNodeColor(d.attrs, state.colorMode))
        .attr("stroke", "#1b2030")
        .attr("stroke-width", 1);
      // NB: a CSS drop-shadow filter was tempting here but it forces every
      // node into its own compositor layer; on large graphs that easily
      // adds 50–200 MB of GPU memory. Skip it.
      g.append("text")
        .attr("dx", (d) => Math.max(3, d.attrs.size ?? 6) + 4)
        .attr("dy", "0.32em")
        .attr("font-size", 11)
        .attr("fill", "currentColor")
        .style("pointer-events", "none")
        .text((d) => truncateLabel(d.attrs.label, 28));
      g.call(dragBehaviour(simulation));
      g.on("click", (event, d) => {
        event.stopPropagation();
        selectNode(d.key);
      });
      g.on("mouseenter", (_event, d) => hoverNode(d.key));
      g.on("mouseleave", () => hoverNode(null));
      return g;
    });

  // Click on empty canvas clears selection.
  svg.on("click", () => {
    state.selectedNode = null;
    state.selectedEdge = null;
    updateStyling();
    notify();
    opts.onSelectionChange?.({ node: null, edge: null, edgeEndpoints: null });
  });

  // ── Tick: compute geometry ──────────────────────────────────────────────
  simulation.on("tick", () => {
    linkSel.each(function (d) {
      const sel = d3.select(this);
      const path = sel.select<SVGPathElement>("path");
      const src = typeof d.source === "object" ? (d.source as SimNode) : nodeByKey.get(d.source as string);
      const tgt = typeof d.target === "object" ? (d.target as SimNode) : nodeByKey.get(d.target as string);
      if (!src || !tgt || src.x == null || src.y == null || tgt.x == null || tgt.y == null) return;

      let pathStr: string;
      let midX = 0;
      let midY = 0;
      let angle = 0;

      if (d.isSelfLoop) {
        const rX = 36;
        const rY = 56;
        const cy = src.y - rY - 8;
        pathStr = `M${src.x},${src.y} C${src.x - rX},${cy} ${src.x + rX},${cy} ${src.x},${src.y}`;
        midX = src.x;
        midY = cy;
      } else {
        const dx = tgt.x - src.x;
        const dy = tgt.y - src.y;
        const dr = Math.sqrt(dx * dx + dy * dy) || 1;
        const mX = (src.x + tgt.x) / 2;
        const mY = (src.y + tgt.y) / 2;
        const nx = -dy / dr;
        const ny = dx / dr;
        const mag = dr * d.curveStrength;
        const cx = mX + nx * mag;
        const cy = mY + ny * mag;
        pathStr = `M${src.x},${src.y} Q${cx},${cy} ${tgt.x},${tgt.y}`;
        midX = 0.25 * src.x + 0.5 * cx + 0.25 * tgt.x;
        midY = 0.25 * src.y + 0.5 * cy + 0.25 * tgt.y;
        angle = (Math.atan2(dy, dx) * 180) / Math.PI;
        if (angle > 90 || angle < -90) angle -= 180;
      }
      path.attr("d", pathStr);

      // Only edges with a label group pay the per-tick transform write.
      const lblNode = (this as SVGGElement).querySelector(".link-label");
      if (lblNode) {
        (lblNode as SVGGElement).setAttribute(
          "transform",
          `translate(${midX},${midY}) rotate(${angle})`,
        );
      }
    });
    nodeSel.attr("transform", (d) => `translate(${d.x ?? 0},${d.y ?? 0})`);
  });

  // After the sim cools off the first time, zoom-to-fit.
  let didInitialFit = false;
  simulation.on("end", () => {
    if (didInitialFit) return;
    didInitialFit = true;
    zoomToFit();
  });

  // ── Hover / selection styling ───────────────────────────────────────────
  function updateStyling() {
    const eff = effectiveVisibleEdgeKinds();
    const focusedNodeKey = state.selectedNode ?? state.hoveredNode;
    const focusedEdgeKey = state.selectedEdge ?? state.hoveredEdge;

    // Build a set of edge keys incident to the focused node.
    const incidentEdgeKeys = new Set<string>();
    const incidentNodeKeys = new Set<string>();
    if (focusedNodeKey) {
      incidentNodeKeys.add(focusedNodeKey);
      for (const e of edges) {
        const sKey = typeof e.source === "string" ? e.source : e.source.key;
        const tKey = typeof e.target === "string" ? e.target : e.target.key;
        if (sKey === focusedNodeKey || tKey === focusedNodeKey) {
          if (eff.has(e.attrs._kind)) {
            incidentEdgeKeys.add(e.key);
            incidentNodeKeys.add(sKey);
            incidentNodeKeys.add(tKey);
          }
        }
      }
    }
    if (focusedEdgeKey) {
      const e = edges.find((x) => x.key === focusedEdgeKey);
      if (e) {
        incidentEdgeKeys.add(e.key);
        const sKey = typeof e.source === "string" ? e.source : e.source.key;
        const tKey = typeof e.target === "string" ? e.target : e.target.key;
        incidentNodeKeys.add(sKey);
        incidentNodeKeys.add(tKey);
      }
    }

    // Nodes.
    nodeSel
      .style("display", (d) => (isNodeVisible(d) ? "" : "none"))
      .style(
        "opacity",
        (d) =>
          (focusedNodeKey || focusedEdgeKey) && !incidentNodeKeys.has(d.key)
            ? DIM_NODE_OPACITY
            : 1,
      );
    nodeSel
      .select<SVGCircleElement>("circle")
      .attr("fill", (d) => pickNodeColor(d.attrs, state.colorMode))
      .attr("stroke", (d) =>
        d.key === state.selectedNode
          ? SELECTED_STROKE
          : d.key === state.hoveredNode
            ? HOVER_STROKE
            : "#1b2030",
      )
      .attr("stroke-width", (d) =>
        d.key === state.selectedNode || d.key === state.hoveredNode ? 2.5 : 1,
      );

    // Edges.
    linkSel
      .style("display", (d) =>
        eff.has(d.attrs._kind) && isEdgeVisible(d) ? "" : "none",
      )
      .select<SVGPathElement>("path")
      .attr("stroke", (d) => {
        if (d.key === state.selectedEdge) return SELECTED_STROKE;
        if (d.key === state.hoveredEdge) return HOVER_STROKE;
        if (focusedNodeKey && incidentEdgeKeys.has(d.key)) return HOVER_STROKE;
        // Community-colored intra-cluster RELATED halo (when in community mode).
        if (
          state.colorMode === "community" &&
          d.attrs._kind === "RELATED" &&
          areSameCommunity(d)
        ) {
          return getCommunityColor(d);
        }
        return baseEdgeColor(d.attrs.color);
      })
      .attr("stroke-opacity", (d) => {
        if (d.key === state.selectedEdge || d.key === state.hoveredEdge) return 1;
        if (focusedNodeKey) {
          return incidentEdgeKeys.has(d.key) ? 0.95 : DIM_OPACITY;
        }
        if (
          state.colorMode === "community" &&
          d.attrs._kind === "RELATED" &&
          areSameCommunity(d)
        ) {
          return 0.7; // community halo
        }
        return DEFAULT_EDGE_OPACITY;
      })
      .attr("stroke-width", (d) => {
        const base = Math.max(EDGE_MIN_RENDER_WIDTH, d.attrs.size ?? 1);
        return d.key === state.selectedEdge || d.key === state.hoveredEdge
          ? base + 1.4
          : base;
      });

    // Edge labels: always show for selected/hovered; otherwise show for
    // every visible edge that has a meaningful label once the user zooms in.
    const showAllEdgeLabels = currentScale >= EDGE_LABEL_ZOOM_THRESHOLD;
    linkSel
      .select<SVGGElement>(".link-label")
      .style("opacity", (d) => {
        if (d.key === state.selectedEdge) return 1;
        if (d.key === state.hoveredEdge) return 0.95;
        if (!showAllEdgeLabels) return 0;
        if (!hasMeaningfulLabel(d.attrs.label, d.attrs._kind)) return 0;
        // Dim incident-only labels less than the focused one, but keep them
        // readable so the user can scan relationship types at a glance.
        if (focusedNodeKey) return incidentEdgeKeys.has(d.key) ? 0.95 : 0.45;
        return 0.85;
      });

    // Only run the (relatively expensive) text/rect layout for labels that
    // could become visible. Skips bbox work when fully zoomed out.
    linkSel.select<SVGGElement>(".link-label").each(function (d) {
      const isSelOrHover =
        d.key === state.selectedEdge || d.key === state.hoveredEdge;
      const wouldShow =
        isSelOrHover ||
        (showAllEdgeLabels && hasMeaningfulLabel(d.attrs.label, d.attrs._kind));
      if (!wouldShow) return;
      const g = d3.select(this);
      const text = g.select<SVGTextElement>("text");
      const rect = g.select<SVGRectElement>("rect");
      const label = d.attrs.label ?? d.attrs._kind;
      text
        .text(truncateLabel(label, EDGE_LABEL_MAX_CHARS))
        .attr("fill", "currentColor")
        .attr("font-size", 10);
      const bbox = (text.node() as SVGTextElement | null)?.getBBox();
      if (bbox) {
        rect
          .attr("x", -bbox.width / 2 - 6)
          .attr("y", -bbox.height / 2 - 3)
          .attr("width", bbox.width + 12)
          .attr("height", bbox.height + 6)
          .attr("fill", "rgba(19, 23, 34, 0.92)");
      }
    });

    // Node labels: hide entirely when zoomed way out so they don't pile up.
    const showNodeLabels = currentScale >= NODE_LABEL_ZOOM_THRESHOLD;
    nodeSel.select<SVGTextElement>("text").style("opacity", (d) => {
      if (!showNodeLabels) return 0;
      if ((focusedNodeKey || focusedEdgeKey) && !incidentNodeKeys.has(d.key))
        return DIM_NODE_OPACITY;
      return 1;
    });
  }

  function areSameCommunity(e: SimEdge): boolean {
    const src = typeof e.source === "string" ? nodeByKey.get(e.source) : e.source;
    const tgt = typeof e.target === "string" ? nodeByKey.get(e.target) : e.target;
    if (!src || !tgt) return false;
    return (
      src.attrs._kind === "entity" &&
      tgt.attrs._kind === "entity" &&
      !!src.attrs._community &&
      src.attrs._community === tgt.attrs._community
    );
  }

  function getCommunityColor(e: SimEdge): string {
    const src = typeof e.source === "string" ? nodeByKey.get(e.source) : e.source;
    return src?.attrs.communityColor ?? "#666c79";
  }

  // ── Selection / hover handlers ──────────────────────────────────────────
  function selectNode(key: string) {
    state.selectedNode = key;
    state.selectedEdge = null;
    focusNode(key);
    updateStyling();
    notify();
    const node = nodeByKey.get(key);
    opts.onSelectionChange?.({ node: node?.attrs ?? null, edge: null, edgeEndpoints: null });
  }

  function selectEdge(key: string) {
    state.selectedNode = null;
    state.selectedEdge = key;
    const e = edges.find((x) => x.key === key);
    updateStyling();
    notify();
    if (!e) {
      opts.onSelectionChange?.({ node: null, edge: null, edgeEndpoints: null });
      return;
    }
    const src = typeof e.source === "string" ? nodeByKey.get(e.source) : e.source;
    const tgt = typeof e.target === "string" ? nodeByKey.get(e.target) : e.target;
    opts.onSelectionChange?.({
      node: null,
      edge: e.attrs,
      edgeEndpoints:
        src && tgt ? { source: src.attrs, target: tgt.attrs } : null,
    });
    // Zoom to fit endpoints.
    if (src && tgt && src.x != null && src.y != null && tgt.x != null && tgt.y != null) {
      zoomToBounds(
        Math.min(src.x, tgt.x),
        Math.min(src.y, tgt.y),
        Math.max(src.x, tgt.x),
        Math.max(src.y, tgt.y),
        120,
      );
    }
  }

  function hoverNode(key: string | null) {
    state.hoveredNode = key;
    state.hoveredEdge = null;
    updateStyling();
  }

  // ── Camera helpers ──────────────────────────────────────────────────────
  function zoomToBounds(
    minX: number,
    minY: number,
    maxX: number,
    maxY: number,
    padding = 80,
  ) {
    const w = container.clientWidth || width;
    const h = container.clientHeight || height;
    const bw = Math.max(1, maxX - minX) + padding * 2;
    const bh = Math.max(1, maxY - minY) + padding * 2;
    const scale = Math.max(
      ZOOM_EXTENT[0],
      Math.min(ZOOM_EXTENT[1], 0.9 * Math.min(w / bw, h / bh)),
    );
    const midX = (minX + maxX) / 2;
    const midY = (minY + maxY) / 2;
    const transform = d3.zoomIdentity
      .translate(w / 2 - midX * scale, h / 2 - midY * scale)
      .scale(scale);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (svg.transition().duration(650).ease(d3.easeCubicInOut) as any).call(
      zoom.transform,
      transform,
    );
  }

  function zoomToFit() {
    const visibleNodes = nodes.filter((n) => isNodeVisible(n) && n.x != null && n.y != null);
    if (visibleNodes.length === 0) return;
    let minX = Infinity,
      minY = Infinity,
      maxX = -Infinity,
      maxY = -Infinity;
    for (const n of visibleNodes) {
      const r = Math.max(3, n.attrs.size ?? 6);
      minX = Math.min(minX, (n.x ?? 0) - r);
      minY = Math.min(minY, (n.y ?? 0) - r);
      maxX = Math.max(maxX, (n.x ?? 0) + r);
      maxY = Math.max(maxY, (n.y ?? 0) + r);
    }
    zoomToBounds(minX, minY, maxX, maxY, 60);
  }

  function focusNode(key: string) {
    const n = nodeByKey.get(key);
    if (!n || n.x == null || n.y == null) return;
    // Frame the node + its first-degree neighbours.
    const eff = effectiveVisibleEdgeKinds();
    let minX = n.x,
      minY = n.y,
      maxX = n.x,
      maxY = n.y;
    for (const e of edges) {
      if (!eff.has(e.attrs._kind)) continue;
      const sKey = typeof e.source === "string" ? e.source : e.source.key;
      const tKey = typeof e.target === "string" ? e.target : e.target.key;
      if (sKey !== key && tKey !== key) continue;
      const other = nodeByKey.get(sKey === key ? tKey : sKey);
      if (!other || other.x == null || other.y == null) continue;
      minX = Math.min(minX, other.x);
      minY = Math.min(minY, other.y);
      maxX = Math.max(maxX, other.x);
      maxY = Math.max(maxY, other.y);
    }
    zoomToBounds(minX, minY, maxX, maxY, 100);
  }

  // ── Drag behaviour ──────────────────────────────────────────────────────
  function dragBehaviour(sim: d3.Simulation<SimNode, SimEdge>) {
    return d3
      .drag<SVGGElement, SimNode>()
      .on("start", (event) => {
        if (!event.active) sim.velocityDecay(0.7).alphaTarget(0.1).restart();
        event.subject.fx = event.subject.x ?? 0;
        event.subject.fy = event.subject.y ?? 0;
      })
      .on("drag", (event) => {
        event.subject.fx = event.x;
        event.subject.fy = event.y;
      })
      .on("end", (event) => {
        if (!event.active) sim.velocityDecay(0.4).alphaTarget(0);
        // Pin the node where the user dropped it.
      });
  }

  // ── Public API ──────────────────────────────────────────────────────────
  const renderer: Renderer = {
    payload,
    destroy() {
      simulation.stop();
      svg.remove();
      listeners.clear();
    },
    relayout() {
      simulation.alpha(1).restart();
      didInitialFit = false;
    },
    setKindVisible(kind, visible) {
      if (visible) state.visibleKinds.add(kind);
      else state.visibleKinds.delete(kind);
      syncEdgeVisibility();
      computeIsolation();
      simulation.alpha(0.5).restart();
      updateStyling();
      notify();
    },
    setTypeFilter(types) {
      state.typeFilter = new Set(types);
      computeIsolation();
      simulation.alpha(0.3).restart();
      updateStyling();
      notify();
    },
    setColorMode(mode) {
      state.colorMode = mode;
      updateStyling();
      notify();
    },
    focusNode(key) {
      focusNode(key);
    },
    searchNodes(query, limit = 12) {
      const q = query.trim().toLowerCase();
      if (!q) return [];
      const out: RawNode[] = [];
      for (const n of nodes) {
        if (n.attrs._kind !== "entity") continue;
        if (!isNodeVisible(n)) continue;
        if (n.attrs.label.toLowerCase().includes(q)) {
          out.push({ key: n.key, attributes: n.attrs });
          if (out.length >= limit) break;
        }
      }
      return out;
    },
    getState() {
      return { ...state };
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };

  // Kick the simulation now that everything is wired up.
  updateStyling();
  simulation.alpha(1).restart();
  return renderer;
}

// ── Helpers ─────────────────────────────────────────────────────────────

function kindCharge(kind: NodeAttrs["_kind"], base: number): number {
  switch (kind) {
    case "community":
      return -Math.abs(base) * 0.28;
    case "document":
      return -Math.abs(base) * 0.7;
    case "chunk":
      return -Math.abs(base) * 0.12;
    case "finding":
      return -Math.abs(base) * 0.08;
    case "entity":
    default:
      return base; // already negative
  }
}

function kindLinkStrength(kind: EdgeKind, base: number): number {
  switch (kind) {
    case "IN_COMMUNITY":
      return base * 0.25;
    case "HAS_FINDING":
      return base * 1.6;
    case "HAS_ENTITY":
      return base * 0.6;
    case "PART_OF":
      return base * 0.8;
    case "MENTIONS":
      return base * 0.4;
    case "RELATED":
    default:
      return base * 1.2;
  }
}

function truncateLabel(s: string, n: number): string {
  if (!s) return "";
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

/**
 * Replace the exporter's default mid-gray RELATED color with a slightly
 * brighter neutral so edges read clearly against the dark canvas. Custom
 * colors (per-kind, community halos) pass through untouched.
 */
function baseEdgeColor(color: string): string {
  if (!color) return DEFAULT_EDGE_COLOR;
  if (color.toLowerCase() === EXPORTER_DEFAULT_EDGE_COLOR) return DEFAULT_EDGE_COLOR;
  return color;
}

// MENTIONS / IN_COMMUNITY / HAS_FINDING / PART_OF / HAS_ENTITY edges don't
// carry meaningful labels — the exporter leaves them blank and our fallback
// would render the bare _kind, which is just noise at zoom.
function hasMeaningfulLabel(label: string | undefined, kind: EdgeKind): boolean {
  if (label && label.trim().length > 0) return true;
  return kind === "RELATED";
}
