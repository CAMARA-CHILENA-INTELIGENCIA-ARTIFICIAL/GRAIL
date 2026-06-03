import {
  FileText,
  FileSpreadsheet,
  FileCode,
  FileImage,
  File,
  Download,
  MessageSquare,
  Timer,
  Cpu,
  GitCommitHorizontal,
  Quote,
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

function classifyFile(title: string): { type: string; Icon: typeof FileText } {
  const ext = title.split(".").pop()?.toLowerCase() ?? "";
  switch (ext) {
    case "pdf":
      return { type: "pdf", Icon: FileText };
    case "xlsx":
    case "xls":
    case "csv":
    case "tsv":
      return { type: "sheet", Icon: FileSpreadsheet };
    case "json":
    case "yaml":
    case "yml":
    case "toml":
    case "xml":
    case "py":
    case "js":
    case "ts":
    case "html":
      return { type: "code", Icon: FileCode };
    case "png":
    case "jpg":
    case "jpeg":
    case "gif":
    case "svg":
    case "webp":
      return { type: "img", Icon: FileImage };
    case "docx":
    case "doc":
      return { type: "doc", Icon: FileText };
    case "md":
    case "markdown":
    case "rst":
    case "txt":
    case "log":
      return { type: "text", Icon: FileText };
    default:
      return { type: "text", Icon: File };
  }
}

function Source({ src }: { src: SourceReference }) {
  const { currentMode, setDraftInput } = useChatStore();
  const { type, Icon } = classifyFile(src.title);
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
    <div className="source" title={src.path || src.title}>
      <div className={`ftype t-${type}`}>
        <Icon size={14} />
      </div>
      <div className="info">
        <div className="fname">{src.title}</div>
        <div className="fmeta">
          <span>{src.path && src.path !== src.title ? truncate(src.path, 28) : "source"}</span>
        </div>
      </div>
      <div className="actions">
        <button onClick={handleDownload} title="Download">
          <Download size={13} />
        </button>
        {isAgent && (
          <button onClick={handleAskAgent} title="Ask agent about this document">
            <MessageSquare size={13} />
          </button>
        )}
      </div>
    </div>
  );
}

function truncate(s: string, n: number): string {
  return s.length > n ? "…" + s.slice(-(n - 1)) : s;
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="msg user">
        <div className="body">
          <div className="bubble-user">{message.content}</div>
          {message.created_at && (
            <div className="meta">
              <span className="t-hover">{formatTime(message.created_at)}</span>
            </div>
          )}
        </div>
      </div>
    );
  }

  const meta = message.metadata;
  const sources = meta?.sources ?? [];

  return (
    <div className="msg assistant">
      <div className="avatar">
        <img src="/assets/grail_isotype.png" alt="" />
      </div>
      <div className="body" style={{ flex: 1, minWidth: 0 }}>
        <div className="bubble-assistant">
          <MarkdownRenderer content={message.content} />

          {sources.length > 0 && (
            <div className="kfooter">
              <div className="sources">
                <div className="sources-label">
                  <Quote size={13} />
                  Sources
                </div>
                <div className="source-list">
                  {sources.map((src) => (
                    <Source key={src.id} src={src} />
                  ))}
                </div>
              </div>
            </div>
          )}

          {meta && (meta.completion_time != null || meta.llm_calls != null) && (
            <div className="meta" style={{ marginTop: 16 }}>
              {meta.completion_time != null && (
                <span className="pill">
                  <Timer size={12} />
                  {formatDuration(meta.completion_time)}
                </span>
              )}
              {meta.llm_calls != null && (
                <span className="pill">
                  <Cpu size={12} />
                  {meta.llm_calls} LLM call{meta.llm_calls !== 1 ? "s" : ""}
                </span>
              )}
              {sources.length > 0 && (
                <span className="pill">
                  <GitCommitHorizontal size={12} />
                  {sources.length} source{sources.length !== 1 ? "s" : ""}
                </span>
              )}
              {message.created_at && (
                <span className="t-hover">{formatTime(message.created_at)}</span>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function StreamingBubble({ content }: { content: string }) {
  return (
    <div className="msg assistant">
      <div className="avatar">
        <img src="/assets/grail_isotype.png" alt="" />
      </div>
      <div className="body" style={{ flex: 1, minWidth: 0 }}>
        <div className="bubble-assistant" style={{ padding: content ? "4px 20px 16px" : 0 }}>
          {content ? (
            <MarkdownRenderer content={content} />
          ) : (
            <div className="streaming">
              <span className="dot" />
              <span className="dot" />
              <span className="dot" />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
