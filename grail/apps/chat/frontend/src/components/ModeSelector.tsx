import { useState, useRef, useEffect } from "react";
import { useChatStore, type SearchMode } from "../lib/store";
import { Sparkles, Search, Globe, FileText, X } from "lucide-react";

// ---------------------------------------------------------------------------
// ModeChips — inline row of mode pill buttons for the input toolbar
// ---------------------------------------------------------------------------

export function ModeChips() {
  const { currentMode, setMode, useRerankerMode, setUseRerankerMode, config } =
    useChatStore();

  const modes: {
    id: string;
    label: string;
    icon: typeof Search;
    recommended?: boolean;
  }[] = [
    { id: "agent", label: "Agent", icon: Sparkles, recommended: true },
    { id: "local", label: "Local", icon: Search },
    ...(config?.has_reranker
      ? [{ id: "local_rerank", label: "Local+Rerank", icon: Search }]
      : []),
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

  const activeId =
    currentMode === "local" && useRerankerMode ? "local_rerank" : currentMode;

  return (
    <div className="flex items-center gap-1">
      {modes.map((mode) => {
        const Icon = mode.icon;
        const isActive = activeId === mode.id;
        return (
          <button
            key={mode.id}
            type="button"
            onClick={() => handleSelect(mode.id)}
            className={`flex items-center gap-1 rounded-full px-2.5 py-1 text-xs transition-colors ${
              isActive
                ? "border border-teal-500/30 bg-teal-500/15 text-teal-400"
                : "border border-transparent text-zinc-500 hover:bg-zinc-800/50 hover:text-zinc-300"
            }`}
          >
            <Icon size={12} />
            <span>{mode.label}</span>
            {mode.recommended && (
              <span className="text-[9px] text-amber-400">&#9733;</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// DocumentScope — document scope button + dropdown picker
// ---------------------------------------------------------------------------

export function DocumentScope() {
  const { documents, documentScope, setDocumentScope } = useChatStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Nothing to render if no documents are indexed
  if (documents.length === 0) return null;

  return (
    <div className="relative" ref={ref}>
      {documentScope ? (
        /* Active document chip */
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-1.5 rounded-full border border-teal-500/30 bg-teal-500/10 px-2.5 py-1 text-xs text-teal-400"
        >
          <FileText size={12} />
          <span className="max-w-[100px] truncate">{documentScope}</span>
          <X
            size={11}
            className="text-zinc-500 hover:text-zinc-300"
            onClick={(e) => {
              e.stopPropagation();
              setDocumentScope(null);
            }}
          />
        </button>
      ) : (
        /* Subtle icon button to open picker */
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex h-7 w-7 items-center justify-center rounded-full text-zinc-500 hover:bg-zinc-800/50 hover:text-zinc-300"
          title="Scope to a document"
        >
          <FileText size={14} />
        </button>
      )}

      {/* Dropdown */}
      {open && (
        <div className="absolute bottom-full left-0 z-50 mb-2 w-72 overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900 shadow-lg shadow-black/40">
          <div className="border-b border-zinc-800 px-4 py-2">
            <span className="text-xs font-medium uppercase tracking-wider text-zinc-500">
              Select document
            </span>
          </div>
          <div className="max-h-60 overflow-y-auto">
            {/* Clear option */}
            {documentScope && (
              <button
                type="button"
                onClick={() => {
                  setDocumentScope(null);
                  setOpen(false);
                }}
                className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm text-zinc-400 hover:bg-zinc-800"
              >
                <X size={14} className="flex-shrink-0" />
                Clear document scope
              </button>
            )}
            {documents.map((doc) => {
              const isActive = doc.title === documentScope;
              return (
                <button
                  key={doc.id}
                  type="button"
                  onClick={() => {
                    setDocumentScope(doc.title);
                    setOpen(false);
                  }}
                  className={`flex w-full items-start gap-3 px-4 py-2.5 text-left hover:bg-zinc-800 ${
                    isActive ? "bg-zinc-800" : ""
                  }`}
                >
                  <FileText
                    size={16}
                    className={`mt-0.5 flex-shrink-0 ${isActive ? "text-teal-400" : "text-zinc-500"}`}
                  />
                  <div className="min-w-0 flex-1">
                    <div
                      className={`truncate text-sm ${isActive ? "text-teal-400" : "text-zinc-200"}`}
                    >
                      {doc.title}
                    </div>
                    {doc.path && doc.path !== doc.title && (
                      <div className="truncate text-xs text-zinc-600">
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
