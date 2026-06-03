import { useEffect, useRef } from "react";
import { useChatStore, type SearchMode } from "../lib/store";
import { Workflow, LocateFixed, Globe, Layers2, FileText, X } from "lucide-react";

export function ModeChips() {
  const { currentMode, setMode, useRerankerMode, setUseRerankerMode, config } = useChatStore();

  const modes: { id: string; label: string; Icon: typeof Workflow; recommended?: boolean }[] = [
    { id: "agent", label: "Agent", Icon: Workflow, recommended: true },
    { id: "local", label: "Local", Icon: LocateFixed },
    ...(config?.has_reranker ? [{ id: "local_rerank", label: "Rerank", Icon: Layers2 }] : []),
    { id: "global", label: "Global", Icon: Globe },
  ];

  function handleSelect(id: string) {
    if (id === "local_rerank") {
      setMode("local");
      setUseRerankerMode(true);
    } else {
      setMode(id as SearchMode);
      setUseRerankerMode(false);
    }
  }

  const activeId = currentMode === "local" && useRerankerMode ? "local_rerank" : currentMode;

  return (
    <div className="mode-chips">
      {modes.map((mode) => {
        const { Icon } = mode;
        const isActive = activeId === mode.id;
        return (
          <button
            key={mode.id}
            type="button"
            onClick={() => handleSelect(mode.id)}
            className={`chip ${isActive ? "active" : ""}`}
          >
            <Icon size={12} />
            <span>{mode.label}</span>
            {mode.recommended && <span className="star">★</span>}
          </button>
        );
      })}
    </div>
  );
}

export function DocumentScopePill() {
  const { documentScope, setDocumentScope } = useChatStore();
  if (!documentScope) return null;
  return (
    <div className="docscope">
      <span className="scope-pill">
        <FileText size={13} />
        {documentScope}
        <button
          type="button"
          className="x"
          onClick={() => setDocumentScope(null)}
          aria-label="Clear document scope"
        >
          <X size={11} />
        </button>
      </span>
    </div>
  );
}

interface DocumentPickerProps {
  onClose: () => void;
}

export function DocumentPicker({ onClose }: DocumentPickerProps) {
  const { documents, documentScope, setDocumentScope } = useChatStore();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [onClose]);

  return (
    <div className="doc-popup" ref={ref}>
      <div className="popup-head">
        <span>Select document</span>
      </div>
      <div className="popup-list">
        {documentScope && (
          <button
            type="button"
            className="popup-item"
            onClick={() => {
              setDocumentScope(null);
              onClose();
            }}
          >
            <X size={13} style={{ marginTop: 2, color: "var(--text-tertiary)" }} />
            <div className="doc-name" style={{ color: "var(--text-secondary)" }}>
              Clear scope
            </div>
          </button>
        )}
        {documents.map((doc) => {
          const isActive = doc.title === documentScope;
          return (
            <button
              key={doc.id}
              type="button"
              className={`popup-item ${isActive ? "active" : ""}`}
              onClick={() => {
                setDocumentScope(doc.title);
                onClose();
              }}
            >
              <FileText size={13} style={{ marginTop: 2, color: isActive ? "var(--accent)" : "var(--text-tertiary)", flex: "0 0 auto" }} />
              <div style={{ minWidth: 0 }}>
                <div className="doc-name">{doc.title}</div>
                {doc.path && doc.path !== doc.title && (
                  <div className="doc-path">{doc.path}</div>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
