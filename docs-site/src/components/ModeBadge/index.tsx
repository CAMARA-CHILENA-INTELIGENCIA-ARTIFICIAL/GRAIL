import React from "react";
import { useCurrentLocale } from "@site/src/lib/locale";

type Mode = "kb" | "memory" | "both";

interface ModeBadgeProps {
  mode: Mode;
}

const LABELS: Record<string, Record<Mode, string>> = {
  es: {
    kb: "Modo · Base de conocimiento",
    memory: "Modo · Memoria agéntica",
    both: "Modo · Ambos",
  },
  en: {
    kb: "Mode · Knowledge base",
    memory: "Mode · Agentic memory",
    both: "Mode · Both",
  },
};

export default function ModeBadge({ mode }: ModeBadgeProps): React.ReactElement {
  const locale = useCurrentLocale();
  const dictionary = LABELS[locale] ?? LABELS.en;
  return (
    <div className={`grail-mode-badge grail-mode-badge--${mode}`}>
      {dictionary[mode]}
    </div>
  );
}
