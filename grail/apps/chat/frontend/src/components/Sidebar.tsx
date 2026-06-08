import { useMemo } from "react";
import { motion } from "framer-motion";
import { useSessionStore, useAuthStore, useChatStore } from "../lib/store";
import { useT, useI18nStore } from "../lib/i18n";
import {
  Plus,
  Trash2,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  BookOpen,
  Github,
  Database,
  MessageSquare,
  Share2,
} from "lucide-react";

const DOCS_URL = "https://grail-docs.vercel.app/";
const REPO_URL = "https://github.com/CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/GRAIL";
import type { Session } from "../lib/store";

interface SidebarProps {
  collapsed: boolean;
  onToggleCollapsed: () => void;
  onMobileClose: () => void;
}

type GroupKey = "today" | "yesterday" | "week" | "older";

function groupSessionsByDate(sessions: Session[]): { key: GroupKey; sessions: Session[] }[] {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86400000);
  const weekAgo = new Date(today.getTime() - 7 * 86400000);

  const groups: { key: GroupKey; sessions: Session[] }[] = [
    { key: "today", sessions: [] },
    { key: "yesterday", sessions: [] },
    { key: "week", sessions: [] },
    { key: "older", sessions: [] },
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
  const { currentMode, config, viewMode, setViewMode } = useChatStore();
  const { logout, user } = useAuthStore();
  const t = useT();
  const { lang, setLang } = useI18nStore();
  const groups = useMemo(() => groupSessionsByDate(sessions), [sessions]);

  const groupLabel = (k: GroupKey): string => {
    switch (k) {
      case "today": return t("sb.groupToday");
      case "yesterday": return t("sb.groupYesterday");
      case "week": return t("sb.groupWeek");
      case "older": return t("sb.groupOlder");
    }
  };

  const isEmpty = sessions.length === 0;

  async function handleNew() {
    setViewMode("chat");
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
          title={collapsed ? t("sb.expand") : t("sb.collapse")}
        >
          {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </button>
      </div>

      {!collapsed && config?.project_name && (
        <div className="sb-project" title={config.project_path || config.project_name}>
          <span className="icon">
            <Database size={13} />
          </span>
          <span className="info">
            <span className="label">{t("sb.kbLabel")}</span>
            <span className="name">{config.project_name}</span>
          </span>
        </div>
      )}

      <button className="sb-new" onClick={handleNew}>
        <Plus size={15} />
        <span>{t("sb.newChat")}</span>
      </button>

      {!collapsed && (
        <div className="sb-views" role="tablist" aria-label={t("sb.viewSwitch")}>
          <button
            type="button"
            role="tab"
            className={`sb-view-pill ${viewMode === "chat" ? "active" : ""}`}
            aria-pressed={viewMode === "chat"}
            onClick={() => setViewMode("chat")}
          >
            <MessageSquare size={13} />
            <span>{t("sb.viewChat")}</span>
          </button>
          <button
            type="button"
            role="tab"
            className={`sb-view-pill ${viewMode === "graph" ? "active" : ""}`}
            aria-pressed={viewMode === "graph"}
            onClick={() => setViewMode("graph")}
          >
            <Share2 size={13} />
            <span>{t("sb.viewGraph")}</span>
          </button>
        </div>
      )}

      {collapsed && (
        <div className="sb-rail-views">
          <button
            type="button"
            className={`pip-btn ${viewMode === "chat" ? "active" : ""}`}
            onClick={() => setViewMode("chat")}
            title={t("sb.viewChat")}
          >
            <MessageSquare size={13} />
          </button>
          <button
            type="button"
            className={`pip-btn ${viewMode === "graph" ? "active" : ""}`}
            onClick={() => setViewMode("graph")}
            title={t("sb.viewGraph")}
          >
            <Share2 size={13} />
          </button>
        </div>
      )}

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
                {t("sb.emptyTitle")}<br />
                {t("sb.emptySub")}
              </div>
            </div>
          ) : (
            <div className="sb-scroll">
              {groups.map((group) => (
                <div key={group.key} className="sb-group">
                  <div className="sb-group-label">{groupLabel(group.key)}</div>
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
                        deleteLabel={t("sb.delete")}
                        untitledLabel={t("sb.untitled")}
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
            <div className="mail">{t("sb.modeLine", { mode: currentMode })}</div>
          </div>
          <button className="logout" onClick={logout} title={t("sb.signOut")}>
            <LogOut size={14} />
          </button>
        </div>
        {!collapsed && (
          <div className="sb-credit">
            <img src="/assets/cchia.png" alt="CCHIA" />
            <span>
              {t("sb.credit")} <b>CCHIA × Nirvai</b>
            </span>
          </div>
        )}
        <div className="sb-links">
          <a
            href={DOCS_URL}
            target="_blank"
            rel="noopener noreferrer"
            title={t("sb.docs")}
          >
            <BookOpen size={13} />
            <span>{t("sb.docs")}</span>
          </a>
          <a
            href={REPO_URL}
            target="_blank"
            rel="noopener noreferrer"
            title={t("sb.github")}
          >
            <Github size={13} />
            <span>{t("sb.github")}</span>
          </a>
        </div>
        <div className="sb-foot-row">
          <div className="lang-toggle" role="group" aria-label="Language">
            <button
              type="button"
              className={lang === "en" ? "active" : ""}
              onClick={() => setLang("en")}
              aria-pressed={lang === "en"}
            >
              EN
            </button>
            <button
              type="button"
              className={lang === "es" ? "active" : ""}
              onClick={() => setLang("es")}
              aria-pressed={lang === "es"}
            >
              ES
            </button>
          </div>
        </div>
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
  deleteLabel,
  untitledLabel,
}: {
  session: Session;
  isActive: boolean;
  onSelect: () => void;
  onDelete: () => void;
  deleteLabel: string;
  untitledLabel: string;
}) {
  return (
    <div
      className={`sb-item ${isActive ? "active" : ""}`}
      onClick={onSelect}
    >
      <span className="dot" />
      <span className="title">{session.title || untitledLabel}</span>
      <span className="when">{formatWhen(session.updated_at || session.created_at)}</span>
      <button
        className="del"
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        title={deleteLabel}
      >
        <Trash2 size={12} />
      </button>
    </div>
  );
}
