import { useMemo } from "react";
import { motion } from "framer-motion";
import { useSessionStore, useAuthStore, useChatStore } from "../lib/store";
import {
  Plus,
  Trash2,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import type { Session } from "../lib/store";

interface SidebarProps {
  collapsed: boolean;
  onToggleCollapsed: () => void;
  onMobileClose: () => void;
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

function formatWhen(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  if (d >= today) {
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  const week = new Date(today.getTime() - 7 * 86400000);
  if (d >= week) {
    return d.toLocaleDateString([], { weekday: "short" });
  }
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

export default function Sidebar({
  collapsed,
  onToggleCollapsed,
  onMobileClose: _onMobileClose,
}: SidebarProps) {
  const {
    sessions,
    activeSessionId,
    deleteSession,
    setActiveSession,
  } = useSessionStore();
  const { currentMode } = useChatStore();
  const { logout, user } = useAuthStore();
  const groups = useMemo(() => groupSessionsByDate(sessions), [sessions]);

  const isEmpty = sessions.length === 0;

  async function handleNew() {
    setActiveSession(null);
  }

  return (
    <aside className="sidebar">
      <div className="sb-head">
        <img className="sb-mark" src="/assets/grail_isotype.png" alt="GRAIL" />
        <span className="sb-word">GRAIL</span>
        <button
          className="sb-collapse"
          onClick={onToggleCollapsed}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </button>
      </div>

      <button className="sb-new" onClick={handleNew}>
        <Plus size={15} />
        <span>New chat</span>
      </button>

      {collapsed && (
        <div className="sb-rail-sessions">
          {sessions.slice(0, 6).map((s) => (
            <div
              key={s.id}
              className={`pip ${s.id === activeSessionId ? "active" : ""}`}
              title={s.title || "Untitled"}
              onClick={() => setActiveSession(s.id)}
              style={{ cursor: "pointer" }}
            />
          ))}
        </div>
      )}

      {!collapsed && (
        <>
          {isEmpty ? (
            <div className="sb-scroll">
              <div className="sb-empty-note">
                No conversations yet.<br />
                Start one to build your graph trail.
              </div>
            </div>
          ) : (
            <div className="sb-scroll">
              {groups.map((group) => (
                <div key={group.label} className="sb-group">
                  <div className="sb-group-label">{group.label}</div>
                  {group.sessions.map((session, i) => (
                    <motion.div
                      key={session.id}
                      initial={{ opacity: 0, x: -6 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ duration: 0.18, delay: i * 0.015 }}
                    >
                      <SessionItem
                        session={session}
                        isActive={session.id === activeSessionId}
                        onSelect={async () => {
                          if (session.id !== activeSessionId) {
                            await createSessionIfNeeded(setActiveSession, session.id);
                          }
                        }}
                        onDelete={() => deleteSession(session.id)}
                      />
                    </motion.div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </>
      )}

      <div className="sb-foot">
        <div className="sb-user">
          <div className="sb-avatar">
            {user?.username?.charAt(0).toUpperCase() || "U"}
          </div>
          <div className="who">
            <div className="name">{user?.username}</div>
            <div className="mail">GRAIL · {currentMode}</div>
          </div>
          <button className="logout" onClick={logout} title="Sign out">
            <LogOut size={14} />
          </button>
        </div>
        {!collapsed && (
          <div className="sb-credit">
            <img src="/assets/cchia.png" alt="CCHIA" />
            <span>
              Open source by <b>CCHIA × Nirvai</b>
            </span>
          </div>
        )}
      </div>
    </aside>
  );
}

async function createSessionIfNeeded(
  setActive: (id: string) => void | Promise<void>,
  id: string,
) {
  await setActive(id);
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
      className={`sb-item ${isActive ? "active" : ""}`}
      onClick={onSelect}
    >
      <span className="dot" />
      <span className="title">{session.title || "New chat"}</span>
      <span className="when">{formatWhen(session.updated_at || session.created_at)}</span>
      <button
        className="del"
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        title="Delete"
      >
        <Trash2 size={12} />
      </button>
    </div>
  );
}
