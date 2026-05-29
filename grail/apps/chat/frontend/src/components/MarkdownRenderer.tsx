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
      className="absolute right-2 top-2 z-10 rounded-md p-1.5 opacity-0 transition-all duration-150 group-hover:opacity-100"
      style={{
        background: "var(--surface-3)",
        color: "var(--text-secondary)",
        border: "1px solid var(--border)",
      }}
      title="Copy"
    >
      {copied ? <Check size={13} style={{ color: "var(--accent)" }} /> : <Copy size={13} />}
    </button>
  );
}

function isCodeBlock(code: string): boolean {
  return code.includes("\n") || code.length > 80;
}

const components: Components = {
  h1: ({ children, ...props }) => (
    <h1 className="text-xl font-bold mb-3 mt-5 tracking-tight" style={{ color: "var(--text-primary)" }} {...props}>{children}</h1>
  ),
  h2: ({ children, ...props }) => (
    <h2 className="text-lg font-semibold mb-2 mt-4 tracking-tight" style={{ color: "var(--text-primary)" }} {...props}>{children}</h2>
  ),
  h3: ({ children, ...props }) => (
    <h3 className="text-base font-semibold mb-2 mt-3" style={{ color: "var(--text-primary)" }} {...props}>{children}</h3>
  ),
  h4: ({ children, ...props }) => (
    <h4 className="text-sm font-semibold mb-1.5 mt-3" style={{ color: "var(--text-primary)" }} {...props}>{children}</h4>
  ),
  p: ({ children, ...props }) => (
    <p className="my-2 leading-relaxed" style={{ color: "var(--text-primary)", opacity: 0.9 }} {...props}>{children}</p>
  ),
  ol: ({ children, ...props }) => (
    <ol className="list-decimal pl-6 space-y-1.5 my-3 leading-relaxed" style={{ color: "var(--text-primary)", opacity: 0.9 }} {...props}>{children}</ol>
  ),
  ul: ({ children, ...props }) => (
    <ul className="list-disc pl-6 space-y-1.5 my-3 leading-relaxed" style={{ color: "var(--text-primary)", opacity: 0.9 }} {...props}>{children}</ul>
  ),
  li: ({ children, ...props }) => (
    <li className="leading-relaxed" style={{ color: "var(--text-primary)", opacity: 0.9 }} {...props}>{children}</li>
  ),
  strong: ({ children, ...props }) => (
    <strong className="font-semibold" style={{ color: "var(--text-primary)" }} {...props}>{children}</strong>
  ),
  blockquote: ({ children, ...props }) => (
    <blockquote
      className="pl-4 py-2 my-3 italic rounded-r"
      style={{
        borderLeft: "2px solid var(--accent-border)",
        background: "var(--accent-soft)",
        color: "var(--text-secondary)",
      }}
      {...props}
    >
      {children}
    </blockquote>
  ),
  a: ({ href, children, ...props }) => {
    if (!href || !href.startsWith("http")) {
      return <span {...props}>{children}</span>;
    }
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[13px] transition-colors duration-150"
        style={{
          background: "var(--surface-2)",
          color: "var(--accent)",
          border: "1px solid var(--border-subtle)",
        }}
        {...props}
      >
        <span className="truncate max-w-[240px]">{children}</span>
      </a>
    );
  },
  hr: () => <hr className="my-4" style={{ borderColor: "var(--border)" }} />,
  img: ({ src, alt, ...props }) => (
    <div className="flex justify-center my-4">
      <img src={src} alt={alt || ""} className="max-w-full h-auto rounded-lg" {...props} />
    </div>
  ),
  code: ({ className, children, ...props }) => {
    const code = String(children).replace(/\n$/, "");
    const isBlock = className ? true : isCodeBlock(code);
    const lang = className?.replace(/language-/, "") || "";

    if (isBlock) {
      return (
        <div
          className="group relative my-3 overflow-hidden rounded-xl"
          style={{
            background: "var(--surface-0)",
            border: "1px solid var(--border)",
          }}
        >
          {lang && (
            <div className="flex items-center px-4 py-1.5" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
              <span
                className="text-[10px] font-semibold uppercase tracking-widest"
                style={{ color: "var(--text-tertiary)", fontFamily: "'JetBrains Mono', monospace" }}
              >
                {lang}
              </span>
            </div>
          )}
          <CopyButton text={code} />
          <pre className="overflow-x-auto p-4 text-[13px] leading-relaxed" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
            <code style={{ color: "var(--text-primary)", opacity: 0.85 }} {...props}>{code}</code>
          </pre>
        </div>
      );
    }

    return (
      <code
        className="rounded-md px-1.5 py-0.5 text-[13px]"
        style={{
          background: "var(--surface-2)",
          color: "#2dd4bf",
          fontFamily: "'JetBrains Mono', monospace",
        }}
        {...props}
      >
        {code}
      </code>
    );
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
            .join(" | ")
        )
        .join("\n");
      navigator.clipboard.writeText(md);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }

    return (
      <div
        className="group relative my-4 overflow-x-auto rounded-xl"
        style={{ border: "1px solid var(--border)" }}
      >
        <button
          onClick={handleCopy}
          className="absolute right-2 top-2 z-10 rounded-md p-1.5 opacity-0 transition-all duration-150 group-hover:opacity-100"
          style={{
            background: "var(--surface-3)",
            color: "var(--text-secondary)",
            border: "1px solid var(--border)",
          }}
          title="Copy table"
        >
          {copied ? <Check size={13} style={{ color: "var(--accent)" }} /> : <Copy size={13} />}
        </button>
        <table ref={tableRef} className="w-full text-sm text-left" {...props}>
          {children}
        </table>
      </div>
    );
  },
  th: ({ children, ...props }) => (
    <th
      className="px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-widest"
      style={{ background: "var(--surface-2)", color: "var(--text-tertiary)" }}
      {...props}
    >
      {children}
    </th>
  ),
  td: ({ children, ...props }) => (
    <td
      className="px-4 py-3"
      style={{ borderTop: "1px solid var(--border-subtle)", color: "var(--text-primary)", opacity: 0.9 }}
      {...props}
    >
      {children}
    </td>
  ),
};

interface MarkdownRendererProps {
  content: string;
}

export default function MarkdownRenderer({ content }: MarkdownRendererProps) {
  const memoComponents = useMemo(() => components, []);

  return (
    <div className="text-sm leading-relaxed">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={memoComponents}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
