/**
 * Public entry point.
 *
 * Provided by Nirvai (Nirvana). Author: Benjamín González Guerrero.
 *
 * Consumed by:
 *   - grail/viz/template.py (UMD bundle inlined into a self-contained HTML)
 *   - grail/apps/chat/frontend/src/components/KnowledgeGraphView.tsx (ESM
 *     via vite path alias)
 */

import "./styles.css";
import { createRenderer } from "./renderer";
import { mountSidebar } from "./controls";
import type { GraphPayload, MountOptions, Renderer } from "./types";

export type {
  GraphPayload,
  Meta,
  NodeAttrs,
  EdgeAttrs,
  RawNode,
  RawEdge,
  NodeKind,
  EdgeKind,
  ColorMode,
  MountOptions,
  Renderer,
  ForceSettings,
} from "./types";

export { createRenderer, mountSidebar };

/**
 * Convenience helper: mount renderer + sidebar in standard layout.
 *
 * The container should already have two children: a canvas div (for the
 * graph) and a sidebar div (for the controls). If `container` has only one
 * child, a sidebar is created next to it.
 *
 * Returns a handle the embedder uses to clean up.
 */
export interface MountHandle {
  renderer: Renderer;
  destroy(): void;
}

export function mount(
  canvasEl: HTMLElement,
  sidebarEl: HTMLElement,
  payload: GraphPayload,
  opts: MountOptions = {},
): MountHandle {
  const renderer = createRenderer(canvasEl, payload, opts);
  const sidebar = mountSidebar(sidebarEl, renderer);
  return {
    renderer,
    destroy() {
      sidebar.destroy();
      renderer.destroy();
    },
  };
}
