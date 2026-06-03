import React from "react";
import { useCurrentLocale } from "@site/src/lib/locale";

interface AnalogyProps {
  label?: string;
  children: React.ReactNode;
}

const DEFAULT_LABEL: Record<string, string> = {
  es: "Piensa en GRAIL como…",
  en: "Think of GRAIL as…",
};

export default function Analogy({ label, children }: AnalogyProps): React.ReactElement {
  const locale = useCurrentLocale();
  const resolved = label ?? DEFAULT_LABEL[locale] ?? DEFAULT_LABEL.en;
  return (
    <aside className="grail-analogy" role="note">
      <span className="grail-analogy__label">{resolved}</span>
      <div className="grail-analogy__body">{children}</div>
    </aside>
  );
}
