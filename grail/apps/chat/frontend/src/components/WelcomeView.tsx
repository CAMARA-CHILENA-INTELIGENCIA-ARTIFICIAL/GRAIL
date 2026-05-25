import { motion } from "framer-motion";
import { Sparkles, Search, Globe } from "lucide-react";
import { useSessionStore, useChatStore, type SearchMode } from "../lib/store";
import ChatInput from "./ChatInput";

const ease = [0.25, 0.4, 0.25, 1] as const;

const CARDS = [
  {
    id: "agent" as SearchMode,
    icon: Sparkles,
    title: "Agent",
    description: "Best for most queries. AI picks the right strategy.",
    recommended: true,
  },
  {
    id: "local" as SearchMode,
    icon: Search,
    title: "Local",
    description: "Find specific entities, relationships, and facts.",
  },
  {
    id: "global" as SearchMode,
    icon: Globe,
    title: "Global",
    description: "Broad themes and patterns across the knowledge base.",
  },
];

export default function WelcomeView() {
  const { createSession } = useSessionStore();
  const { currentMode, setMode, setUseRerankerMode, sendMessage } =
    useChatStore();

  async function handleSend(message: string) {
    const session = await createSession(currentMode);
    sendMessage(message, session.id);
  }

  function handleCardClick(mode: SearchMode) {
    setMode(mode);
    setUseRerankerMode(false);
  }

  return (
    <div className="flex h-full flex-col items-center justify-center">
      <div className="mx-auto flex w-full max-w-2xl flex-col items-center gap-4 px-4">
        {/* Title */}
        <motion.h1
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease }}
          className="text-balance text-center text-3xl font-bold tracking-tight sm:text-4xl md:text-[46px]"
          style={{
            background:
              "linear-gradient(135deg, #5eead4, #14b8a6, #0d9488)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}
        >
          Search. Discover. Learn.
        </motion.h1>

        {/* Subtitle */}
        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease, delay: 0.1 }}
          className="-mt-1 pb-2 text-center text-lg text-zinc-400"
        >
          Your knowledge graph, one question away
        </motion.p>

        {/* Input */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease, delay: 0.2 }}
          className="w-full"
        >
          <ChatInput onSend={handleSend} />
        </motion.div>

        {/* Explanation cards */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease, delay: 0.3 }}
          className="mt-2 grid w-full grid-cols-3 gap-3"
        >
          {CARDS.map((card, i) => {
            const Icon = card.icon;
            const isActive = currentMode === card.id;
            return (
              <motion.button
                key={card.id}
                type="button"
                onClick={() => handleCardClick(card.id)}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, ease, delay: 0.35 + i * 0.05 }}
                whileHover={{ scale: 1.02 }}
                className={`flex flex-col items-start rounded-xl border p-4 text-left transition-colors ${
                  isActive
                    ? "border-teal-500/40 bg-teal-500/5"
                    : "border-zinc-800 bg-zinc-900/50 hover:border-zinc-700 hover:bg-zinc-900"
                }`}
              >
                <div className="mb-2 flex w-full items-center gap-2">
                  <Icon
                    size={16}
                    className={isActive ? "text-teal-400" : "text-zinc-500"}
                  />
                  <span
                    className={`text-sm font-medium ${isActive ? "text-teal-400" : "text-zinc-300"}`}
                  >
                    {card.title}
                  </span>
                  {card.recommended && (
                    <span className="ml-auto rounded-full bg-teal-500/10 px-1.5 py-0.5 text-[9px] font-medium text-teal-400">
                      Recommended
                    </span>
                  )}
                </div>
                <p className="text-xs leading-relaxed text-zinc-500">
                  {card.description}
                </p>
              </motion.button>
            );
          })}
        </motion.div>
      </div>
    </div>
  );
}
