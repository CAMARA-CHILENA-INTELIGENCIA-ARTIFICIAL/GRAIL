import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { mount, type GraphPayload, type MountHandle } from "@grail/viz";
import { api, ApiError } from "../lib/api";
import { useT } from "../lib/i18n";
import { useChatStore } from "../lib/store";
import { RefreshCw, AlertTriangle, Info } from "lucide-react";

type ErrorKind = { kind: "empty" } | { kind: "load"; status?: number };

const DEFAULT_ENTITY_CAP = 5000;
// Pin caps so user choices stay sane.
const CAP_STEPS = [1000, 2500, 5000, 10000, 25000];
const NO_CAP = 0;

export default function KnowledgeGraphView() {
  const canvasRef = useRef<HTMLDivElement>(null);
  const sidebarRef = useRef<HTMLDivElement>(null);
  const handleRef = useRef<MountHandle | null>(null);

  const t = useT();
  const projectName = useChatStore((s) => s.config?.project_name);

  const [loading, setLoading] = useState(true);
  const [errorKind, setErrorKind] = useState<ErrorKind | null>(null);
  const [payload, setPayload] = useState<GraphPayload | null>(null);
  // Effective cap sent to the backend. 0 = no cap.
  const [maxEntities, setMaxEntities] = useState<number>(DEFAULT_ENTITY_CAP);
  // Forces a refetch independent of `maxEntities` changes.
  const [refreshKey, setRefreshKey] = useState(0);

  // Fetch the graph payload. Re-runs when the user changes the cap or
  // clicks Refresh — never on unrelated re-renders.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErrorKind(null);
    setPayload(null);
    (async () => {
      try {
        const url = `/viz/graph?max_entities=${maxEntities}`;
        const data = await api.get<GraphPayload>(url);
        if (cancelled) return;
        setPayload(data);
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiError) {
          setErrorKind(
            e.status === 404 ? { kind: "empty" } : { kind: "load", status: e.status },
          );
        } else {
          setErrorKind({ kind: "load" });
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [maxEntities, refreshKey]);

  // Mount the D3 renderer once the payload is in hand.
  useEffect(() => {
    if (!payload) return;
    const canvas = canvasRef.current;
    const sidebar = sidebarRef.current;
    if (!canvas || !sidebar) return;
    canvas.innerHTML = "";
    sidebar.innerHTML = "";
    const handle = mount(canvas, sidebar, payload);
    handleRef.current = handle;
    return () => {
      handle.destroy();
      handleRef.current = null;
    };
  }, [payload]);

  const errorMessage =
    errorKind == null
      ? null
      : errorKind.kind === "empty"
        ? t("graph.errEmpty")
        : errorKind.status
          ? `${t("graph.errLoad")} (${errorKind.status})`
          : t("graph.errLoad");

  const truncation = payload?.meta.truncation;
  const nextCap = pickNextCap(maxEntities);

  return (
    <motion.div
      className="kg-shell"
      // Opt into the renderer's scoped color tokens (defined under
      // `:where(.grail-viz, [data-grail-viz])` in grail-viz.css). Without
      // this attribute the sidebar text inherits the chat UI's tokens,
      // which don't match — dim text ends up muddy on the panel bg.
      data-grail-viz=""
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
    >
      <div className="kg-header">
        <div className="kg-title">
          <span className="kg-title-text">{t("graph.title")}</span>
          {projectName && <span className="kg-project">{projectName}</span>}
        </div>
        <button
          type="button"
          className="kg-refresh"
          onClick={() => setRefreshKey((k) => k + 1)}
          title={t("graph.refresh")}
          disabled={loading}
        >
          <RefreshCw size={14} className={loading ? "spin" : ""} />
          <span>{t("graph.refresh")}</span>
        </button>
      </div>

      {truncation && !loading && (
        <div className="kg-banner" role="status">
          <Info size={14} />
          <span className="kg-banner-text">
            {t("graph.truncated", {
              kept: truncation.kept_entities.toLocaleString(),
              total: truncation.total_entities.toLocaleString(),
            })}
          </span>
          <div className="kg-banner-actions">
            {nextCap !== null && (
              <button
                type="button"
                onClick={() => setMaxEntities(nextCap)}
                disabled={loading}
              >
                {nextCap === NO_CAP
                  ? t("graph.loadAll")
                  : t("graph.loadMore", { n: nextCap.toLocaleString() })}
              </button>
            )}
          </div>
        </div>
      )}

      <div className="kg-body">
        <div className="kg-canvas-wrap">
          {loading && (
            <div className="kg-status">
              <div className="kg-spinner" />
              <span>{t("graph.loading")}</span>
            </div>
          )}
          {errorMessage && !loading && (
            <div className="kg-status kg-status-error">
              <AlertTriangle size={18} />
              <span>{errorMessage}</span>
            </div>
          )}
          {!errorMessage && <div className="kg-canvas" ref={canvasRef} />}
        </div>
        <div className="kg-sidebar" ref={sidebarRef} />
      </div>
    </motion.div>
  );
}

/** Next cap step above the current value, or NO_CAP after the last step. */
function pickNextCap(current: number): number | null {
  if (current === NO_CAP) return null;
  const next = CAP_STEPS.find((step) => step > current);
  if (next !== undefined) return next;
  return NO_CAP;
}
