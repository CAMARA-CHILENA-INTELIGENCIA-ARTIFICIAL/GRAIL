import { useMemo } from "react";
import { motion } from "framer-motion";
import { useSessionStore, useAuthStore, useChatStore } from "../lib/store";
import { Plus, Trash2, LogOut, PanelLeftClose } from "lucide-react";
import type { Session } from "../lib/store";

interface SidebarProps {
  onClose: () => void;
  isCollapsed: boolean;
}

function groupSessionsByDate(sessions: Session[]) {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86400000);
  const weekAgo = new Date(today.getTime() - 7 * 86400000);

  const groups: { label: string; sessions: Session[] }[] = [
    { label: "Today", sessions: [] },
    { label: "Yesterday", sessions: [] },
    { label: "Previous 7 days", sessions: [] },
    { label: "Older", sessions: [] },
  ];

  for (const s of sessions) {
    const d = new Date(s.updated_at || s.created_at);
    if (d >= today) groups[0].sessions.push(s);
    else if (d >= yesterday) groups[1].sessions.push(s);
    else if (d >= weekAgo) groups[2].sessions.push(s);
    else groups[3].sessions.push(s);
  }

  return groups.filter((g) => g.sessions.length > 0);
}

export default function Sidebar({ onClose, isCollapsed }: SidebarProps) {
  const { sessions, activeSessionId, createSession, deleteSession, setActiveSession } = useSessionStore();
  const { currentMode } = useChatStore();
  const { logout, user } = useAuthStore();
  const groups = useMemo(() => groupSessionsByDate(sessions), [sessions]);

  if (isCollapsed) return null;

  return (
    <div
      className="flex h-full w-[272px] flex-col"
      style={{ background: "var(--surface-1)", borderRight: "1px solid var(--border-subtle)" }}
    >
      {/* Header */}
      <div
        className="flex flex-shrink-0 items-center justify-between px-4 py-3"
        style={{ borderBottom: "1px solid var(--border-subtle)" }}
      >
        <div className="flex items-center gap-2.5">
          <div
            className="flex h-7 w-7 items-center justify-center rounded-lg"
            style={{ background: "var(--accent-soft)", border: "1px solid var(--accent-border)" }}
          >
            <span className="text-xs font-bold" style={{ color: "var(--accent)" }}>G</span>
          </div>
          <span
            className="text-sm font-semibold tracking-tight"
            style={{ color: "var(--text-primary)" }}
          >
            GRAIL
          </span>
        </div>
        <button
          onClick={onClose}
          className="rounded-lg p-1.5 transition-colors duration-150"
          style={{ color: "var(--text-tertiary)" }}
          onMouseEnter={(e) => { e.currentTarget.style.background = "var(--surface-3)"; e.currentTarget.style.color = "var(--text-secondary)"; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--text-tertiary)"; }}
          aria-label="Close sidebar"
        >
          <PanelLeftClose size={16} />
        </button>
      </div>

      {/* New chat button */}
      <div className="flex-shrink-0 p-3">
        <button
          onClick={async () => {
            const session = await createSession(currentMode);
            setActiveSession(session.id);
          }}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm transition-all duration-150"
          style={{
            background: "var(--surface-2)",
            border: "1px solid var(--border)",
            color: "var(--text-primary)",
          }}
          onMouseEnter={(e) => { e.currentTarget.style.borderColor = "var(--accent-border)"; e.currentTarget.style.background = "var(--surface-3)"; }}
          onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.background = "var(--surface-2)"; }}
        >
          <Plus size={15} style={{ color: "var(--accent)" }} />
          <span className="font-medium">New Chat</span>
        </button>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {groups.map((group) => (
          <div key={group.label} className="mt-4 first:mt-1">
            <h3
              className="mb-1 px-2.5 text-[11px] font-medium uppercase tracking-widest"
              style={{ color: "var(--text-tertiary)" }}
            >
              {group.label}
            </h3>
            {group.sessions.map((session, i) => (
              <motion.div
                key={session.id}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.2, delay: i * 0.02 }}
              >
                <SessionItem
                  session={session}
                  isActive={session.id === activeSessionId}
                  onSelect={() => setActiveSession(session.id)}
                  onDelete={() => deleteSession(session.id)}
                />
              </motion.div>
            ))}
          </div>
        ))}

        {sessions.length === 0 && (
          <p
            className="mt-10 px-3 text-center text-sm"
            style={{ color: "var(--text-tertiary)" }}
          >
            No conversations yet.
            <br />
            Start a new chat to begin.
          </p>
        )}
      </div>

      {/* Footer */}
      <div
        className="flex flex-shrink-0 items-center justify-between px-4 py-3"
        style={{ borderTop: "1px solid var(--border-subtle)" }}
      >
        <div className="flex items-center gap-2">
          <div
            className="flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-semibold"
            style={{ background: "var(--surface-3)", color: "var(--text-secondary)" }}
          >
            {user?.username?.charAt(0).toUpperCase()}
          </div>
          <span className="truncate text-xs" style={{ color: "var(--text-secondary)" }}>
            {user?.username}
          </span>
        </div>
        <button
          onClick={logout}
          className="rounded-lg p-1.5 transition-colors duration-150"
          style={{ color: "var(--text-tertiary)" }}
          onMouseEnter={(e) => { e.currentTarget.style.color = "var(--text-secondary)"; }}
          onMouseLeave={(e) => { e.currentTarget.style.color = "var(--text-tertiary)"; }}
          title="Sign out"
        >
          <LogOut size={14} />
        </button>
      </div>
    </div>
  );
}

function SessionItem({
  session,
  isActive,
  onSelect,
  onDelete,
}: {
  session: Session;
  isActive: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  return (
    <div
      className="group relative flex cursor-pointer items-center rounded-lg px-2.5 py-1.5 text-[13px] transition-all duration-150"
      style={{
        background: isActive ? "var(--accent-soft)" : "transparent",
        color: isActive ? "var(--text-primary)" : "var(--text-secondary)",
        ...(isActive ? { boxShadow: `inset 2px 0 0 var(--accent)` } : {}),
      }}
      onClick={onSelect}
      onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.background = "var(--surface-2)"; }}
      onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.background = "transparent"; }}
    >
      <span className="flex-1 truncate">{session.title || "New Chat"}</span>
      <button
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        className="ml-2 hidden flex-shrink-0 rounded p-1 transition-colors duration-150 group-hover:block"
        style={{ color: "var(--text-tertiary)" }}
        onMouseEnter={(e) => { e.currentTarget.style.color = "#f87171"; }}
        onMouseLeave={(e) => { e.currentTarget.style.color = "var(--text-tertiary)"; }}
        title="Delete"
      >
        <Trash2 size={13} />
      </button>
    </div>
  );
}
