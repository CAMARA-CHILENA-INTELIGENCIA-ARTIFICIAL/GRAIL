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
  const { isStreaming, setShowInfo } = useChatStore();

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
      className="overflow-visible rounded-xl border border-zinc-800 bg-zinc-900 transition-colors duration-200 focus-within:border-zinc-700"
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
          className="max-h-[200px] min-h-[44px] w-full resize-none border-none bg-transparent text-sm text-zinc-50 placeholder-zinc-500 outline-none"
        />
      </div>

      {/* Bottom toolbar */}
      <div className="flex items-center gap-1.5 border-t border-zinc-800/60 px-2 py-1.5">
        {/* Mode chips */}
        <ModeChips />

        {/* Document scope */}
        <DocumentScope />

        {/* Info button */}
        <button
          type="button"
          onClick={() => setShowInfo(true)}
          className="flex h-7 w-7 items-center justify-center rounded-full text-zinc-500 hover:bg-zinc-800/50 hover:text-zinc-300"
          title="How search works"
        >
          <CircleHelp size={14} />
        </button>

        <div className="flex-1" />

        {/* Send button */}
        <button
          type="submit"
          disabled={!canSend}
          className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg transition-colors ${
            canSend
              ? "bg-teal-600 text-white hover:bg-teal-500"
              : "bg-zinc-800 text-zinc-600"
          }`}
          aria-label="Send message"
        >
          <ArrowUp size={16} />
        </button>
      </div>
    </form>
  );
}
