import { useRef, useEffect } from "react";
import { Database } from "lucide-react";
import { useSessionStore, useChatStore } from "../lib/store";
import MessageBubble, { StreamingBubble } from "./MessageBubble";

export default function ChatView() {
  const { activeSessionId, messages, isLoadingMessages, sessions } = useSessionStore();
  const { isStreaming, streamingContent, documentScope } = useChatStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  const activeSession = sessions.find((s) => s.id === activeSessionId);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent, isStreaming]);

  if (isLoadingMessages) {
    return (
      <div className="stream">
        <div className="flex justify-center py-16">
          <div className="streaming">
            <span className="dot" />
            <span className="dot" />
            <span className="dot" />
          </div>
        </div>
      </div>
    );
  }

  if (messages.length === 0 && !isStreaming) {
    return (
      <section className="empty-session" style={{ minHeight: "calc(100vh - 200px)" }}>
        <img className="glyph" src="/assets/grail_isotype.png" alt="" />
        <h2 className="es-title">Start the conversation below.</h2>
        <p className="es-sub">This session is empty. Ask anything about your indexed corpus.</p>
        {documentScope && (
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              fontFamily: "var(--font-mono)",
              fontSize: 11,
              color: "var(--text-tertiary)",
              background: "var(--surface-1)",
              border: "1px solid var(--border-subtle)",
              borderRadius: 99,
              padding: "5px 12px",
            }}
          >
            <Database size={13} style={{ color: "var(--accent)" }} />
            Scoped to <b style={{ color: "var(--text-secondary)", fontWeight: 500 }}>{documentScope}</b>
          </div>
        )}
        {activeSession && (
          <div
            style={{
              marginTop: 20,
              fontFamily: "var(--font-mono)",
              fontSize: 11,
              color: "var(--text-tertiary)",
              letterSpacing: "0.03em",
            }}
          >
            mode · {activeSession.mode}
          </div>
        )}
      </section>
    );
  }

  return (
    <div className="stream">
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
      {isStreaming && <StreamingBubble content={streamingContent} />}
      <div ref={bottomRef} />
    </div>
  );
}
