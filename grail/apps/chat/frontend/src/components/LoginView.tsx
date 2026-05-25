import { useState, type FormEvent } from "react";
import { motion } from "framer-motion";
import { useAuthStore } from "../lib/store";
import { Lock, User, ArrowRight } from "lucide-react";

const LOGO = ` ██████╗ ██████╗ █████╗ ██╗██╗
██╔════╝ ██╔══██╗██╔══██╗██║██║
██║  ███╗██████╔╝███████║██║██║
██║   ██║██╔══██╗██╔══██║██║██║
╚██████╔╝██║  ██║██║  ██║██║███████╗
 ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚══════╝`;

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
      if (needsSetup) {
        await setup(username, password);
      } else {
        await login(username, password);
      }
    } catch {
      // Error is set in store
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, ease: [0.25, 0.4, 0.25, 1] }}
        className="w-full max-w-sm"
      >
        {/* Logo */}
        <div className="mb-8 text-center">
          <pre
            className="inline-block text-left font-mono text-xs leading-tight"
            style={{
              background:
                "linear-gradient(180deg, #5eead4 0%, #14b8a6 50%, #0f766e 100%)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            {LOGO}
          </pre>
        </div>

        {/* Card */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-6">
          <h2 className="mb-1 text-center text-lg font-semibold text-zinc-50">
            {needsSetup ? "Set up your account" : "Sign in"}
          </h2>
          <p className="mb-6 text-center text-sm text-zinc-400">
            {needsSetup
              ? "Create your first account to get started"
              : "Enter your credentials to continue"}
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Username */}
            <div>
              <label
                htmlFor="username"
                className="mb-1.5 block text-sm font-medium text-zinc-300"
              >
                Username
              </label>
              <div className="relative">
                <User
                  size={16}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500"
                />
                <input
                  id="username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Enter username"
                  autoComplete="username"
                  className="w-full rounded-lg border border-zinc-800 bg-zinc-950 py-2.5 pl-10 pr-3 text-sm text-zinc-50 placeholder-zinc-500 outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
                />
              </div>
            </div>

            {/* Password */}
            <div>
              <label
                htmlFor="password"
                className="mb-1.5 block text-sm font-medium text-zinc-300"
              >
                Password
              </label>
              <div className="relative">
                <Lock
                  size={16}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500"
                />
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter password"
                  autoComplete={needsSetup ? "new-password" : "current-password"}
                  className="w-full rounded-lg border border-zinc-800 bg-zinc-950 py-2.5 pl-10 pr-3 text-sm text-zinc-50 placeholder-zinc-500 outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
                />
              </div>
            </div>

            {/* Error */}
            {error && (
              <p className="rounded-lg bg-red-900/30 px-3 py-2 text-sm text-red-400">
                {error}
              </p>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={isSubmitting || !username.trim() || !password.trim()}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-teal-600 py-2.5 text-sm font-medium text-white hover:bg-teal-500 disabled:cursor-not-allowed disabled:opacity-50"
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
                  <ArrowRight size={16} />
                </>
              )}
            </button>
          </form>
        </div>

        <p className="mt-4 text-center text-xs text-zinc-600">
          Graph RAG with Advanced Integration and Learning
        </p>
      </motion.div>
    </div>
  );
}
