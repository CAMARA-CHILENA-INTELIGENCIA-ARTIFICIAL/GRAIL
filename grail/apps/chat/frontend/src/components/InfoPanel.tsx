import { motion, AnimatePresence } from "framer-motion";
import { X, Sparkles, Search, Globe, FileText } from "lucide-react";
import { useChatStore } from "../lib/store";

const MODES = [
  {
    icon: Sparkles,
    title: "Agent",
    badge: "Recommended",
    description: "AI automatically picks the best search strategy. It can combine local and global searches for the most complete answer.",
  },
  {
    icon: Search,
    title: "Local Search",
    description: "Finds specific entities, relationships, and facts closest to your query. Best for targeted questions about particular topics.",
  },
  {
    icon: Globe,
    title: "Global Search",
    description: "Synthesizes themes and patterns across your entire knowledge base. Best for broad, high-level questions.",
  },
  {
    icon: FileText,
    title: "Document Scope",
    description: "Focus your search on a specific document. Select a document using the document button in the toolbar.",
  },
];

export default function InfoPanel() {
  const { showInfo, setShowInfo } = useChatStore();

  return (
    <AnimatePresence>
      {showInfo && (
        <>
          <motion.div
            className="fixed inset-0 z-50"
            style={{ background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)" }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setShowInfo(false)}
          />
          <motion.div
            className="fixed inset-x-0 bottom-0 z-50 mx-auto max-w-2xl rounded-t-2xl p-6"
            style={{
              background: "var(--surface-1)",
              border: "1px solid var(--border)",
              borderBottom: "none",
              boxShadow: "0 -8px 40px -8px rgba(0,0,0,0.5)",
            }}
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ type: "spring", damping: 30, stiffness: 300 }}
          >
            <div className="mb-5 flex items-center justify-between">
              <h2 className="text-base font-semibold" style={{ color: "var(--text-primary)" }}>
                How search works
              </h2>
              <button
                type="button"
                onClick={() => setShowInfo(false)}
                className="rounded-lg p-1 transition-colors duration-150"
                style={{ color: "var(--text-tertiary)" }}
                onMouseEnter={(e) => { e.currentTarget.style.color = "var(--text-primary)"; }}
                onMouseLeave={(e) => { e.currentTarget.style.color = "var(--text-tertiary)"; }}
              >
                <X size={18} />
              </button>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              {MODES.map((mode, i) => {
                const Icon = mode.icon;
                return (
                  <motion.div
                    key={mode.title}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.05 * i, duration: 0.3 }}
                    className="rounded-xl p-4"
                    style={{
                      background: "var(--surface-0)",
                      border: "1px solid var(--border-subtle)",
                    }}
                  >
                    <div className="mb-2 flex items-center gap-2">
                      <div
                        className="flex h-6 w-6 items-center justify-center rounded-lg"
                        style={{ background: "var(--accent-soft)" }}
                      >
                        <Icon size={13} style={{ color: "var(--accent)" }} />
                      </div>
                      <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                        {mode.title}
                      </span>
                      {mode.badge && (
                        <span
                          className="ml-auto rounded-full px-1.5 py-0.5 text-[9px] font-medium"
                          style={{ background: "var(--accent-soft)", color: "var(--accent)", border: "1px solid var(--accent-border)" }}
                        >
                          {mode.badge}
                        </span>
                      )}
                    </div>
                    <p className="text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                      {mode.description}
                    </p>
                  </motion.div>
                );
              })}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
