import { motion } from "framer-motion";
import { Sparkles, Search, Globe, ArrowRight } from "lucide-react";
import { useSessionStore, useChatStore, type SearchMode } from "../lib/store";
import ChatInput from "./ChatInput";

const ease = [0.25, 0.4, 0.25, 1] as const;

const CARDS = [
  {
    id: "agent" as SearchMode,
    icon: Sparkles,
    title: "Agent",
    description: "AI picks the right search strategy for your question automatically.",
    recommended: true,
  },
  {
    id: "local" as SearchMode,
    icon: Search,
    title: "Local Search",
    description: "Find specific entities, relationships, and facts in your knowledge base.",
  },
  {
    id: "global" as SearchMode,
    icon: Globe,
    title: "Global Search",
    description: "Discover broad themes and patterns across your entire knowledge base.",
  },
];

export default function WelcomeView() {
  const { createSession } = useSessionStore();
  const { currentMode, setMode, setUseRerankerMode, sendMessage } = useChatStore();

  async function handleSend(message: string) {
    const session = await createSession(currentMode);
    sendMessage(message, session.id);
  }

  function handleCardClick(mode: SearchMode) {
    setMode(mode);
    setUseRerankerMode(false);
  }

  return (
    <div className="flex h-full flex-col items-center justify-center px-4">
      <div className="mx-auto flex w-full max-w-2xl flex-col items-center gap-6">
        {/* Logo mark */}
        <motion.div
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.6, ease }}
          className="flex h-14 w-14 items-center justify-center rounded-2xl"
          style={{
            background: "var(--accent-soft)",
            border: "1px solid var(--accent-border)",
            boxShadow: "0 0 40px -8px rgba(20, 184, 166, 0.2)",
          }}
        >
          <Sparkles size={24} style={{ color: "var(--accent)" }} />
        </motion.div>

        {/* Title */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease, delay: 0.1 }}
          className="text-center"
        >
          <h1
            className="text-3xl font-bold tracking-tight sm:text-4xl"
            style={{ color: "var(--text-primary)", letterSpacing: "-0.025em" }}
          >
            What do you want to{" "}
            <span
              style={{
                background: "linear-gradient(135deg, #5eead4 0%, #14b8a6 50%, #0d9488 100%)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
              }}
            >
              discover
            </span>
            ?
          </h1>
          <p className="mt-2 text-base" style={{ color: "var(--text-secondary)" }}>
            Ask anything about your knowledge graph
          </p>
        </motion.div>

        {/* Input */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease, delay: 0.2 }}
          className="w-full"
        >
          <ChatInput onSend={handleSend} />
        </motion.div>

        {/* Mode cards */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease, delay: 0.3 }}
          className="mt-1 grid w-full grid-cols-1 gap-3 sm:grid-cols-3"
        >
          {CARDS.map((card, i) => {
            const Icon = card.icon;
            const isActive = currentMode === card.id;
            return (
              <motion.button
                key={card.id}
                type="button"
                onClick={() => handleCardClick(card.id)}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, ease, delay: 0.35 + i * 0.06 }}
                whileHover={{ y: -2, transition: { duration: 0.2 } }}
                className="group flex flex-col items-start rounded-xl p-4 text-left transition-all duration-200"
                style={{
                  background: isActive ? "var(--accent-soft)" : "var(--surface-1)",
                  border: `1px solid ${isActive ? "var(--accent-border)" : "var(--border)"}`,
                  ...(isActive ? { boxShadow: "0 0 24px -6px rgba(20, 184, 166, 0.12)" } : {}),
                }}
                onMouseEnter={(e) => {
                  if (!isActive) {
                    e.currentTarget.style.borderColor = "var(--border)";
                    e.currentTarget.style.background = "var(--surface-2)";
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isActive) {
                    e.currentTarget.style.borderColor = "var(--border)";
                    e.currentTarget.style.background = "var(--surface-1)";
                  }
                }}
              >
                <div className="mb-3 flex w-full items-center gap-2">
                  <div
                    className="flex h-7 w-7 items-center justify-center rounded-lg"
                    style={{
                      background: isActive ? "rgba(20,184,166,0.15)" : "var(--surface-3)",
                    }}
                  >
                    <Icon size={14} style={{ color: isActive ? "var(--accent)" : "var(--text-tertiary)" }} />
                  </div>
                  <span
                    className="text-sm font-medium"
                    style={{ color: isActive ? "var(--accent)" : "var(--text-primary)" }}
                  >
                    {card.title}
                  </span>
                  {card.recommended && (
                    <span
                      className="ml-auto rounded-full px-2 py-0.5 text-[10px] font-medium"
                      style={{
                        background: "var(--accent-soft)",
                        color: "var(--accent)",
                        border: "1px solid var(--accent-border)",
                      }}
                    >
                      Recommended
                    </span>
                  )}
                </div>
                <p className="text-xs leading-relaxed" style={{ color: "var(--text-tertiary)" }}>
                  {card.description}
                </p>
                <div
                  className="mt-3 flex items-center gap-1 text-[11px] font-medium opacity-0 transition-opacity duration-200 group-hover:opacity-100"
                  style={{ color: "var(--accent)" }}
                >
                  Select <ArrowRight size={10} />
                </div>
              </motion.button>
            );
          })}
        </motion.div>
      </div>
    </div>
  );
}
