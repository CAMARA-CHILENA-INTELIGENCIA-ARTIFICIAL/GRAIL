import { useState, useRef, useMemo, type ComponentPropsWithoutRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Copy, Check } from "lucide-react";

type Components = ComponentPropsWithoutRef<typeof ReactMarkdown>["components"];

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <button
      onClick={handleCopy}
      style={{
        position: "absolute",
        right: 8,
        top: 8,
        zIndex: 10,
        padding: 5,
        borderRadius: 6,
        background: "var(--surface-3)",
        color: "var(--text-secondary)",
        border: "1px solid var(--border)",
        opacity: 0,
        transition: "opacity 0.15s",
      }}
      className="md-copy-btn"
      title="Copy"
    >
      {copied ? <Check size={12} style={{ color: "var(--accent)" }} /> : <Copy size={12} />}
    </button>
  );
}

function isCodeBlock(code: string): boolean {
  return code.includes("\n") || code.length > 80;
}

const components: Components = {
  a: ({ href, children, ...props }) => {
    if (!href || !href.startsWith("http")) {
      return <span {...props}>{children}</span>;
    }
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
        {children}
      </a>
    );
  },
  img: ({ src, alt, ...props }) => (
    <div style={{ display: "flex", justifyContent: "center", margin: "16px 0" }}>
      <img
        src={src}
        alt={alt || ""}
        style={{ maxWidth: "100%", height: "auto", borderRadius: 10 }}
        {...props}
      />
    </div>
  ),
  code: ({ className, children, ...props }) => {
    const code = String(children).replace(/\n$/, "");
    const isBlock = className ? true : isCodeBlock(code);

    if (isBlock) {
      return (
        <div className="group" style={{ position: "relative" }}>
          <CopyButton text={code} />
          <pre>
            <code {...props}>{code}</code>
          </pre>
        </div>
      );
    }

    return <code {...props}>{code}</code>;
  },
  table: ({ children, ...props }) => {
    const tableRef = useRef<HTMLTableElement>(null);
    const [copied, setCopied] = useState(false);

    function handleCopy() {
      if (!tableRef.current) return;
      const rows = tableRef.current.querySelectorAll("tr");
      const md = Array.from(rows)
        .map((row) =>
          Array.from(row.querySelectorAll("th, td"))
            .map((cell) => cell.textContent?.trim() || "")
            .join(" | "),
        )
        .join("\n");
      navigator.clipboard.writeText(md);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }

    return (
      <div className="group" style={{ position: "relative", margin: "1.1em 0" }}>
        <button
          onClick={handleCopy}
          className="md-copy-btn"
          style={{
            position: "absolute",
            right: 8,
            top: 8,
            zIndex: 10,
            padding: 5,
            borderRadius: 6,
            background: "var(--surface-3)",
            color: "var(--text-secondary)",
            border: "1px solid var(--border)",
            opacity: 0,
            transition: "opacity 0.15s",
          }}
          title="Copy table"
        >
          {copied ? <Check size={12} style={{ color: "var(--accent)" }} /> : <Copy size={12} />}
        </button>
        <table ref={tableRef} {...props}>
          {children}
        </table>
      </div>
    );
  },
};

interface MarkdownRendererProps {
  content: string;
}

export default function MarkdownRenderer({ content }: MarkdownRendererProps) {
  const memoComponents = useMemo(() => components, []);

  return (
    <div className="prose-grail">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={memoComponents}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
