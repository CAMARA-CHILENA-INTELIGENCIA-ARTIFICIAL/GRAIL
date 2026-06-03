import { useState, useRef, useEffect, type KeyboardEvent } from "react";
import { ArrowUp, HelpCircle, FileText } from "lucide-react";
import { useChatStore, useSessionStore } from "../lib/store";
import { useT } from "../lib/i18n";
import { ModeChips, DocumentScopePill, DocumentPicker } from "./ModeSelector";

interface ChatInputProps {
  onSend: (message: string) => void;
}

export default function ChatInput({ onSend }: ChatInputProps) {
  const [value, setValue] = useState("");
  const [docPickerOpen, setDocPickerOpen] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const {
    isStreaming,
    setShowInfo,
    draftInput,
    setDraftInput,
    documents,
  } = useChatStore();
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const t = useT();

  useEffect(() => {
    textareaRef.current?.focus();
  }, [activeSessionId]);

  useEffect(() => {
    if (draftInput) {
      setValue(draftInput);
      setDraftInput(null);
      textareaRef.current?.focus();
    }
  }, [draftInput, setDraftInput]);

  const canSend = value.trim().length > 0 && !isStreaming;

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
      ta.style.height = Math.min(ta.scrollHeight, 140) + "px";
    }
  }, [value]);

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  return (
    <form
      className="composer"
      onSubmit={(e) => {
        e.preventDefault();
        handleSend();
      }}
    >
      <div className="composer-top">
        <ModeChips />
        <div className="composer-tools">
          {documents.length > 0 && (
            <div style={{ position: "relative" }}>
              <button
                type="button"
                className="tool-btn"
                onClick={() => setDocPickerOpen((v) => !v)}
                title={t("composer.docScopeTitle")}
              >
                <FileText size={15} />
              </button>
              {docPickerOpen && (
                <DocumentPicker onClose={() => setDocPickerOpen(false)} />
              )}
            </div>
          )}
          <button
            type="button"
            className="tool-btn"
            onClick={() => setShowInfo(true)}
            title={t("composer.helpTitle")}
          >
            <HelpCircle size={15} />
          </button>
        </div>
      </div>

      <DocumentScopePill />

      <div className="composer-input">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t("composer.placeholder")}
          disabled={isStreaming}
          rows={1}
        />
        <button
          type="submit"
          className={`send ${canSend ? "" : "disabled"}`}
          disabled={!canSend}
          aria-label={t("composer.sendAria")}
        >
          <ArrowUp size={16} />
        </button>
      </div>
    </form>
  );
}
