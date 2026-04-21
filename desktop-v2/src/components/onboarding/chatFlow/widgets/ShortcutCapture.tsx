import { useEffect, useRef } from "react";
import { KeyCapDisplay } from "../../animations/KeyCapDisplay";
import { useShortcutCapture } from "@/hooks/useShortcutCapture";
import type { StepWidget, WidgetResult } from "../types";

interface Props {
  widget: Extract<StepWidget, { type: "shortcut_capture" }>;
  disabled: boolean;
  onCapture: (result: WidgetResult, summary: string | null) => void;
}

/** Live keyboard-chord capture widget. Reuses the existing hook; auto-
 *  commits on release (for modifier-only chords) or once a non-modifier
 *  joins held modifiers (for full chords). */
export function ShortcutCaptureWidget({ widget, disabled, onCapture }: Props) {
  const capturedRef = useRef(false);
  const { held, captured } = useShortcutCapture({
    allowModifierOnly: widget.allowModifierOnly,
    onCaptured: (chord) => {
      if (capturedRef.current || disabled) return;
      capturedRef.current = true;
      const chordText = chord.join("+");
      // Small delay so the user sees the chord land before the widget
      // disables.
      window.setTimeout(() => {
        onCapture({ chord: chordText }, chordText);
      }, 250);
    },
  });

  const displayKeys = held.length > 0 ? held : (captured ?? []);

  // If the widget is already captured (re-render after onCapture), show
  // the final chord.
  useEffect(() => {
    // nothing to do — capturedRef handles idempotency inside onCaptured
  }, []);

  return (
    <div className="flex flex-col gap-2 mt-2">
      <KeyCapDisplay keys={displayKeys} active={!disabled && !captured} />
      <div className="text-[12px] text-muted-foreground">
        {disabled
          ? "Saved."
          : held.length > 0
            ? "Holding…"
            : captured
              ? "Release captured. Saving…"
              : widget.allowModifierOnly
                ? "Hold any key or modifier — release to commit."
                : "Press the combination you want."}
      </div>
    </div>
  );
}
