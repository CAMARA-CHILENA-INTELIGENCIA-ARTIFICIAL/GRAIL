import { motion } from "framer-motion";
import { Workflow, LocateFixed, Globe, Star, Layers, UserSearch, GitCompare } from "lucide-react";
import { useChatStore, type SearchMode } from "../lib/store";

const ease = [0.25, 0.4, 0.25, 1] as const;

const CARDS: {
  id: SearchMode;
  icon: typeof Workflow;
  title: string;
  description: string;
  recommended?: boolean;
}[] = [
  {
    id: "agent",
    icon: Workflow,
    title: "Agent",
    description:
      "Lets GRAIL decide which searches to run and chain them — best for open-ended questions.",
    recommended: true,
  },
  {
    id: "local",
    icon: LocateFixed,
    title: "Local",
    description:
      "Walks the neighborhood around specific entities. Best for precise, grounded lookups.",
  },
  {
    id: "global",
    icon: Globe,
    title: "Global",
    description:
      "Map-reduces over community reports. Best for broad themes across the whole corpus.",
  },
];

const SAMPLE_PROMPTS: { icon: typeof Layers; text: string }[] = [
  { icon: Layers, text: "What are the main themes across my documents?" },
  { icon: UserSearch, text: "Who is mentioned most in the corpus?" },
  { icon: GitCompare, text: "Summarize what changed between versions." },
];

export default function WelcomeView() {
  const { currentMode, setMode, setUseRerankerMode, setDraftInput } = useChatStore();

  function handleCardClick(mode: SearchMode) {
    setMode(mode);
    setUseRerankerMode(false);
  }

  function handleSampleClick(text: string) {
    setDraftInput(text);
  }

  return (
    <section className="welcome">
      <motion.img
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 0.96, y: 0 }}
        transition={{ duration: 0.5, ease }}
        className="logo"
        src="/assets/grail_logotype.png"
        alt="GRAIL — GraphRAG with Advanced Integration and Learning"
      />

      <motion.h1
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease, delay: 0.08 }}
        className="lede"
      >
        Ask your <em>knowledge graph.</em>
      </motion.h1>

      <motion.p
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease, delay: 0.14 }}
        className="sub"
      >
        GRAIL turns your documents into a graph of entities and relationships — then answers
        from it, with sources you can trace.
      </motion.p>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease, delay: 0.2 }}
        className="mode-cards"
      >
        {CARDS.map((card, i) => {
          const Icon = card.icon;
          const isActive = currentMode === card.id;
          return (
            <motion.button
              key={card.id}
              type="button"
              onClick={() => handleCardClick(card.id)}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, ease, delay: 0.26 + i * 0.05 }}
              className={`mcard ${card.recommended ? "rec" : ""} ${isActive ? "active" : ""}`}
            >
              {card.recommended && (
                <span className="mc-badge">
                  <Star size={11} />
                  Recommended
                </span>
              )}
              <div className="mc-ico">
                <Icon size={17} />
              </div>
              <div className="mc-title">{card.title}</div>
              <div className="mc-desc">{card.description}</div>
            </motion.button>
          );
        })}
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease, delay: 0.42 }}
        className="sample-chips"
      >
        {SAMPLE_PROMPTS.map((p) => {
          const Icon = p.icon;
          return (
            <button
              key={p.text}
              type="button"
              className="sample-chip"
              onClick={() => handleSampleClick(p.text)}
            >
              <Icon size={13} />
              {p.text}
            </button>
          );
        })}
      </motion.div>
    </section>
  );
}
