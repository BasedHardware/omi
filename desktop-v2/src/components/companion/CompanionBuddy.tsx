/**
 * CompanionBuddy — the cursor-anchored sprite window.
 *
 * Renders the Rive "opal" orb (Canvas2D pipeline so it works on transparent
 * macOS windows) plus the SpeechBubble overlay when state === 'speaking'.
 *
 * The orb is intentionally always-animating (driven via the "thinking" SM
 * input) so it reads as a living presence next to the cursor regardless of
 * the assistant's logical state. State changes are surfaced via the HUD at
 * top-of-screen and the speech bubble — the buddy itself just signals "I'm
 * here" with continuous motion.
 *
 * Window geometry:
 *   - Compact (idle / listening / thinking): 96×96 (tauri.conf.json default,
 *     restored by SpeechBubble's cleanup useEffect).
 *   - Expanded (speaking): 320×224 (managed by SpeechBubble).
 *
 * Position is driven entirely by the Rust cursor tracker at ~60 Hz; this
 * component never needs to know its screen coordinates.
 */
import { useEffect } from "react";
import { CompanionOrb } from "@/components/companion/CompanionOrb";
import { SpeechBubble } from "@/components/companion/SpeechBubble";

export function CompanionBuddy() {
  // Force dark class so SpeechBubble + any inherited typography use the
  // dark palette to match the buddy's transparent-on-desktop aesthetic.
  useEffect(() => {
    document.documentElement.classList.add("dark");
  }, []);

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        display: "flex",
        alignItems: "flex-end",
        justifyContent: "center",
        pointerEvents: "none",
      }}
    >
      <SpeechBubble />
      <CompanionOrb size={88} />
    </div>
  );
}
