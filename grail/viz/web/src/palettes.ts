/**
 * Color lookup helpers driven by the meta payload.
 *
 * Provided by Nirvai (Nirvana). Author: Benjamín González Guerrero.
 */

import type { ColorMode, Meta, NodeAttrs } from "./types";

const DEFAULT_KIND_COLORS: Record<string, string> = {
  entity: "#7c5cff",
  document: "#7aa2f7",
  chunk: "#9aa5b1",
  community: "#bb9af7",
  finding: "#e0af68",
};

export const FALLBACK_COMMUNITY_COLOR = "#666c79";
export const FALLBACK_TYPE_COLOR = "#7c5cff";

export function colorForKind(kind: string, meta: Meta): string {
  return meta.kind_palette?.[kind] ?? DEFAULT_KIND_COLORS[kind] ?? "#7c5cff";
}

export function colorForCommunity(cid: string | undefined, meta: Meta): string {
  if (!cid) return FALLBACK_COMMUNITY_COLOR;
  return meta.community_palette?.[cid] ?? FALLBACK_COMMUNITY_COLOR;
}

export function colorForType(type: string | undefined, meta: Meta): string {
  if (!type) return FALLBACK_TYPE_COLOR;
  return meta.type_palette?.[type] ?? FALLBACK_TYPE_COLOR;
}

/**
 * Pick the rendered color for a node given the current color mode.
 *
 * For entities, the toggle switches between community and type colors.
 * For all other kinds, the precomputed `color` field wins because the
 * exporter already chose a sensible value (community color for communities
 * and findings, kind color for documents and chunks).
 */
export function pickNodeColor(attrs: NodeAttrs, mode: ColorMode): string {
  if (attrs._kind !== "entity") return attrs.color;
  return mode === "community" ? attrs.communityColor : attrs.typeColor;
}

/**
 * Append an 8-bit alpha to a #RRGGBB color. Used to dim non-incident edges
 * on hover and to fade community-colored intra-cluster edge halos.
 */
export function withAlpha(hex: string, alpha: number): string {
  if (!hex.startsWith("#") || hex.length !== 7) return hex;
  const clamped = Math.max(0, Math.min(255, Math.round(alpha * 255)));
  return hex + clamped.toString(16).padStart(2, "0");
}
