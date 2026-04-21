import { useState, type FormEvent } from "react";
import { Suggestion, Suggestions } from "@/components/ai-elements/suggestion";
import { Input } from "@/components/ui/input";
import type { ChipOption, StepWidget, WidgetResult } from "../types";

interface Props {
  widget: Extract<StepWidget, { type: "chips" }>;
  disabled: boolean;
  onCapture: (result: WidgetResult, summary: string | null) => void;
}

/** Chip row (reuses ai-elements Suggestions) + optional inline free-text
 *  field. Clicking a chip OR pressing Enter on the input commits the step. */
export function ChipGroupWidget({ widget, disabled, onCapture }: Props) {
  const [draft, setDraft] = useState("");

  const handleChip = (chipId: string) => {
    if (disabled) return;
    const option = widget.options.find((o) => o.id === chipId);
    onCapture({ chip: chipId }, option?.label ?? chipId);
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (disabled) return;
    const trimmed = draft.trim();
    if (!trimmed) return;
    onCapture({ text: trimmed }, trimmed);
  };

  return (
    <div className="flex flex-col gap-2 mt-2">
      <Suggestions>
        {widget.options.map((option: ChipOption) => (
          <Suggestion
            key={option.id}
            suggestion={option.id}
            onClick={handleChip}
            disabled={disabled}
            variant="outline"
          >
            <span className="flex flex-col items-start leading-tight">
              <span className="text-[13px] font-medium">{option.label}</span>
              {option.sublabel ? (
                <span className="text-[11px] text-muted-foreground">
                  {option.sublabel}
                </span>
              ) : null}
            </span>
          </Suggestion>
        ))}
      </Suggestions>

      {widget.allowFreeText ? (
        <form onSubmit={handleSubmit} className="flex items-center gap-2">
          <Input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={widget.placeholder ?? "Type your answer"}
            disabled={disabled}
            className="h-9 text-[13px]"
          />
          <Suggestion
            suggestion="submit"
            onClick={() => handleSubmit(new Event("submit") as unknown as FormEvent)}
            disabled={disabled || draft.trim().length === 0}
            variant="secondary"
          >
            Send
          </Suggestion>
        </form>
      ) : null}
    </div>
  );
}
