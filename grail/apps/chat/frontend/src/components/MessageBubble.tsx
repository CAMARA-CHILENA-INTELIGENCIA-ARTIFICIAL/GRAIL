import { useState } from "react";
import { motion } from "framer-motion";
import {
  User,
  Sparkles,
  Clock,
  FileText,
  FileSpreadsheet,
  FileCode,
  FileImage,
  File,
  Download,
  MessageSquare,
} from "lucide-react";
import type { Message, SourceReference } from "../lib/store";
import { useChatStore } from "../lib/store";
import { api } from "../lib/api";
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

function fileIcon(title: string) {
  const ext = title.split(".").pop()?.toLowerCase() ?? "";
  const s = 11;
  switch (ext) {
    case "pdf":
      return <FileText size={s} style={{ color: "#f87171" }} />;
    case "xlsx": case "xls": case "csv": case "tsv":
      return <FileSpreadsheet size={s} style={{ color: "#4ade80" }} />;
    case "json": case "yaml": case "yml": case "toml": case "xml": case "py": case "js": case "ts": case "html":
      return <FileCode size={s} style={{ color: "#60a5fa" }} />;
    case "png": case "jpg": case "jpeg": case "gif": case "svg": case "webp":
      return <FileImage size={s} style={{ color: "#c084fc" }} />;
    case "docx": case "doc":
      return <FileText size={s} style={{ color: "#60a5fa" }} />;
    case "md": case "markdown": case "rst": case "txt": case "log":
      return <FileText size={s} style={{ color: "var(--text-tertiary)" }} />;
    default:
      return <File size={s} style={{ color: "var(--text-tertiary)" }} />;
  }
}

function SourceBadge({ src }: { src: SourceReference }) {
  const { currentMode, setDraftInput } = useChatStore();
  const isAgent = currentMode === "agent";

  function handleDownload(e: React.MouseEvent) {
    e.stopPropagation();
    const token = api.getToken();
    const url = `/api/documents/${encodeURIComponent(src.id)}/download`;
    const a = document.createElement("a");
    a.href = url + (token ? `?token=${encodeURIComponent(token)}` : "");
    a.download = src.title;
    a.click();
  }

  function handleAskAgent(e: React.MouseEvent) {
    e.stopPropagation();
    setDraftInput(`Search in document "${src.title}" (${src.id}): `);
  }

  return (
    <span
      className="group/src inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs transition-all duration-150"
      style={{
        background: "var(--surface-2)",
        border: "1px solid var(--border-subtle)",
        color: "var(--text-secondary)",
      }}
      title={src.path || src.title}
    >
      {fileIcon(src.title)}
      <span className="max-w-[130px] truncate">{src.title}</span>
      <button
        type="button"
        onClick={handleDownload}
        className="ml-0.5 hidden rounded p-0.5 transition-colors duration-150 group-hover/src:inline-flex"
        style={{ color: "var(--text-tertiary)" }}
        onMouseEnter={(e) => { e.currentTarget.style.color = "var(--text-primary)"; e.currentTarget.style.background = "var(--surface-3)"; }}
        onMouseLeave={(e) => { e.currentTarget.style.color = "var(--text-tertiary)"; e.currentTarget.style.background = "transparent"; }}
        title="Download source file"
      >
        <Download size={11} />
      </button>
      {isAgent && (
        <button
          type="button"
          onClick={handleAskAgent}
          className="hidden rounded p-0.5 transition-colors duration-150 group-hover/src:inline-flex"
          style={{ color: "var(--text-tertiary)" }}
          onMouseEnter={(e) => { e.currentTarget.style.color = "var(--accent)"; e.currentTarget.style.background = "var(--surface-3)"; }}
          onMouseLeave={(e) => { e.currentTarget.style.color = "var(--text-tertiary)"; e.currentTarget.style.background = "transparent"; }}
          title="Ask agent about this document"
        >
          <MessageSquare size={11} />
        </button>
      )}
    </span>
  );
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const [showTime, setShowTime] = useState(false);
  const isUser = message.role === "user";

  return (
    <div
      className={`group flex gap-3 px-4 py-3 ${isUser ? "flex-row-reverse" : "flex-row"}`}
      onMouseEnter={() => setShowTime(true)}
      onMouseLeave={() => setShowTime(false)}
    >
      {/* Avatar */}
      <div
        className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl"
        style={{
          background: isUser ? "var(--accent)" : "var(--surface-2)",
          border: isUser ? "none" : "1px solid var(--border)",
        }}
      >
        {isUser ? (
          <User size={14} className="text-white" />
        ) : (
          <Sparkles size={14} style={{ color: "var(--accent)" }} />
        )}
      </div>

      {/* Content */}
      <div className={`min-w-0 max-w-[80%] ${isUser ? "items-end" : "items-start"}`}>
        <div
          className="rounded-2xl px-4 py-3"
          style={{
            background: isUser ? "var(--accent)" : "var(--surface-1)",
            border: isUser ? "none" : "1px solid var(--border-subtle)",
            borderTopRightRadius: isUser ? 6 : undefined,
            borderTopLeftRadius: isUser ? undefined : 6,
            color: isUser ? "white" : "var(--text-primary)",
          }}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap text-sm">{message.content}</p>
          ) : (
            <MarkdownRenderer content={message.content} />
          )}
        </div>

        {/* Metadata */}
        <div
          className={`mt-1.5 flex items-center gap-3 px-1 text-[11px] ${
            isUser ? "justify-end" : "justify-start"
          }`}
          style={{ color: "var(--text-tertiary)" }}
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
                  {message.metadata.llm_calls} call{message.metadata.llm_calls !== 1 ? "s" : ""}
                </span>
              )}
            </>
          )}
        </div>

        {/* Source references */}
        {!isUser && message.metadata?.sources && message.metadata.sources.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.1 }}
            className="mt-2 flex flex-wrap gap-1.5 px-1"
          >
            {message.metadata.sources.map((src) => (
              <SourceBadge key={src.id} src={src} />
            ))}
          </motion.div>
        )}
      </div>
    </div>
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
        <div
          className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl"
          style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}
        >
          <Sparkles size={14} style={{ color: "var(--accent)" }} />
        </div>
        <div className="min-w-0 max-w-[80%]">
          <div
            className="rounded-2xl rounded-tl-md px-4 py-3"
            style={{ background: "var(--surface-1)", border: "1px solid var(--border-subtle)", color: "var(--text-primary)" }}
          >
            {content ? (
              <MarkdownRenderer content={content} />
            ) : (
              <div className="flex gap-1.5 py-2">
                <span className="loading-dot h-1.5 w-1.5 rounded-full" style={{ background: "var(--accent)" }} />
                <span className="loading-dot h-1.5 w-1.5 rounded-full" style={{ background: "var(--accent)" }} />
                <span className="loading-dot h-1.5 w-1.5 rounded-full" style={{ background: "var(--accent)" }} />
              </div>
            )}
          </div>
        </div>
      </div>
    </motion.div>
  );
}
