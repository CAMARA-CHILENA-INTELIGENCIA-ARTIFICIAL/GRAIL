import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useSessionStore } from "../lib/store";
import Sidebar from "./Sidebar";
import WelcomeView from "./WelcomeView";
import ChatView from "./ChatView";
import InfoPanel from "./InfoPanel";
import { PanelLeft } from "lucide-react";

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileOpen, setMobileOpen] = useState(false);
  const { activeSessionId, loadSessions } = useSessionStore();

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: "var(--surface-0)" }}>
      {/* Mobile overlay */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            className="fixed inset-0 z-30 md:hidden"
            style={{ background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)" }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setMobileOpen(false)}
          />
        )}
      </AnimatePresence>

      {/* Sidebar */}
      <div
        className={`
          fixed inset-y-0 left-0 z-40 flex-shrink-0
          transition-all duration-300 ease-[cubic-bezier(0.25,0.4,0.25,1)]
          md:relative md:z-auto
          ${mobileOpen ? "translate-x-0" : "-translate-x-full"}
          ${sidebarOpen ? "md:translate-x-0" : "md:-translate-x-full md:w-0"}
        `}
        style={{ width: sidebarOpen || mobileOpen ? 272 : 0 }}
      >
        <Sidebar
          onClose={() => {
            setMobileOpen(false);
            setSidebarOpen(false);
          }}
          isCollapsed={!sidebarOpen && !mobileOpen}
        />
      </div>

      {/* Main content */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top bar */}
        <div
          className="flex h-12 flex-shrink-0 items-center gap-3 px-4"
          style={{ borderBottom: "1px solid var(--border-subtle)" }}
        >
          <button
            onClick={() => {
              if (window.innerWidth < 768) {
                setMobileOpen(true);
              } else {
                setSidebarOpen((v) => !v);
              }
            }}
            className="rounded-lg p-1.5 transition-colors duration-150"
            style={{ color: "var(--text-tertiary)" }}
            onMouseEnter={(e) => { e.currentTarget.style.background = "var(--surface-2)"; e.currentTarget.style.color = "var(--text-secondary)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--text-tertiary)"; }}
            aria-label="Toggle sidebar"
          >
            <PanelLeft size={18} />
          </button>

          <span
            className="text-sm font-semibold tracking-tight"
            style={{ color: "var(--accent)" }}
          >
            GRAIL
          </span>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-hidden">
          <AnimatePresence mode="wait">
            {activeSessionId ? (
              <motion.div
                key="chat"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.2 }}
                className="h-full"
              >
                <ChatView />
              </motion.div>
            ) : (
              <motion.div
                key="welcome"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.2 }}
                className="h-full"
              >
                <WelcomeView />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      <InfoPanel />
    </div>
  );
}
