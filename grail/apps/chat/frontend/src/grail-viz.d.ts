// Ambient declaration for the cross-package renderer.
//
// Vite resolves the import to grail/viz/web/src via an alias in
// vite.config.ts; TypeScript here only needs to know the module exists
// and the shapes it exposes. The actual source of truth is
// grail/viz/web/src/types.ts.

declare module "@grail/viz" {
  export type NodeKind =
    | "entity"
    | "document"
    | "chunk"
    | "community"
    | "finding";

  export type EdgeKind =
    | "RELATED"
    | "PART_OF"
    | "HAS_ENTITY"
    | "IN_COMMUNITY"
    | "HAS_FINDING"
    | "MENTIONS";

  export type ColorMode = "community" | "type";

  export interface NodeAttrs {
    label: string;
    size: number;
    color: string;
    typeColor: string;
    communityColor: string;
    _kind: NodeKind;
    _type?: string;
    _community?: string;
    _degree?: number;
    _description?: string;
    _documents?: string[];
    _title?: string;
    _path?: string;
    _n_text_units?: number;
    _doc_id?: string;
    _text?: string;
    _n_tokens?: number;
    _document_ids?: string[];
    _chunk_id?: string;
    _community_id?: string;
    _level?: number;
    _size?: number;
    _rank?: number;
    _summary?: string;
    _n_findings?: number;
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
    force_settings?: Record<string, number>;
    truncation?: {
      truncated: true;
      total_entities: number;
      total_relationships: number;
      kept_entities: number;
      kept_relationships: number;
      policy: string;
      cap: number;
    };
  }

  export interface GraphPayload {
    nodes: RawNode[];
    edges: RawEdge[];
    meta: Meta;
  }

  export interface MountOptions {
    colorMode?: ColorMode;
    onSelectionChange?: (selection: {
      node: NodeAttrs | null;
      edge: EdgeAttrs | null;
      edgeEndpoints?: { source: NodeAttrs; target: NodeAttrs } | null;
    }) => void;
  }

  export interface Renderer {
    destroy(): void;
    relayout(): void;
    setKindVisible(kind: NodeKind, visible: boolean): void;
    setTypeFilter(types: Set<string>): void;
    setColorMode(mode: ColorMode): void;
    focusNode(key: string): void;
    searchNodes(query: string, limit?: number): RawNode[];
    readonly payload: GraphPayload;
  }

  export interface MountHandle {
    renderer: Renderer;
    destroy(): void;
  }

  export function mount(
    canvasEl: HTMLElement,
    sidebarEl: HTMLElement,
    payload: GraphPayload,
    opts?: MountOptions,
  ): MountHandle;

  export function createRenderer(
    container: HTMLElement,
    payload: GraphPayload,
    opts?: MountOptions,
  ): Renderer;

  export function mountSidebar(
    container: HTMLElement,
    renderer: Renderer,
  ): { destroy(): void };
}
