import { motion } from "framer-motion";
import { Workflow, LocateFixed, Globe, Star, Layers, UserSearch, GitCompare, Database } from "lucide-react";
import { useChatStore, type SearchMode } from "../lib/store";
import { useT } from "../lib/i18n";
import type { StringKey } from "../lib/i18n";

const ease = [0.25, 0.4, 0.25, 1] as const;

const CARDS: {
  id: SearchMode;
  icon: typeof Workflow;
  titleKey: StringKey;
  descKey: StringKey;
  recommended?: boolean;
}[] = [
  {
    id: "agent",
    icon: Workflow,
    titleKey: "welcome.cardAgentTitle",
    descKey: "welcome.cardAgentDesc",
    recommended: true,
  },
  {
    id: "local",
    icon: LocateFixed,
    titleKey: "welcome.cardLocalTitle",
    descKey: "welcome.cardLocalDesc",
  },
  {
    id: "global",
    icon: Globe,
    titleKey: "welcome.cardGlobalTitle",
    descKey: "welcome.cardGlobalDesc",
  },
];

const SAMPLE_PROMPTS: { icon: typeof Layers; key: StringKey }[] = [
  { icon: Layers, key: "welcome.sample1" },
  { icon: UserSearch, key: "welcome.sample2" },
  { icon: GitCompare, key: "welcome.sample3" },
];

export default function WelcomeView() {
  const { currentMode, setMode, setUseRerankerMode, setDraftInput, config } = useChatStore();
  const t = useT();

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
        {t("welcome.lede1")} <em>{t("welcome.lede2")}</em>
      </motion.h1>

      <motion.p
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease, delay: 0.14 }}
        className="sub"
      >
        {t("welcome.sub")}
      </motion.p>

      {config?.project_name && (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease, delay: 0.18 }}
          className="project-chip"
          title={config.project_path || config.project_name}
        >
          <Database size={12} />
          {t("welcome.connectedTo")} <b>{config.project_name}</b>
        </motion.div>
      )}

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
                  {t("welcome.recommended")}
                </span>
              )}
              <div className="mc-ico">
                <Icon size={17} />
              </div>
              <div className="mc-title">{t(card.titleKey)}</div>
              <div className="mc-desc">{t(card.descKey)}</div>
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
          const text = t(p.key);
          return (
            <button
              key={p.key}
              type="button"
              className="sample-chip"
              onClick={() => handleSampleClick(text)}
            >
              <Icon size={13} />
              {text}
            </button>
          );
        })}
      </motion.div>
    </section>
  );
}
