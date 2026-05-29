import { useState, type FormEvent } from "react";
import { motion } from "framer-motion";
import { useAuthStore } from "../lib/store";
import { Lock, User, ArrowRight, Sparkles } from "lucide-react";

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

  return (
    <div
      className="relative flex min-h-screen items-center justify-center px-4"
      style={{ background: "var(--surface-0)" }}
    >
      {/* Ambient glow */}
      <div
        className="pointer-events-none absolute left-1/2 top-1/3 -translate-x-1/2 -translate-y-1/2"
        style={{
          width: 500,
          height: 500,
          background: "radial-gradient(circle, rgba(20,184,166,0.06) 0%, transparent 70%)",
          filter: "blur(60px)",
        }}
      />

      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease }}
        className="relative w-full max-w-sm"
      >
        {/* Logo */}
        <div className="mb-8 flex flex-col items-center gap-3">
          <motion.div
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.5, ease, delay: 0.1 }}
            className="flex h-12 w-12 items-center justify-center rounded-xl"
            style={{
              background: "var(--accent-soft)",
              border: "1px solid var(--accent-border)",
              boxShadow: "0 0 40px -8px rgba(20, 184, 166, 0.25)",
            }}
          >
            <Sparkles size={20} style={{ color: "var(--accent)" }} />
          </motion.div>
          <motion.span
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2 }}
            className="text-xl font-bold tracking-tight"
            style={{
              background: "linear-gradient(135deg, #5eead4, #14b8a6)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            GRAIL
          </motion.span>
        </div>

        {/* Card */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease, delay: 0.15 }}
          className="rounded-xl p-6"
          style={{
            background: "var(--surface-1)",
            border: "1px solid var(--border)",
          }}
        >
          <h2 className="mb-1 text-center text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
            {needsSetup ? "Create your account" : "Welcome back"}
          </h2>
          <p className="mb-6 text-center text-sm" style={{ color: "var(--text-secondary)" }}>
            {needsSetup ? "Set up credentials to get started" : "Sign in to continue"}
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="username" className="mb-1.5 block text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
                Username
              </label>
              <div className="relative">
                <User size={15} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "var(--text-tertiary)" }} />
                <input
                  id="username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Enter username"
                  autoComplete="username"
                  className="w-full rounded-lg py-2.5 pl-10 pr-3 text-sm outline-none transition-all duration-150 focus:ring-1"
                  style={{
                    background: "var(--surface-0)",
                    border: "1px solid var(--border)",
                    color: "var(--text-primary)",
                  }}
                  onFocus={(e) => { e.currentTarget.style.borderColor = "var(--accent)"; e.currentTarget.style.boxShadow = "0 0 0 1px var(--accent-border)"; }}
                  onBlur={(e) => { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.boxShadow = "none"; }}
                />
              </div>
            </div>

            <div>
              <label htmlFor="password" className="mb-1.5 block text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
                Password
              </label>
              <div className="relative">
                <Lock size={15} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "var(--text-tertiary)" }} />
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter password"
                  autoComplete={needsSetup ? "new-password" : "current-password"}
                  className="w-full rounded-lg py-2.5 pl-10 pr-3 text-sm outline-none transition-all duration-150"
                  style={{
                    background: "var(--surface-0)",
                    border: "1px solid var(--border)",
                    color: "var(--text-primary)",
                  }}
                  onFocus={(e) => { e.currentTarget.style.borderColor = "var(--accent)"; e.currentTarget.style.boxShadow = "0 0 0 1px var(--accent-border)"; }}
                  onBlur={(e) => { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.boxShadow = "none"; }}
                />
              </div>
            </div>

            {error && (
              <motion.p
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                className="rounded-lg px-3 py-2 text-sm"
                style={{ background: "rgba(248,113,113,0.08)", border: "1px solid rgba(248,113,113,0.15)", color: "#f87171" }}
              >
                {error}
              </motion.p>
            )}

            <button
              type="submit"
              disabled={isSubmitting || !username.trim() || !password.trim()}
              className="flex w-full items-center justify-center gap-2 rounded-lg py-2.5 text-sm font-medium text-white transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-40"
              style={{
                background: "var(--accent)",
                boxShadow: "0 1px 2px rgba(0,0,0,0.2), 0 0 16px -4px rgba(20,184,166,0.3)",
              }}
              onMouseEnter={(e) => { if (!isSubmitting) e.currentTarget.style.filter = "brightness(1.1)"; }}
              onMouseLeave={(e) => { e.currentTarget.style.filter = "brightness(1)"; }}
            >
              {isSubmitting ? (
                <div className="flex gap-1">
                  <span className="loading-dot h-1.5 w-1.5 rounded-full bg-white" />
                  <span className="loading-dot h-1.5 w-1.5 rounded-full bg-white" />
                  <span className="loading-dot h-1.5 w-1.5 rounded-full bg-white" />
                </div>
              ) : (
                <>
                  {needsSetup ? "Create Account" : "Sign In"}
                  <ArrowRight size={15} />
                </>
              )}
            </button>
          </form>
        </motion.div>

        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.4 }}
          className="mt-5 text-center text-[11px] tracking-wide"
          style={{ color: "var(--text-tertiary)" }}
        >
          Graph RAG with Advanced Integration and Learning
        </motion.p>
      </motion.div>
    </div>
  );
}
