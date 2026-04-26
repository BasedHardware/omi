/**
 * SpeechBubble — shows Gemini's text answer inside the CompanionBuddy window.
 *
 * Rendered inside the buddy window, positioned above the orb.
 * The buddy window resizes dynamically:
 *   - Idle / listening / thinking: 96×96 (orb only, set by Phase 1)
 *   - Speaking: 320×auto (bubble + orb), using getCurrentWindow().setSize()
 *
 * The window size change is handled here via a useEffect that watches
 * companionStore.state so the buddy window can grow and shrink automatically.
 *
 * Word-boundary highlighting: `tts:willSpeakRange` events update `speakingRange`
 * in the store. The text is split into three spans (before / active / after);
 * the active span uses `text-primary font-medium` (shadcn semantic tokens).
 */

import { useEffect } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { PhysicalSize } from "@tauri-apps/api/dpi";
import { useCompanionStore } from "@/stores/companionStore";

/** Width of the expanded buddy window when showing the speech bubble (px). */
const BUBBLE_WINDOW_W = 320;
/** Height of the expanded buddy window (orb 96 + bubble ~120 + gap 8). */
const BUBBLE_WINDOW_H = 224;
/** Compact window size used when no bubble is shown. */
const COMPACT_WINDOW_W = 96;
const COMPACT_WINDOW_H = 96;

/** Render `text` with the character range [start, end) highlighted. */
function HighlightedText({
  text,
  start,
  end,
}: {
  text: string;
  start: number;
  end: number;
}) {
  // Clamp to valid indices so out-of-bounds TTS ranges never throw.
  const safeStart = Math.max(0, Math.min(start, text.length));
  const safeEnd = Math.max(safeStart, Math.min(end, text.length));

  const before = text.slice(0, safeStart);
  const inside = text.slice(safeStart, safeEnd);
  const after = text.slice(safeEnd);

  return (
    <>
      {before && <span>{before}</span>}
      {inside && <span className="text-primary font-medium">{inside}</span>}
      {after && <span>{after}</span>}
    </>
  );
}

export function SpeechBubble() {
  const state = useCompanionStore((s) => s.state);
  const answer = useCompanionStore((s) => s.answer);
  const errorMessage = useCompanionStore((s) => s.errorMessage);
  const speakingRange = useCompanionStore((s) => s.speakingRange);

  const isSpeaking = state === "speaking" && !!answer;
  const isError = state === "idle" && !!errorMessage;
  const showBubble = isSpeaking || isError;

  // Resize the buddy window when the bubble appears / disappears.
  useEffect(() => {
    const win = getCurrentWindow();
    if (showBubble) {
      win.setSize(new PhysicalSize(BUBBLE_WINDOW_W, BUBBLE_WINDOW_H)).catch((e) =>
        console.warn("[SpeechBubble] setSize failed:", e),
      );
    } else {
      win.setSize(new PhysicalSize(COMPACT_WINDOW_W, COMPACT_WINDOW_H)).catch((e) =>
        console.warn("[SpeechBubble] setSize failed:", e),
      );
    }
  }, [showBubble]);

  if (!showBubble) return null;

  return (
    <div
      className={[
        "absolute bottom-full mb-2 left-1/2 -translate-x-1/2",
        "w-72 rounded-2xl px-4 py-3",
        "bg-card/95 backdrop-blur-sm border border-border",
        "shadow-xl",
        "text-card-foreground text-sm leading-relaxed",
        "transition-opacity duration-300",
      ].join(" ")}
      role="status"
      aria-live="polite"
    >
      {isError ? (
        <span className="text-destructive">{errorMessage}</span>
      ) : answer && speakingRange ? (
        <HighlightedText text={answer} start={speakingRange.start} end={speakingRange.end} />
      ) : (
        <span>{answer}</span>
      )}
    </div>
  );
}
