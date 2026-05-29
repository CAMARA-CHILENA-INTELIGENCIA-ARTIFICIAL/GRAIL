import { useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useAuthStore, useChatStore } from "./lib/store";
import LoginView from "./components/LoginView";
import Layout from "./components/Layout";

export default function App() {
  const { isAuthenticated, isLoading, checkAuth } = useAuthStore();
  const { loadConfig, loadDocuments } = useChatStore();

  useEffect(() => {
    checkAuth();
    loadConfig();
  }, [checkAuth, loadConfig]);

  useEffect(() => {
    if (isAuthenticated) {
      loadDocuments();
    }
  }, [isAuthenticated, loadDocuments]);

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center" style={{ background: "var(--surface-0)" }}>
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.4 }}
          className="flex flex-col items-center gap-4"
        >
          <span
            className="text-2xl font-semibold tracking-tight"
            style={{
              background: "linear-gradient(135deg, #5eead4, #14b8a6)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            GRAIL
          </span>
          <div className="flex gap-1.5">
            <span className="loading-dot h-1.5 w-1.5 rounded-full bg-teal-500" />
            <span className="loading-dot h-1.5 w-1.5 rounded-full bg-teal-500" />
            <span className="loading-dot h-1.5 w-1.5 rounded-full bg-teal-500" />
          </div>
        </motion.div>
      </div>
    );
  }

  return (
    <AnimatePresence mode="wait">
      {!isAuthenticated ? (
        <motion.div
          key="login"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.3 }}
        >
          <LoginView />
        </motion.div>
      ) : (
        <motion.div
          key="app"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
          className="h-screen"
        >
          <Layout />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
