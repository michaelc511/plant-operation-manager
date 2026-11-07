import { useState, type FormEvent, type KeyboardEvent } from "react";

type Props = {
  disabled: boolean;
  onAsk: (question: string) => void;
};

const MAX = 1000;

export function AskBar({ disabled, onAsk }: Props) {
  const [text, setText] = useState("");
  const question = text.trim();
  const canSend = !disabled && question.length >= 3;

  function submit(e?: FormEvent) {
    e?.preventDefault();
    if (!canSend) return;
    onAsk(question);
    setText("");
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends on a keyboard; Shift+Enter adds a new line.
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <form className="ask-bar" onSubmit={submit}>
      <label htmlFor="question" className="visually-hidden">
        Your question
      </label>
      <textarea
        id="question"
        rows={1}
        maxLength={MAX}
        placeholder="Ask a question…"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        enterKeyHint="send"
      />
      <button type="submit" disabled={!canSend} aria-label="Ask">
        <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
          <path d="M3 20.5 21 12 3 3.5l.01 6.6L15 12 3.01 13.9z" fill="currentColor" />
        </svg>
      </button>
    </form>
  );
}
