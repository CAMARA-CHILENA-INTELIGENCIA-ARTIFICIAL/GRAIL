import { useState, useEffect } from "react";
import { useSessionStore } from "../lib/store";
import Sidebar from "./Sidebar";
import WelcomeView from "./WelcomeView";
import ChatView from "./ChatView";
import InfoPanel from "./InfoPanel";
import { Menu } from "lucide-react";

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileOpen, setMobileOpen] = useState(false);
  const { activeSessionId, loadSessions } = useSessionStore();

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Sidebar */}
      <div
        className={`
          fixed inset-y-0 left-0 z-40 flex-shrink-0
          transition-transform duration-200 ease-in-out
          md:relative md:z-auto
          ${mobileOpen ? "translate-x-0" : "-translate-x-full"}
          ${sidebarOpen ? "md:translate-x-0" : "md:-translate-x-full md:w-0"}
        `}
        style={{ width: sidebarOpen || mobileOpen ? 280 : 0 }}
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
        <div className="flex h-12 flex-shrink-0 items-center gap-3 border-b border-zinc-800 px-4">
          {/* Toggle sidebar / hamburger */}
          <button
            onClick={() => {
              if (window.innerWidth < 768) {
                setMobileOpen(true);
              } else {
                setSidebarOpen((v) => !v);
              }
            }}
            className="rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
            aria-label="Toggle sidebar"
          >
            <Menu size={20} />
          </button>

          <span className="text-sm font-medium text-teal-400">GRAIL</span>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-hidden">
          {activeSessionId ? <ChatView /> : <WelcomeView />}
        </div>
      </div>

      {/* Info panel overlay */}
      <InfoPanel />
    </div>
  );
}
