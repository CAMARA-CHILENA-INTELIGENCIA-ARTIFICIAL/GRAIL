import { useState } from "react";
import { motion } from "framer-motion";
import { User, Sparkles, Clock } from "lucide-react";
import type { Message } from "../lib/store";
import MarkdownRenderer from "./MarkdownRenderer";

interface MessageBubbleProps {
  message: Message;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatDuration(seconds: number): string {
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const [showTime, setShowTime] = useState(false);
  const isUser = message.role === "user";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <div
        className={`group flex gap-3 px-4 py-3 ${isUser ? "flex-row-reverse" : "flex-row"}`}
        onMouseEnter={() => setShowTime(true)}
        onMouseLeave={() => setShowTime(false)}
      >
        {/* Avatar */}
        <div
          className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full ${
            isUser ? "bg-teal-600" : "bg-zinc-800"
          }`}
        >
          {isUser ? (
            <User size={16} className="text-white" />
          ) : (
            <Sparkles size={16} className="text-teal-400" />
          )}
        </div>

        {/* Content */}
        <div className={`min-w-0 max-w-[80%] ${isUser ? "items-end" : "items-start"}`}>
          <div
            className={`rounded-2xl px-4 py-3 ${
              isUser
                ? "rounded-tr-sm bg-teal-600 text-white"
                : "rounded-tl-sm bg-zinc-800/80 text-zinc-100"
            }`}
          >
            {isUser ? (
              <p className="whitespace-pre-wrap text-sm">{message.content}</p>
            ) : (
              <MarkdownRenderer content={message.content} />
            )}
          </div>

          {/* Metadata */}
          <div
            className={`mt-1 flex items-center gap-3 px-1 text-xs text-zinc-500 ${
              isUser ? "justify-end" : "justify-start"
            }`}
          >
            {showTime && message.created_at && (
              <span className="flex items-center gap-1">
                <Clock size={10} />
                {formatTime(message.created_at)}
              </span>
            )}
            {!isUser && message.metadata && (
              <>
                {message.metadata.completion_time != null && (
                  <span>{formatDuration(message.metadata.completion_time)}</span>
                )}
                {message.metadata.llm_calls != null && (
                  <span>
                    {message.metadata.llm_calls} LLM call
                    {message.metadata.llm_calls !== 1 ? "s" : ""}
                  </span>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </motion.div>
  );
}

export function StreamingBubble({ content }: { content: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <div className="group flex gap-3 px-4 py-3">
        <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-zinc-800">
          <Sparkles size={16} className="text-teal-400" />
        </div>
        <div className="min-w-0 max-w-[80%]">
          <div className="rounded-2xl rounded-tl-sm bg-zinc-800/80 px-4 py-3 text-zinc-100">
            {content ? (
              <MarkdownRenderer content={content} />
            ) : (
              <div className="flex gap-1.5 py-2">
                <span className="loading-dot h-2 w-2 rounded-full bg-teal-500" />
                <span className="loading-dot h-2 w-2 rounded-full bg-teal-500" />
                <span className="loading-dot h-2 w-2 rounded-full bg-teal-500" />
              </div>
            )}
          </div>
        </div>
      </div>
    </motion.div>
  );
}
