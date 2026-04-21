import { Suggestion, Suggestions } from "@/components/ai-elements/suggestion";
import type { StepWidget, WidgetResult } from "../types";

interface Props {
  widget: Extract<StepWidget, { type: "acknowledge" }>;
  disabled: boolean;
  onCapture: (result: WidgetResult, summary: string | null) => void;
}

/** Single-chip acknowledge bubble. Commits immediately on click. */
export function AcknowledgeWidget({ widget, disabled, onCapture }: Props) {
  return (
    <div className="mt-2">
      <Suggestions>
        <Suggestion
          suggestion="ack"
          onClick={() => onCapture({ ack: true }, widget.label)}
          disabled={disabled}
          variant="default"
          className="text-primary-foreground hover:text-primary-foreground border-transparent hover:border-transparent"
        >
          {widget.label}
        </Suggestion>
        {widget.skippable ? (
          <Suggestion
            suggestion="skip"
            onClick={() => onCapture({ ack: true }, "Skipped")}
            disabled={disabled}
          >
            Skip
          </Suggestion>
        ) : null}
      </Suggestions>
    </div>
  );
}
