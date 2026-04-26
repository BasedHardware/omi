import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { KeyCapDisplay } from "../../animations/KeyCapDisplay";
import { Suggestion } from "@/components/ai-elements/suggestion";
import { useShortcutCapture } from "@/hooks/useShortcutCapture";
import type { StepWidget, WidgetResult } from "../types";

interface Props {
  widget: Extract<StepWidget, { type: "shortcut_capture" }>;
  disabled: boolean;
  onCapture: (result: WidgetResult, summary: string | null) => void;
}

/** Live keyboard-chord capture widget.
 *
 *  When `defaultChord` is set, the widget starts in "confirm default" mode —
 *  the user sees the suggested chord and can Use / Try it / Change. Entering
 *  Change mode detaches the default and swaps to live capture. This keeps
 *  the happy path (keep the default) one click and still allows re-pick.
 */
export function ShortcutCaptureWidget({ widget, disabled, onCapture }: Props) {
  const committedRef = useRef(false);
  const hasDefault = !!widget.defaultChord;
  const [mode, setMode] = useState<"default" | "capture">(
    hasDefault ? "default" : "capture",
  );

  // Live capture is only armed once the user opts into re-picking — otherwise
  // pressing Cmd+\ to test the default would immediately swap into capture.
  const captureDisabled = disabled || mode !== "capture";
  const { held, captured, reset } = useShortcutCapture({
    allowModifierOnly: widget.allowModifierOnly,
    disabled: captureDisabled,
  });

  // Suspend pre-registered global shortcuts so the user can pick already-
  // bound combos (Cmd+\ is the floating-bar default). Only while capturing —
  // the "try it" button explicitly needs the floating bar to respond.
  useEffect(() => {
    if (mode !== "capture" || disabled) return;
    invoke("suspend_global_shortcuts").catch((err) =>
      console.warn("[shortcut_capture] suspend failed:", err),
    );
    return () => {
      invoke("restore_global_shortcuts").catch((err) =>
        console.warn("[shortcut_capture] restore failed:", err),
      );
    };
  }, [mode, disabled]);

  const parsedDefault = widget.defaultChord ? parseChord(widget.defaultChord) : null;
  const liveKeys = held.length > 0 ? held : (captured ?? []);
  const displayKeys =
    mode === "default" && !captured && parsedDefault ? parsedDefault : liveKeys;

  const commit = (chordText: string) => {
    if (committedRef.current || disabled || !chordText) return;
    committedRef.current = true;
    onCapture({ chord: chordText }, chordText);
  };

  const handleUseDefault = () => {
    if (!widget.defaultChord) return;
    commit(widget.defaultChord);
  };

  const handleUseCaptured = () => {
    if (!captured) return;
    commit(captured.join("+"));
  };

  const handleChange = () => {
    reset();
    setMode("capture");
  };

  const handleTryIt = async () => {
    if (widget.kind !== "floating_bar") return;
    try {
      await invoke("toggle_floating_bar");
    } catch (err) {
      console.warn("[shortcut_capture] toggle_floating_bar failed:", err);
    }
  };

  const helper = disabled
    ? "Saved."
    : mode === "default"
      ? "You can try it, keep it, or change it."
      : held.length > 0
        ? "Holding…"
        : captured
          ? "Looks good?"
          : widget.allowModifierOnly
            ? "Hold any key or modifier — release to commit."
            : "Press the combination you want.";

  return (
    <div className="flex flex-col gap-2 mt-2">
      <KeyCapDisplay
        keys={displayKeys}
        active={!disabled && (mode === "default" || !captured)}
      />
      <div className="text-[12px] text-muted-foreground">{helper}</div>

      {!disabled && mode === "default" ? (
        <div className="flex items-center gap-2 flex-wrap">
          <Suggestion
            suggestion="use"
            onClick={handleUseDefault}
            variant="default"
            className="text-primary-foreground hover:text-primary-foreground border-transparent hover:border-transparent"
          >
            Keep this shortcut
          </Suggestion>
          {widget.kind === "floating_bar" ? (
            <Suggestion suggestion="try" onClick={handleTryIt}>
              Try it
            </Suggestion>
          ) : null}
          <Suggestion suggestion="change" onClick={handleChange}>
            Change
          </Suggestion>
        </div>
      ) : null}

      {!disabled && mode === "capture" && captured ? (
        <div className="flex items-center gap-2 flex-wrap">
          <Suggestion
            suggestion="use"
            onClick={handleUseCaptured}
            variant="default"
            className="text-primary-foreground hover:text-primary-foreground border-transparent hover:border-transparent"
          >
            Use this shortcut
          </Suggestion>
          <Suggestion suggestion="change" onClick={() => reset()}>
            Change
          </Suggestion>
        </div>
      ) : null}
    </div>
  );
}

/** Parse a stored chord string ("Cmd+\\") into label parts the KeyCapDisplay
 *  understands. "\\" is printable, so we leave it as-is. */
function parseChord(chord: string): string[] {
  return chord.split("+").map((p) => p.trim()).filter(Boolean);
}
