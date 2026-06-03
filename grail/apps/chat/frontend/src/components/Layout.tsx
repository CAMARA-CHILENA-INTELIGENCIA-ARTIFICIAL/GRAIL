import { useState, useEffect, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useSessionStore, useChatStore } from "../lib/store";
import Sidebar from "./Sidebar";
import WelcomeView from "./WelcomeView";
import ChatView from "./ChatView";
import ChatInput from "./ChatInput";
import InfoPanel from "./InfoPanel";
import GraphMotif from "./GraphMotif";

export default function Layout() {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const { activeSessionId, createSession, loadSessions } = useSessionStore();
  const { currentMode, sendMessage, statusText } = useChatStore();
  const streamRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  async function handleSend(message: string) {
    let sid = activeSessionId;
    if (!sid) {
      const session = await createSession(currentMode);
      sid = session.id;
    }
    sendMessage(message, sid);
  }

  const showMotif = !activeSessionId;

  return (
    <div className={`app-shell ${collapsed ? "collapsed" : ""} ${mobileOpen ? "mobile-open" : ""}`}>
      <GraphMotif show={showMotif} />

      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            className="mobile-scrim"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setMobileOpen(false)}
          />
        )}
      </AnimatePresence>

      <Sidebar
        collapsed={collapsed}
        onToggleCollapsed={() => setCollapsed((v) => !v)}
        onMobileClose={() => setMobileOpen(false)}
      />

      <main className="main">
        <div className={`statusbar ${statusText ? "show" : ""}`}>
          <div className="inner">
            <div className="spinner" />
            <div className="stxt">{statusText || ""}</div>
          </div>
        </div>

        <div className="stream-wrap" ref={streamRef}>
          <AnimatePresence mode="wait">
            {activeSessionId ? (
              <motion.div
                key="chat"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
              >
                <ChatView />
              </motion.div>
            ) : (
              <motion.div
                key="welcome"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="h-full"
              >
                <WelcomeView />
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <div className="composer-wrap">
          <div className="composer-inner">
            <ChatInput onSend={handleSend} />
            <div className="composer-hint">
              <span>{modeHint(currentMode)}</span>
              <span>
                <kbd>↵</kbd> send &nbsp;·&nbsp; <kbd>⇧↵</kbd> newline
              </span>
            </div>
          </div>
        </div>
      </main>

      <InfoPanel />
    </div>
  );
}

function modeHint(mode: string): string {
  switch (mode) {
    case "agent":
      return "Agent mode · chains searches automatically";
    case "local":
      return "Local search · walks the entity neighborhood";
    case "global":
      return "Global search · synthesizes community reports";
    default:
      return "Ask your knowledge graph";
  }
}
