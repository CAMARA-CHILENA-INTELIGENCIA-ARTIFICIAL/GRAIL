import { motion, AnimatePresence } from "framer-motion";
import { X, Workflow, LocateFixed, Globe, Layers2 } from "lucide-react";
import { useChatStore } from "../lib/store";

const MODES = [
  {
    Icon: Workflow,
    title: "Agent",
    tag: "recommended",
    description:
      "An LLM loop that decides which searches to run and chains them. Best when the question spans entities and themes, or you're not sure where to look.",
  },
  {
    Icon: LocateFixed,
    title: "Local",
    tag: "entity-first",
    description:
      "Anchors on the entities in your question and walks their neighborhood — relationships, attributes, and the chunks that mention them. Precise and grounded.",
  },
  {
    Icon: Globe,
    title: "Global",
    tag: "theme-first",
    description:
      "Map-reduces across community reports built during indexing. Best for broad, corpus-wide questions where no single entity holds the answer.",
  },
  {
    Icon: Layers2,
    title: "Rerank",
    tag: "optional",
    description:
      "When a reranker is configured, candidate passages are re-scored for relevance before synthesis — sharpening citations on dense corpora.",
  },
];

export default function InfoPanel() {
  const { showInfo, setShowInfo } = useChatStore();

  return (
    <AnimatePresence>
      {showInfo && (
        <>
          <motion.div
            className="scrim"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            onClick={() => setShowInfo(false)}
          />
          <motion.div
            className="sheet"
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ type: "spring", damping: 30, stiffness: 300 }}
          >
            <div className="sheet-inner">
              <div className="sheet-grip" />
              <div className="sheet-head">
                <img className="glyph" src="/assets/grail_isotype.png" alt="" />
                <div>
                  <h2>How search works</h2>
                  <p>GRAIL chooses how to traverse your graph. Four modes, one knowledge base.</p>
                </div>
                <button
                  type="button"
                  className="close"
                  onClick={() => setShowInfo(false)}
                  aria-label="Close"
                >
                  <X size={18} />
                </button>
              </div>
              <div className="mode-grid">
                {MODES.map((mode, i) => {
                  const Icon = mode.Icon;
                  return (
                    <motion.div
                      key={mode.title}
                      className="mode-tile"
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.04, duration: 0.25 }}
                    >
                      <div className="mt-ico">
                        <Icon size={16} />
                      </div>
                      <h3>
                        {mode.title} <span className="tag">{mode.tag}</span>
                      </h3>
                      <p>{mode.description}</p>
                    </motion.div>
                  );
                })}
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
