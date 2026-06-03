import { motion, AnimatePresence } from "framer-motion";
import { X, Workflow, LocateFixed, Globe, Layers2, Combine } from "lucide-react";
import { useChatStore } from "../lib/store";
import { useT } from "../lib/i18n";
import type { StringKey } from "../lib/i18n";

const MODES: {
  Icon: typeof Workflow;
  titleKey: StringKey;
  tagKey: StringKey;
  descKey: StringKey;
}[] = [
  {
    Icon: Workflow,
    titleKey: "mode.agent",
    tagKey: "info.tagRecommended",
    descKey: "info.agentDesc",
  },
  {
    Icon: LocateFixed,
    titleKey: "mode.local",
    tagKey: "info.tagEntityFirst",
    descKey: "info.localDesc",
  },
  {
    Icon: Combine,
    titleKey: "mode.cascade",
    tagKey: "info.tagHybrid",
    descKey: "info.cascadeDesc",
  },
  {
    Icon: Globe,
    titleKey: "mode.global",
    tagKey: "info.tagThemeFirst",
    descKey: "info.globalDesc",
  },
  {
    Icon: Layers2,
    titleKey: "mode.rerank",
    tagKey: "info.tagOptional",
    descKey: "info.rerankDesc",
  },
];

export default function InfoPanel() {
  const { showInfo, setShowInfo } = useChatStore();
  const t = useT();

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
                  <h2>{t("info.title")}</h2>
                  <p>{t("info.sub")}</p>
                </div>
                <button
                  type="button"
                  className="close"
                  onClick={() => setShowInfo(false)}
                  aria-label={t("info.close")}
                >
                  <X size={18} />
                </button>
              </div>
              <div className="mode-grid">
                {MODES.map((mode, i) => {
                  const Icon = mode.Icon;
                  return (
                    <motion.div
                      key={mode.titleKey}
                      className="mode-tile"
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.04, duration: 0.25 }}
                    >
                      <div className="mt-ico">
                        <Icon size={16} />
                      </div>
                      <h3>
                        {t(mode.titleKey)} <span className="tag">{t(mode.tagKey)}</span>
                      </h3>
                      <p>{t(mode.descKey)}</p>
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
