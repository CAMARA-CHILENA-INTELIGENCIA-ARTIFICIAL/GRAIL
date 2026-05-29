import { useState, useRef, useEffect } from "react";
import { useChatStore, type SearchMode } from "../lib/store";
import { Sparkles, Search, Globe, FileText, X } from "lucide-react";

export function ModeChips() {
  const { currentMode, setMode, useRerankerMode, setUseRerankerMode, config } = useChatStore();

  const modes: { id: string; label: string; icon: typeof Search; recommended?: boolean }[] = [
    { id: "agent", label: "Agent", icon: Sparkles, recommended: true },
    { id: "local", label: "Local", icon: Search },
    ...(config?.has_reranker ? [{ id: "local_rerank", label: "Rerank", icon: Search }] : []),
    { id: "global", label: "Global", icon: Globe },
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
    <div className="flex items-center gap-0.5">
      {modes.map((mode) => {
        const Icon = mode.icon;
        const isActive = activeId === mode.id;
        return (
          <button
            key={mode.id}
            type="button"
            onClick={() => handleSelect(mode.id)}
            className="flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-medium transition-all duration-150"
            style={{
              background: isActive ? "var(--accent-soft)" : "transparent",
              border: `1px solid ${isActive ? "var(--accent-border)" : "transparent"}`,
              color: isActive ? "var(--accent)" : "var(--text-tertiary)",
            }}
            onMouseEnter={(e) => {
              if (!isActive) {
                e.currentTarget.style.background = "var(--surface-3)";
                e.currentTarget.style.color = "var(--text-secondary)";
              }
            }}
            onMouseLeave={(e) => {
              if (!isActive) {
                e.currentTarget.style.background = "transparent";
                e.currentTarget.style.color = "var(--text-tertiary)";
              }
            }}
          >
            <Icon size={11} />
            <span>{mode.label}</span>
            {mode.recommended && (
              <span className="text-[8px]" style={{ color: "#f59e0b" }}>&#9733;</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function DocumentScope() {
  const { documents, documentScope, setDocumentScope } = useChatStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  if (documents.length === 0) return null;

  return (
    <div className="relative" ref={ref}>
      {documentScope ? (
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-[11px] font-medium transition-all duration-150"
          style={{
            background: "var(--accent-soft)",
            border: "1px solid var(--accent-border)",
            color: "var(--accent)",
          }}
        >
          <FileText size={11} />
          <span className="max-w-[90px] truncate">{documentScope}</span>
          <X
            size={10}
            style={{ color: "var(--text-tertiary)" }}
            onClick={(e) => { e.stopPropagation(); setDocumentScope(null); }}
            onMouseEnter={(e) => { e.currentTarget.style.color = "var(--text-primary)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.color = "var(--text-tertiary)"; }}
          />
        </button>
      ) : (
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex h-7 w-7 items-center justify-center rounded-lg transition-colors duration-150"
          style={{ color: "var(--text-tertiary)" }}
          onMouseEnter={(e) => { e.currentTarget.style.background = "var(--surface-3)"; e.currentTarget.style.color = "var(--text-secondary)"; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--text-tertiary)"; }}
          title="Scope to a document"
        >
          <FileText size={14} />
        </button>
      )}

      {open && (
        <div
          className="absolute bottom-full left-0 z-50 mb-2 w-72 overflow-hidden rounded-xl shadow-xl"
          style={{
            background: "var(--surface-1)",
            border: "1px solid var(--border)",
            boxShadow: "0 8px 32px -4px rgba(0,0,0,0.5)",
          }}
        >
          <div className="px-4 py-2.5" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
            <span
              className="text-[10px] font-semibold uppercase tracking-widest"
              style={{ color: "var(--text-tertiary)" }}
            >
              Select document
            </span>
          </div>
          <div className="max-h-60 overflow-y-auto py-1">
            {documentScope && (
              <button
                type="button"
                onClick={() => { setDocumentScope(null); setOpen(false); }}
                className="flex w-full items-center gap-3 px-4 py-2 text-left text-sm transition-colors duration-100"
                style={{ color: "var(--text-secondary)" }}
                onMouseEnter={(e) => { e.currentTarget.style.background = "var(--surface-2)"; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
              >
                <X size={13} className="flex-shrink-0" />
                Clear scope
              </button>
            )}
            {documents.map((doc) => {
              const isActive = doc.title === documentScope;
              return (
                <button
                  key={doc.id}
                  type="button"
                  onClick={() => { setDocumentScope(doc.title); setOpen(false); }}
                  className="flex w-full items-start gap-3 px-4 py-2 text-left transition-colors duration-100"
                  style={{ background: isActive ? "var(--accent-soft)" : "transparent" }}
                  onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.background = "var(--surface-2)"; }}
                  onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.background = isActive ? "var(--accent-soft)" : "transparent"; }}
                >
                  <FileText
                    size={14}
                    className="mt-0.5 flex-shrink-0"
                    style={{ color: isActive ? "var(--accent)" : "var(--text-tertiary)" }}
                  />
                  <div className="min-w-0 flex-1">
                    <div
                      className="truncate text-sm"
                      style={{ color: isActive ? "var(--accent)" : "var(--text-primary)" }}
                    >
                      {doc.title}
                    </div>
                    {doc.path && doc.path !== doc.title && (
                      <div className="truncate text-[11px]" style={{ color: "var(--text-tertiary)" }}>
                        {doc.path}
                      </div>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
