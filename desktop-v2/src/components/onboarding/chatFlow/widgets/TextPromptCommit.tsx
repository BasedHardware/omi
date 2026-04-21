import { useEffect, useRef, useState, type FormEvent } from "react";
import { Input } from "@/components/ui/input";
import { Suggestion } from "@/components/ai-elements/suggestion";
import type { StepWidget, WidgetResult } from "../types";

interface Props {
  widget: Extract<StepWidget, { type: "text_prompt" }>;
  disabled: boolean;
  onCapture: (result: WidgetResult, summary: string | null) => void;
}

/** Inline text input bubble. Commits on Enter or Send click. The main
 *  PromptInput at the bottom also routes typed input to this step's
 *  handler when the handler has `acceptsTypedAnswer`, so this widget is
 *  redundant for keyboard-first users but useful as a visual cue. */
export function TextPromptCommitWidget({ widget, disabled, onCapture }: Props) {
  const [draft, setDraft] = useState(widget.initialValue ?? "");
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!disabled) inputRef.current?.focus();
  }, [disabled]);

  const commit = () => {
    const trimmed = draft.trim();
    if (!trimmed || disabled) return;
    onCapture({ text: trimmed }, trimmed);
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    commit();
  };

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-2 mt-2">
      <Input
        ref={inputRef}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        placeholder={widget.placeholder}
        disabled={disabled}
        className="h-9 text-[13px]"
      />
      <Suggestion
        suggestion="commit"
        onClick={commit}
        disabled={disabled || draft.trim().length === 0}
        variant="secondary"
      >
        Send
      </Suggestion>
    </form>
  );
}
