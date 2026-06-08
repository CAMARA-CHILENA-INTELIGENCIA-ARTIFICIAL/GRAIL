/**
 * Public payload types — must match grail/viz/exporter.py output.
 *
 * Provided by Nirvai (Nirvana). Author: Benjamín González Guerrero.
 */

export type NodeKind = "entity" | "document" | "chunk" | "community" | "finding";

export type EdgeKind =
  | "RELATED"
  | "PART_OF"
  | "HAS_ENTITY"
  | "IN_COMMUNITY"
  | "HAS_FINDING"
  | "MENTIONS";

export interface NodeAttrs {
  label: string;
  size: number;
  color: string;
  typeColor: string;
  communityColor: string;
  _kind: NodeKind;

  // entity-only
  _type?: string;
  _community?: string;
  _degree?: number;
  _description?: string;
  _documents?: string[];

  // document-only
  _title?: string;
  _path?: string;
  _n_text_units?: number;
  _doc_id?: string;

  // chunk-only
  _text?: string;
  _n_tokens?: number;
  _document_ids?: string[];
  _chunk_id?: string;

  // community-only
  _community_id?: string;
  _level?: number;
  _size?: number;
  _rank?: number;
  _summary?: string;
  _n_findings?: number;

  // finding-only
  _explanation?: string;
}

export interface EdgeAttrs {
  size: number;
  color: string;
  _kind: EdgeKind;
  label?: string;
  _description?: string;
  _weight?: number;
  _rank?: number;
}

export interface RawNode {
  key: string;
  attributes: NodeAttrs;
}

export interface RawEdge {
  key: string;
  source: string;
  target: string;
  attributes: EdgeAttrs;
}

export interface ForceSettings {
  seed: number;
  linkDistance: number;
  linkStrength: number;
  chargeStrength: number;
  collideRadius: number;
  centerStrength: number;
  isolatedRadius: number;
  isolatedStrength: number;
  alphaDecay: number;
}

export interface Meta {
  n_entities: number;
  n_relationships: number;
  n_communities: number;
  n_documents: number;
  n_chunks: number;
  n_findings: number;
  kind_counts: Record<string, number>;
  edge_kind_counts: Record<string, number>;
  kind_palette: Record<string, string>;
  type_palette: Record<string, string>;
  type_counts: Record<string, number>;
  community_palette: Record<string, string>;
  community_counts: Record<string, number>;
  default_visible_kinds: string[];
  default_visible_edge_kinds: string[];
  force_settings?: Partial<ForceSettings>;
}

export interface GraphPayload {
  nodes: RawNode[];
  edges: RawEdge[];
  meta: Meta;
}

// ── Runtime types (what the renderer manipulates) ─────────────────────────

import type { SimulationLinkDatum, SimulationNodeDatum } from "d3";

export interface SimNode extends SimulationNodeDatum {
  key: string;
  attrs: NodeAttrs;
  // Whether the node has zero incident visible edges; drives the gravity well.
  isolated: boolean;
}

export interface SimEdge extends SimulationLinkDatum<SimNode> {
  key: string;
  source: SimNode | string;
  target: SimNode | string;
  attrs: EdgeAttrs;
  // Curve strength for fan-out of multi-edges between the same pair.
  curveStrength: number;
  // For self-loops, render as ellipse rather than Bézier.
  isSelfLoop: boolean;
}

export type ColorMode = "community" | "type";

export interface RendererState {
  // Which node kinds are visible right now.
  visibleKinds: Set<NodeKind>;
  // Which edge kinds are visible right now.
  visibleEdgeKinds: Set<EdgeKind>;
  // Entity-type filter — if non-empty, only show entities whose _type is in this set.
  typeFilter: Set<string>;
  // Current entity color mode.
  colorMode: ColorMode;
  // Currently selected node/edge key (mutually exclusive).
  selectedNode: string | null;
  selectedEdge: string | null;
  // Currently hovered node/edge key.
  hoveredNode: string | null;
  hoveredEdge: string | null;
}

export interface MountOptions {
  /** Initial color mode (community by default). */
  colorMode?: ColorMode;
  /** Optional callback fired when selection changes — useful for embedders. */
  onSelectionChange?: (selection: {
    node: NodeAttrs | null;
    edge: EdgeAttrs | null;
    edgeEndpoints?: { source: NodeAttrs; target: NodeAttrs } | null;
  }) => void;
}

export interface Renderer {
  /** Tear down the renderer and free its resources. */
  destroy(): void;
  /** Reheat and rerun the force simulation. */
  relayout(): void;
  /** Toggle visibility for a node kind. */
  setKindVisible(kind: NodeKind, visible: boolean): void;
  /** Set the visible entity types (empty set = show all). */
  setTypeFilter(types: Set<string>): void;
  /** Set the entity color mode. */
  setColorMode(mode: ColorMode): void;
  /** Zoom to a specific node by key. */
  focusNode(key: string): void;
  /** Find nodes whose label fuzzy-matches a query (case-insensitive substring). */
  searchNodes(query: string, limit?: number): RawNode[];
  /** Snapshot of the current state — for the sidebar to read. */
  getState(): RendererState;
  /** Subscribe to state changes; returns an unsubscribe function. */
  subscribe(listener: (state: RendererState) => void): () => void;
  /** The original payload. */
  readonly payload: GraphPayload;
}
