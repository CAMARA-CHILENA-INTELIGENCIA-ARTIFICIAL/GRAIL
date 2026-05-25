import { useRef, useEffect } from "react";
import { motion } from "framer-motion";
import { useSessionStore, useChatStore } from "../lib/store";
import MessageBubble, { StreamingBubble } from "./MessageBubble";
import ChatInput from "./ChatInput";

export default function ChatView() {
  const { activeSessionId, messages, isLoadingMessages } = useSessionStore();
  const { isStreaming, streamingContent, statusText, sendMessage } =
    useChatStore();
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages or streaming content
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
      {statusText && (
        <div className="flex flex-shrink-0 items-center gap-2 border-b border-zinc-800 bg-zinc-900/50 px-4 py-2">
          <div className="h-2 w-2 animate-pulse rounded-full bg-teal-500" />
          <span className="text-xs text-zinc-400">{statusText}</span>
        </div>
      )}

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl py-4">
          {isLoadingMessages ? (
            <div className="flex justify-center py-12">
              <div className="flex gap-1.5">
                <span className="loading-dot h-2 w-2 rounded-full bg-teal-500" />
                <span className="loading-dot h-2 w-2 rounded-full bg-teal-500" />
                <span className="loading-dot h-2 w-2 rounded-full bg-teal-500" />
              </div>
            </div>
          ) : messages.length === 0 && !isStreaming ? (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
              className="flex flex-col items-center justify-center py-16 text-center"
            >
              <p className="text-sm text-zinc-500">
                Start the conversation by typing a message below.
              </p>
            </motion.div>
          ) : (
            <>
              {messages.map((msg) => (
                <MessageBubble key={msg.id} message={msg} />
              ))}
            </>
          )}

          {/* Streaming indicator */}
          {isStreaming && <StreamingBubble content={streamingContent} />}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input */}
      <div className="mx-auto w-full max-w-3xl flex-shrink-0 px-4 pb-4">
        <ChatInput onSend={handleSend} disabled={isStreaming} />
      </div>
    </div>
  );
}
