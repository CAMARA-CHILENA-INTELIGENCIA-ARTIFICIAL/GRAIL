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
      className="absolute right-2 top-2 z-10 rounded-md p-1.5 opacity-0 transition-opacity group-hover:opacity-100 bg-zinc-700 hover:bg-zinc-600 text-zinc-300"
      title="Copy"
    >
      {copied ? <Check size={14} className="text-teal-400" /> : <Copy size={14} />}
    </button>
  );
}

function isCodeBlock(code: string): boolean {
  return code.includes("\n") || code.length > 80;
}

const components: Components = {
  h1: ({ children, ...props }) => (
    <h1 className="text-xl font-bold mb-3 mt-5 tracking-tight text-zinc-50" {...props}>{children}</h1>
  ),
  h2: ({ children, ...props }) => (
    <h2 className="text-lg font-semibold mb-2 mt-4 tracking-tight text-zinc-50" {...props}>{children}</h2>
  ),
  h3: ({ children, ...props }) => (
    <h3 className="text-base font-semibold mb-2 mt-3 text-zinc-50" {...props}>{children}</h3>
  ),
  h4: ({ children, ...props }) => (
    <h4 className="text-sm font-semibold mb-1.5 mt-3 text-zinc-100" {...props}>{children}</h4>
  ),
  p: ({ children, ...props }) => (
    <p className="my-2 leading-relaxed text-zinc-200" {...props}>{children}</p>
  ),
  ol: ({ children, ...props }) => (
    <ol className="list-decimal pl-6 space-y-1.5 my-3 leading-relaxed text-zinc-200" {...props}>{children}</ol>
  ),
  ul: ({ children, ...props }) => (
    <ul className="list-disc pl-6 space-y-1.5 my-3 leading-relaxed text-zinc-200" {...props}>{children}</ul>
  ),
  li: ({ children, ...props }) => (
    <li className="text-zinc-200 leading-relaxed" {...props}>{children}</li>
  ),
  strong: ({ children, ...props }) => (
    <strong className="font-semibold text-zinc-50" {...props}>{children}</strong>
  ),
  blockquote: ({ children, ...props }) => (
    <blockquote className="border-l-2 border-teal-500/50 bg-zinc-800/40 pl-4 py-2 my-3 italic rounded-r text-zinc-400" {...props}>
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
        className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-zinc-800/60 hover:bg-zinc-700/80 text-teal-400 hover:text-teal-300 text-[13px] transition-colors"
        {...props}
      >
        <span className="truncate max-w-[240px]">{children}</span>
      </a>
    );
  },
  hr: () => <hr className="my-4 border-t border-zinc-700" />,
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
        <div className="group relative my-3 overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950">
          {lang && (
            <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-1.5">
              <span className="text-[11px] font-medium uppercase tracking-wider text-zinc-500">{lang}</span>
            </div>
          )}
          <CopyButton text={code} />
          <pre className="overflow-x-auto p-4 text-sm leading-relaxed">
            <code className="text-zinc-300" {...props}>{code}</code>
          </pre>
        </div>
      );
    }

    return (
      <code className="rounded bg-zinc-800 px-1.5 py-0.5 text-[13px] text-teal-300" {...props}>
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
      <div className="group relative my-4 overflow-x-auto rounded-lg border border-zinc-800">
        <button
          onClick={handleCopy}
          className="absolute right-2 top-2 z-10 rounded-md p-1.5 opacity-0 transition-opacity group-hover:opacity-100 bg-zinc-700 hover:bg-zinc-600 text-zinc-300"
          title="Copy table"
        >
          {copied ? <Check size={14} className="text-teal-400" /> : <Copy size={14} />}
        </button>
        <table ref={tableRef} className="w-full text-sm text-left" {...props}>
          {children}
        </table>
      </div>
    );
  },
  th: ({ children, ...props }) => (
    <th className="px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wider bg-zinc-900 text-zinc-400" {...props}>
      {children}
    </th>
  ),
  td: ({ children, ...props }) => (
    <td className="px-4 py-3 border-t border-zinc-800 text-zinc-300" {...props}>
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
