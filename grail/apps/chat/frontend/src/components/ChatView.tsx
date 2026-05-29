import { useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2 } from "lucide-react";
import { useSessionStore, useChatStore } from "../lib/store";
import MessageBubble, { StreamingBubble } from "./MessageBubble";
import ChatInput from "./ChatInput";

export default function ChatView() {
  const { activeSessionId, messages, isLoadingMessages } = useSessionStore();
  const { isStreaming, streamingContent, statusText, sendMessage } = useChatStore();
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent, isStreaming]);

  function handleSend(content: string) {
    if (!activeSessionId) return;
    sendMessage(content, activeSessionId);
  }

  return (
    <div className="flex h-full flex-col">
      {/* Status bar */}
      <AnimatePresence>
        {statusText && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="flex-shrink-0 overflow-hidden"
            style={{ borderBottom: "1px solid var(--border-subtle)" }}
          >
            <div className="flex items-center gap-2.5 px-4 py-2" style={{ background: "var(--surface-1)" }}>
              <Loader2 size={13} className="animate-spin" style={{ color: "var(--accent)" }} />
              <span className="text-xs" style={{ color: "var(--text-secondary)" }}>{statusText}</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl py-6">
          {isLoadingMessages ? (
            <div className="flex justify-center py-16">
              <div className="flex gap-1.5">
                <span className="loading-dot h-1.5 w-1.5 rounded-full bg-teal-500" />
                <span className="loading-dot h-1.5 w-1.5 rounded-full bg-teal-500" />
                <span className="loading-dot h-1.5 w-1.5 rounded-full bg-teal-500" />
              </div>
            </div>
          ) : messages.length === 0 && !isStreaming ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex flex-col items-center justify-center py-20 text-center"
            >
              <p className="text-sm" style={{ color: "var(--text-tertiary)" }}>
                Start the conversation below.
              </p>
            </motion.div>
          ) : (
            <div className="space-y-1">
              {messages.map((msg, i) => (
                <motion.div
                  key={msg.id}
                  initial={i === messages.length - 1 ? { opacity: 0, y: 8 } : false}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3 }}
                >
                  <MessageBubble message={msg} />
                </motion.div>
              ))}
            </div>
          )}

          {isStreaming && <StreamingBubble content={streamingContent} />}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input */}
      <div
        className="flex-shrink-0"
        style={{ borderTop: "1px solid var(--border-subtle)" }}
      >
        <div className="mx-auto w-full max-w-3xl px-4 py-3">
          <ChatInput onSend={handleSend} disabled={isStreaming} />
        </div>
      </div>
    </div>
  );
}
