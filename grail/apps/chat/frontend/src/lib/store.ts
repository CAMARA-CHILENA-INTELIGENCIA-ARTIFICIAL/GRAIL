import { create } from "zustand";
import { api, ApiError, parseSSE } from "./api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface User {
  id: string;
  username: string;
}

export interface Session {
  id: string;
  title: string;
  mode: string;
  created_at: string;
  updated_at: string;
  message_count?: number;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  metadata?: {
    completion_time?: number;
    llm_calls?: number;
  };
  created_at: string;
}

export type SearchMode = "local" | "global" | "agent";

export interface AppConfig {
  project_name: string;
  modes: string[];
  has_reranker: boolean;
  version: string;
}

export interface IndexedDocument {
  id: string;
  title: string;
  path: string;
}

// ---------------------------------------------------------------------------
// Auth Store
// ---------------------------------------------------------------------------

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  needsSetup: boolean;
  isLoading: boolean;
  error: string | null;
  checkAuth: () => Promise<void>;
  login: (username: string, password: string) => Promise<void>;
  setup: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  needsSetup: false,
  isLoading: true,
  error: null,

  checkAuth: async () => {
    const token = api.getToken();
    if (!token) {
      try {
        const status = await api.get<{ needs_setup: boolean }>("/auth/status");
        set({ isLoading: false, needsSetup: status.needs_setup });
      } catch {
        set({ isLoading: false, needsSetup: true });
      }
      return;
    }
    try {
      const user = await api.get<User>("/auth/me");
      set({ user, isAuthenticated: true, isLoading: false });
    } catch {
      api.clearToken();
      set({ isAuthenticated: false, isLoading: false });
    }
  },

  login: async (username, password) => {
    set({ error: null });
    try {
      const res = await api.post<{
        access_token: string;
        user: User;
      }>("/auth/login", { username, password });
      api.setToken(res.access_token);
      set({ user: res.user, isAuthenticated: true, needsSetup: false });
    } catch (e) {
      const msg =
        e instanceof ApiError ? e.message : "Login failed";
      set({ error: msg });
      throw e;
    }
  },

  setup: async (username, password) => {
    set({ error: null });
    try {
      const res = await api.post<{
        access_token: string;
        user: User;
      }>("/auth/setup", { username, password });
      api.setToken(res.access_token);
      set({
        user: res.user,
        isAuthenticated: true,
        needsSetup: false,
      });
    } catch (e) {
      const msg =
        e instanceof ApiError ? e.message : "Setup failed";
      set({ error: msg });
      throw e;
    }
  },

  logout: () => {
    api.clearToken();
    set({ user: null, isAuthenticated: false });
    useSessionStore.getState().reset();
  },
}));

// ---------------------------------------------------------------------------
// Session Store
// ---------------------------------------------------------------------------

interface SessionState {
  sessions: Session[];
  activeSessionId: string | null;
  messages: Message[];
  isLoadingSessions: boolean;
  isLoadingMessages: boolean;
  loadSessions: () => Promise<void>;
  createSession: (mode?: SearchMode) => Promise<Session>;
  deleteSession: (id: string) => Promise<void>;
  setActiveSession: (id: string | null) => Promise<void>;
  loadMessages: (sessionId: string) => Promise<void>;
  addMessage: (message: Message) => void;
  updateLastAssistantMessage: (content: string) => void;
  updateSessionTitle: (id: string, title: string) => Promise<void>;
  reset: () => void;
}

export const useSessionStore = create<SessionState>((set, get) => ({
  sessions: [],
  activeSessionId: null,
  messages: [],
  isLoadingSessions: false,
  isLoadingMessages: false,

  loadSessions: async () => {
    set({ isLoadingSessions: true });
    try {
      const sessions = await api.get<Session[]>("/sessions");
      set({ sessions, isLoadingSessions: false });
    } catch {
      set({ isLoadingSessions: false });
    }
  },

  createSession: async (mode?: SearchMode) => {
    const session = await api.post<Session>("/sessions", {
      mode: mode || "agent",
    });
    set((state) => ({
      sessions: [session, ...state.sessions],
      activeSessionId: session.id,
      messages: [],
    }));
    return session;
  },

  deleteSession: async (id: string) => {
    await api.delete(`/sessions/${id}`);
    set((state) => ({
      sessions: state.sessions.filter((s) => s.id !== id),
      activeSessionId: state.activeSessionId === id ? null : state.activeSessionId,
      messages: state.activeSessionId === id ? [] : state.messages,
    }));
  },

  setActiveSession: async (id: string | null) => {
    set({ activeSessionId: id, messages: [] });
    if (id) {
      await get().loadMessages(id);
    }
  },

  loadMessages: async (sessionId: string) => {
    set({ isLoadingMessages: true });
    try {
      const session = await api.get<Session & { messages: Message[] }>(
        `/sessions/${sessionId}`,
      );
      set({ messages: session.messages, isLoadingMessages: false });
    } catch {
      set({ isLoadingMessages: false });
    }
  },

  addMessage: (message: Message) => {
    set((state) => ({ messages: [...state.messages, message] }));
  },

  updateLastAssistantMessage: (content: string) => {
    set((state) => {
      const msgs = [...state.messages];
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === "assistant") {
          msgs[i] = { ...msgs[i], content };
          break;
        }
      }
      return { messages: msgs };
    });
  },

  updateSessionTitle: async (id: string, title: string) => {
    await api.patch(`/sessions/${id}`, { title });
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.id === id ? { ...s, title } : s,
      ),
    }));
  },

  reset: () => {
    set({
      sessions: [],
      activeSessionId: null,
      messages: [],
    });
  },
}));

// ---------------------------------------------------------------------------
// Chat Store
// ---------------------------------------------------------------------------

interface ChatState {
  isStreaming: boolean;
  streamingContent: string;
  statusText: string | null;
  currentMode: SearchMode;
  useRerankerMode: boolean;
  documentScope: string | null;
  config: AppConfig | null;
  documents: IndexedDocument[];
  showInfo: boolean;
  setMode: (mode: SearchMode) => void;
  setUseRerankerMode: (v: boolean) => void;
  setDocumentScope: (doc: string | null) => void;
  setShowInfo: (v: boolean) => void;
  loadConfig: () => Promise<void>;
  loadDocuments: () => Promise<void>;
  sendMessage: (content: string, sessionId: string) => Promise<void>;
}

export const useChatStore = create<ChatState>((set, get) => ({
  isStreaming: false,
  streamingContent: "",
  statusText: null,
  currentMode: "agent",
  useRerankerMode: false,
  documentScope: null,
  config: null,
  documents: [],
  showInfo: false,

  setMode: (mode) => set({ currentMode: mode }),
  setUseRerankerMode: (v) => set({ useRerankerMode: v }),
  setDocumentScope: (doc) => set({ documentScope: doc }),
  setShowInfo: (v) => set({ showInfo: v }),

  loadConfig: async () => {
    try {
      const config = await api.get<AppConfig>("/config");
      set({ config });
    } catch {
      // Config endpoint not available, use defaults
    }
  },

  loadDocuments: async () => {
    try {
      const docs = await api.get<IndexedDocument[]>("/documents");
      set({ documents: docs });
    } catch {
      // Documents endpoint not available
    }
  },

  sendMessage: async (content, sessionId) => {
    const sessionStore = useSessionStore.getState();

    // Determine actual API mode and params
    let apiMode: string = get().currentMode;
    let document: string | undefined;
    let useReranker: boolean | undefined;

    if (get().documentScope) {
      apiMode = "document";
      document = get().documentScope ?? undefined;
    } else if (apiMode === "local" && get().useRerankerMode) {
      useReranker = true;
    }

    set({ isStreaming: true, streamingContent: "", statusText: null });

    try {
      const reader = await api.stream("/chat", {
        session_id: sessionId,
        message: content,
        mode: apiMode,
        document,
        use_reranker: useReranker,
      });

      for await (const event of parseSSE(reader)) {
        const data = JSON.parse(event.data);

        switch (event.event) {
          case "user_message":
            sessionStore.addMessage(data as Message);
            break;

          case "status":
            set({ statusText: `Searching (${data.mode})...` });
            break;

          case "assistant_chunk":
            set((state) => ({
              streamingContent: state.streamingContent + (data.content || ""),
            }));
            break;

          case "assistant_message":
            // Final complete message -- replace streaming content
            set({ streamingContent: "" });
            sessionStore.addMessage(data as Message);
            // Update session title in the sidebar if it was auto-generated
            if (data.session_title) {
              set(() => {
                const ss = useSessionStore.getState();
                useSessionStore.setState({
                  sessions: ss.sessions.map((s) =>
                    s.id === sessionId
                      ? { ...s, title: data.session_title }
                      : s,
                  ),
                });
                return {};
              });
            }
            break;

          case "done":
            break;

          case "error":
            console.error("SSE error:", data.detail);
            break;
        }
      }
    } catch (e) {
      console.error("Chat error:", e);
    } finally {
      set({ isStreaming: false, streamingContent: "", statusText: null });
    }
  },
}));
