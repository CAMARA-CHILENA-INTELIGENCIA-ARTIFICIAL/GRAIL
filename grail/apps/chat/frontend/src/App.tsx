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
      <div
        style={{
          height: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "var(--surface-0)",
        }}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.94 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.4 }}
          style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 18 }}
        >
          <img src="/assets/grail_logotype.png" alt="GRAIL" style={{ height: 56, opacity: 0.9 }} />
          <div style={{ display: "flex", gap: 6 }}>
            <span
              className="loading-dot"
              style={{ width: 6, height: 6, borderRadius: 99, background: "var(--accent)" }}
            />
            <span
              className="loading-dot"
              style={{ width: 6, height: 6, borderRadius: 99, background: "var(--accent)" }}
            />
            <span
              className="loading-dot"
              style={{ width: 6, height: 6, borderRadius: 99, background: "var(--accent)" }}
            />
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
          style={{ height: "100vh" }}
        >
          <Layout />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
