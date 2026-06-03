import { useState, type FormEvent } from "react";
import { motion } from "framer-motion";
import { BookOpen, Github } from "lucide-react";
import { useAuthStore } from "../lib/store";
import { useT, useI18nStore } from "../lib/i18n";
import GraphMotif from "./GraphMotif";

const DOCS_URL = "https://grail-docs.vercel.app/";
const REPO_URL = "https://github.com/CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/GRAIL";

const ease = [0.25, 0.4, 0.25, 1] as const;

export default function LoginView() {
  const { needsSetup, login, setup, error } = useAuthStore();
  const t = useT();
  const { lang, setLang } = useI18nStore();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!username.trim() || !password.trim()) return;
    setIsSubmitting(true);
    try {
      if (needsSetup) await setup(username, password);
      else await login(username, password);
    } catch {
      // Error is set in store
    } finally {
      setIsSubmitting(false);
    }
  }

  const canSubmit = !isSubmitting && username.trim().length > 0 && password.trim().length > 0;

  return (
    <div className="login-page">
      <GraphMotif show={true} />

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease }}
        className="lg-card"
      >
        <img className="lg-logo" src="/assets/grail_logotype.png" alt="GRAIL" />

        <h2 className="lg-title">
          {needsSetup ? t("login.titleSetup") : t("login.titleSignIn")}
        </h2>
        <p className="lg-sub">
          {needsSetup ? t("login.subSetup") : t("login.subSignIn")}
        </p>

        <form className="lg-form" onSubmit={handleSubmit}>
          <div className="field">
            <label htmlFor="username">{t("login.username")}</label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder={t("login.usernamePlaceholder")}
              autoComplete="username"
            />
          </div>

          <div className="field">
            <label htmlFor="password">{t("login.password")}</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t("login.passwordPlaceholder")}
              autoComplete={needsSetup ? "new-password" : "current-password"}
            />
          </div>

          {error && <div className="lg-error">{error}</div>}

          <button
            type="submit"
            className="lg-submit"
            disabled={!canSubmit}
          >
            {isSubmitting ? (
              <div style={{ display: "flex", gap: 6 }}>
                <span className="loading-dot" style={{ width: 6, height: 6, borderRadius: 99, background: "var(--on-accent)" }} />
                <span className="loading-dot" style={{ width: 6, height: 6, borderRadius: 99, background: "var(--on-accent)" }} />
                <span className="loading-dot" style={{ width: 6, height: 6, borderRadius: 99, background: "var(--on-accent)" }} />
              </div>
            ) : (
              needsSetup ? t("login.submitSetup") : t("login.submitSignIn")
            )}
          </button>
        </form>

        <p className="lg-tagline">{t("login.tagline")}</p>

        <div className="lg-links">
          <a href={DOCS_URL} target="_blank" rel="noopener noreferrer">
            <BookOpen size={13} />
            {t("sb.docs")}
          </a>
          <a href={REPO_URL} target="_blank" rel="noopener noreferrer">
            <Github size={13} />
            {t("sb.github")}
          </a>
          <div className="lang-toggle" role="group" aria-label="Language" style={{ marginLeft: 4 }}>
            <button
              type="button"
              className={lang === "en" ? "active" : ""}
              onClick={() => setLang("en")}
              aria-pressed={lang === "en"}
            >
              EN
            </button>
            <button
              type="button"
              className={lang === "es" ? "active" : ""}
              onClick={() => setLang("es")}
              aria-pressed={lang === "es"}
            >
              ES
            </button>
          </div>
        </div>
      </motion.div>

      <div className="lg-credit">
        <img src="/assets/cchia.png" alt="CCHIA" />
        <span>
          {t("login.credit")} <b>CCHIA × Nirvai</b>
        </span>
      </div>
    </div>
  );
}
