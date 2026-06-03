import { useState, type FormEvent } from "react";
import { motion } from "framer-motion";
import { useAuthStore } from "../lib/store";
import GraphMotif from "./GraphMotif";

const ease = [0.25, 0.4, 0.25, 1] as const;

export default function LoginView() {
  const { needsSetup, login, setup, error } = useAuthStore();
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
          {needsSetup ? "Create your account" : "Welcome back"}
        </h2>
        <p className="lg-sub">
          {needsSetup
            ? "Set up credentials to get started."
            : "Sign in to your knowledge graph."}
        </p>

        <form className="lg-form" onSubmit={handleSubmit}>
          <div className="field">
            <label htmlFor="username">Username</label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="you@cchia.cl"
              autoComplete="username"
            />
          </div>

          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••"
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
              needsSetup ? "Create account" : "Sign in"
            )}
          </button>
        </form>

        <p className="lg-tagline">Graph RAG with Advanced Integration and Learning</p>
      </motion.div>

      <div className="lg-credit">
        <img src="/assets/cchia.png" alt="CCHIA" />
        <span>
          An open-source project by <b>CCHIA × Nirvai</b>
        </span>
      </div>
    </div>
  );
}
