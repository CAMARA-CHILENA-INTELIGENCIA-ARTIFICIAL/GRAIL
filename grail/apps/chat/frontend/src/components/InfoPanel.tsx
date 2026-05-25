import { motion, AnimatePresence } from "framer-motion";
import { X, Sparkles, Search, Globe, FileText } from "lucide-react";
import { useChatStore } from "../lib/store";

export default function InfoPanel() {
  const { showInfo, setShowInfo } = useChatStore();

  return (
    <AnimatePresence>
      {showInfo && (
        <>
          {/* Backdrop */}
          <motion.div
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setShowInfo(false)}
          />
          {/* Panel */}
          <motion.div
            className="fixed inset-x-0 bottom-0 z-50 mx-auto max-w-2xl rounded-t-2xl border border-zinc-800 bg-zinc-900 p-6 shadow-2xl"
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ type: "spring", damping: 30, stiffness: 300 }}
          >
            <div className="mb-6 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-zinc-50">
                How search works
              </h2>
              <button
                type="button"
                onClick={() => setShowInfo(false)}
                className="rounded-lg p-1 text-zinc-500 hover:text-zinc-300"
              >
                <X size={20} />
              </button>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              {/* Agent card */}
              <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
                <div className="mb-2 flex items-center gap-2">
                  <Sparkles size={18} className="text-teal-400" />
                  <span className="font-medium text-zinc-100">Agent</span>
                  <span className="ml-auto rounded-full bg-teal-500/10 px-2 py-0.5 text-[10px] font-medium text-teal-400">
                    Recommended
                  </span>
                </div>
                <p className="text-sm leading-relaxed text-zinc-400">
                  AI automatically picks the best search strategy for your
                  question. It can combine local and global searches for the
                  most complete answer.
                </p>
              </div>

              {/* Local card */}
              <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
                <div className="mb-2 flex items-center gap-2">
                  <Search size={18} className="text-teal-400" />
                  <span className="font-medium text-zinc-100">
                    Local Search
                  </span>
                </div>
                <p className="text-sm leading-relaxed text-zinc-400">
                  Finds specific entities, relationships, and facts closest to
                  your query. Best for targeted questions about particular
                  topics.
                </p>
              </div>

              {/* Global card */}
              <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
                <div className="mb-2 flex items-center gap-2">
                  <Globe size={18} className="text-teal-400" />
                  <span className="font-medium text-zinc-100">
                    Global Search
                  </span>
                </div>
                <p className="text-sm leading-relaxed text-zinc-400">
                  Synthesizes themes and patterns across your entire knowledge
                  base. Best for broad, high-level questions.
                </p>
              </div>

              {/* Document scope card */}
              <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
                <div className="mb-2 flex items-center gap-2">
                  <FileText size={18} className="text-teal-400" />
                  <span className="font-medium text-zinc-100">
                    Document Scope
                  </span>
                </div>
                <p className="text-sm leading-relaxed text-zinc-400">
                  Focus your search on a specific document. Select a document
                  using the document button in the toolbar.
                </p>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
