import { useMemo } from "react";
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
  const {
    sessions,
    activeSessionId,
    createSession,
    deleteSession,
    setActiveSession,
  } = useSessionStore();
  const { currentMode } = useChatStore();
  const { logout, user } = useAuthStore();

  const groups = useMemo(() => groupSessionsByDate(sessions), [sessions]);

  if (isCollapsed) return null;

  return (
    <div className="flex h-full w-[280px] flex-col border-r border-zinc-800 bg-zinc-900">
      {/* Header with logo */}
      <div className="flex flex-shrink-0 items-start justify-between border-b border-zinc-800 px-3 py-3">
        <pre
          className="font-mono text-[5px] leading-[1.15] sm:text-[6px]"
          style={{
            background:
              "linear-gradient(180deg, #5eead4 0%, #14b8a6 50%, #0f766e 100%)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}
        >{` ██████╗ ██████╗  █████╗ ██╗██╗
██╔════╝ ██╔══██╗██╔══██╗██║██║
██║  ███╗██████╔╝███████║██║██║
██║   ██║██╔══██╗██╔══██║██║██║
╚██████╔╝██║  ██║██║  ██║██║███████╗
 ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚══════╝`}</pre>
        <button
          onClick={onClose}
          className="mt-1 rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
          aria-label="Close sidebar"
        >
          <PanelLeftClose size={18} />
        </button>
      </div>

      {/* New chat button */}
      <div className="flex-shrink-0 p-3">
        <button
          onClick={async () => {
            const session = await createSession(currentMode);
            setActiveSession(session.id);
          }}
          className="flex w-full items-center gap-2 rounded-lg border border-zinc-800 px-3 py-2.5 text-sm text-zinc-200 hover:border-teal-600 hover:bg-zinc-800"
        >
          <Plus size={16} className="text-teal-500" />
          New Chat
        </button>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {groups.map((group) => (
          <div key={group.label} className="mt-4 first:mt-0">
            <h3 className="mb-1 px-2 text-xs font-medium uppercase tracking-wider text-zinc-500">
              {group.label}
            </h3>
            {group.sessions.map((session) => (
              <SessionItem
                key={session.id}
                session={session}
                isActive={session.id === activeSessionId}
                onSelect={() => setActiveSession(session.id)}
                onDelete={() => deleteSession(session.id)}
              />
            ))}
          </div>
        ))}

        {sessions.length === 0 && (
          <p className="mt-8 px-3 text-center text-sm text-zinc-600">
            No conversations yet. Start a new chat to begin.
          </p>
        )}
      </div>

      {/* Footer */}
      <div className="flex flex-shrink-0 items-center justify-between border-t border-zinc-800 px-3 py-3">
        <span className="truncate text-xs text-zinc-500">
          {user?.username}
        </span>
        <button
          onClick={logout}
          className="rounded-lg p-1.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
          title="Sign out"
        >
          <LogOut size={16} />
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
      className={`group relative flex cursor-pointer items-center rounded-lg px-3 py-2 text-sm ${
        isActive
          ? "border-l-2 border-teal-500 bg-zinc-800 text-zinc-50"
          : "text-zinc-300 hover:bg-zinc-800/60"
      }`}
      onClick={onSelect}
    >
      <span className="flex-1 truncate">
        {session.title || "New Chat"}
      </span>
      <button
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        className="ml-2 hidden flex-shrink-0 rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-red-400 group-hover:block"
        title="Delete"
      >
        <Trash2 size={14} />
      </button>
    </div>
  );
}
