import { useMemo, useState } from "react";
import { ChevronRight, Wrench, Loader2 } from "lucide-react";
import MarkdownRenderer from "./MarkdownRenderer";
import { useT } from "../lib/i18n";

interface AssistantContentProps {
  content: string;
  /** When true, an unclosed <tool_call> block at the end renders as pending. */
  streaming?: boolean;
}

type Segment =
  | { kind: "text"; text: string }
  | { kind: "tool_call"; name: string; args: string }
  | { kind: "tool_call_pending"; name: string; args: string };

const TOOL_CALL_RE = /<tool_call\s+name="([^"]+)">\s*([\s\S]*?)\s*<\/tool_call>/g;
const TOOL_CALL_OPEN_RE = /<tool_call\s+name="([^"]*)"\s*>([\s\S]*)$/;

/**
 * Splits an assistant message into prose + tool_call segments. During
 * streaming the last segment may be a partial (unclosed) tool_call which we
 * render as a pending card.
 */
function parseAssistantContent(content: string, streaming: boolean): Segment[] {
  const out: Segment[] = [];
  TOOL_CALL_RE.lastIndex = 0;
  let cursor = 0;
  let m: RegExpExecArray | null;
  while ((m = TOOL_CALL_RE.exec(content)) !== null) {
    if (m.index > cursor) {
      out.push({ kind: "text", text: content.slice(cursor, m.index) });
    }
    out.push({ kind: "tool_call", name: m[1], args: m[2] });
    cursor = TOOL_CALL_RE.lastIndex;
  }
  if (cursor < content.length) {
    const tail = content.slice(cursor);
    // If we're streaming, look for a partially-open <tool_call name="..."> at
    // the end so it shows immediately rather than appearing as literal text.
    if (streaming) {
      const open = tail.indexOf("<tool_call");
      if (open >= 0) {
        if (open > 0) out.push({ kind: "text", text: tail.slice(0, open) });
        const partial = tail.slice(open);
        const pm = partial.match(TOOL_CALL_OPEN_RE);
        if (pm) {
          out.push({ kind: "tool_call_pending", name: pm[1], args: pm[2] });
          return out;
        }
        // Not enough of the tag has arrived yet to extract a name. Drop the
        // partial fragment from the visible text — it would only ever read
        // as "<tool_c…" until the rest streams in.
        return out;
      }
    }
    out.push({ kind: "text", text: tail });
  }
  return out;
}

export default function AssistantContent({ content, streaming = false }: AssistantContentProps) {
  const segments = useMemo(
    () => parseAssistantContent(content, streaming),
    [content, streaming],
  );

  return (
    <>
      {segments.map((seg, i) => {
        if (seg.kind === "text") {
          if (!seg.text.trim()) return null;
          return <MarkdownRenderer key={i} content={seg.text} />;
        }
        return (
          <ToolCallCard
            key={i}
            name={seg.name}
            args={seg.args}
            pending={seg.kind === "tool_call_pending"}
          />
        );
      })}
    </>
  );
}

function ToolCallCard({
  name,
  args,
  pending,
}: {
  name: string;
  args: string;
  pending?: boolean;
}) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const argsPretty = useMemo(() => {
    const trimmed = (args ?? "").trim();
    if (!trimmed) return "";
    try {
      return JSON.stringify(JSON.parse(trimmed), null, 2);
    } catch {
      return trimmed;
    }
  }, [args]);
  // One-line summary for the collapsed header: first non-empty primitive arg.
  const summary = useMemo(() => extractSummary(argsPretty), [argsPretty]);
  const displayName = humanizeToolName(name);

  return (
    <div className={`tool-call ${pending ? "pending" : ""}`} data-tool-name={name}>
      <button
        type="button"
        className="tool-call-head"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="tool-call-icon">
          {pending ? (
            <Loader2 size={14} className="tool-call-spin" />
          ) : (
            <Wrench size={14} />
          )}
        </span>
        <span className="tool-call-name">{displayName}</span>
        {summary && <span className="tool-call-summary">{summary}</span>}
        {pending && (
          <span className="tool-call-status">{t("toolCall.running")}</span>
        )}
        <ChevronRight
          size={14}
          className={`tool-call-chevron ${open ? "open" : ""}`}
        />
      </button>
      {open && argsPretty && (
        <pre className="tool-call-args">
          <code>{argsPretty}</code>
        </pre>
      )}
    </div>
  );
}

function humanizeToolName(name: string): string {
  if (!name) return "Tool";
  // local_search → Local search; cascade_search → Cascade search
  const cleaned = name.replace(/_/g, " ").trim();
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

/**
 * Try to surface the first interesting argument inline so the collapsed
 * card already says *what* the tool is doing without forcing the user to
 * expand. Prefers `query`, then any string value.
 */
function extractSummary(argsPretty: string): string {
  if (!argsPretty) return "";
  try {
    const parsed = JSON.parse(argsPretty);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      const preferred = ["query", "question", "document", "filename", "filter"];
      for (const k of preferred) {
        const v = (parsed as Record<string, unknown>)[k];
        if (typeof v === "string" && v.trim()) {
          return truncate(v.trim(), 90);
        }
      }
      // Fall back to the first stringable value.
      for (const v of Object.values(parsed)) {
        if (typeof v === "string" && v.trim()) return truncate(v.trim(), 90);
        if (typeof v === "number" || typeof v === "boolean") return String(v);
      }
    }
  } catch {
    // Not JSON — return the raw args, truncated.
    return truncate(argsPretty, 90);
  }
  return "";
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}
