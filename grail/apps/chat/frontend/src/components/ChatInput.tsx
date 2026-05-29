import { useState, useRef, useEffect, type KeyboardEvent } from "react";
import { ArrowUp, CircleHelp } from "lucide-react";
import { useChatStore } from "../lib/store";
import { ModeChips, DocumentScope } from "./ModeSelector";

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
}

export default function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { isStreaming, setShowInfo, draftInput, setDraftInput } = useChatStore();

  useEffect(() => {
    if (draftInput) {
      setValue(draftInput);
      setDraftInput(null);
      textareaRef.current?.focus();
    }
  }, [draftInput, setDraftInput]);

  const canSend = value.trim().length > 0 && !disabled && !isStreaming;

  function handleSend() {
    if (!canSend) return;
    onSend(value.trim());
    setValue("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }

  function handleKeyDown(e: KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  useEffect(() => {
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = "auto";
      ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
    }
  }, [value]);

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  return (
    <form
      className="overflow-visible rounded-xl transition-all duration-200"
      style={{
        background: "var(--surface-1)",
        border: "1px solid var(--border)",
      }}
      onFocus={(e) => {
        const form = e.currentTarget;
        form.style.borderColor = "var(--accent-border)";
        form.style.boxShadow = "0 0 0 1px var(--accent-border), 0 0 24px -6px rgba(20,184,166,0.08)";
      }}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node)) {
          const form = e.currentTarget;
          form.style.borderColor = "var(--border)";
          form.style.boxShadow = "none";
        }
      }}
      onSubmit={(e) => {
        e.preventDefault();
        handleSend();
      }}
    >
      {/* Textarea */}
      <div className="px-3 pt-3 pb-2">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything..."
          disabled={isStreaming}
          rows={1}
          className="max-h-[200px] min-h-[44px] w-full resize-none border-none bg-transparent text-sm outline-none"
          style={{ color: "var(--text-primary)" }}
        />
      </div>

      {/* Bottom toolbar */}
      <div
        className="flex items-center gap-1.5 px-2 py-1.5"
        style={{ borderTop: "1px solid var(--border-subtle)" }}
      >
        <ModeChips />
        <DocumentScope />

        <button
          type="button"
          onClick={() => setShowInfo(true)}
          className="flex h-7 w-7 items-center justify-center rounded-lg transition-colors duration-150"
          style={{ color: "var(--text-tertiary)" }}
          onMouseEnter={(e) => { e.currentTarget.style.background = "var(--surface-3)"; e.currentTarget.style.color = "var(--text-secondary)"; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--text-tertiary)"; }}
          title="How search works"
        >
          <CircleHelp size={14} />
        </button>

        <div className="flex-1" />

        <button
          type="submit"
          disabled={!canSend}
          className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg transition-all duration-200"
          style={{
            background: canSend ? "var(--accent)" : "var(--surface-3)",
            color: canSend ? "white" : "var(--text-tertiary)",
            ...(canSend ? { boxShadow: "0 1px 3px rgba(0,0,0,0.2), 0 0 12px -3px rgba(20,184,166,0.3)" } : {}),
          }}
          aria-label="Send message"
        >
          <ArrowUp size={15} />
        </button>
      </div>
    </form>
  );
}
