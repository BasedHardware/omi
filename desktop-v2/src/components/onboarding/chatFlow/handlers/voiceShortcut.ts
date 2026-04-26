import { invoke } from "@tauri-apps/api/core";
import type { ChatStepHandler } from "../types";

export const voiceShortcutHandler: ChatStepHandler = {
  stepId: "voice_shortcut",
  acceptsTypedAnswer: false,
  buildOpenerInstruction: () =>
    "They're picking a push-to-talk key for voice. One sentence: ask them to pick — modifier-only is fine (like holding Option). Casual.",
  fallbackOpener: () =>
    "Pick a push-to-talk key. Holding a single modifier like Option works great.",
  widget: () => ({
    type: "shortcut_capture",
    kind: "voice",
    allowModifierOnly: true,
  }),
  summarize: (r) => ("chord" in r ? r.chord : null),
  onCapture: async (r, ctx) => {
    const chord = "chord" in r ? r.chord : "";
    if (!chord) return;
    ctx.onboarding.setVoiceShortcut(chord);
    ctx.companion.addNote(`voice: ${chord}`);
    // PTT hold is single-key by design. If the user picked a multi-key
    // chord (e.g. "Cmd+Shift"), take the last key — conventionally the
    // non-modifier or most recently held key. This keeps the capture UI
    // flexible while still producing something the hold-listener can match.
    const ptKey = chord.split("+").pop()?.trim();
    if (ptKey) {
      try {
        await invoke("set_ptt_key", { label: ptKey });
      } catch (err) {
        console.warn("[voice_shortcut] set_ptt_key failed:", err);
      }
    }
    ctx.onboarding.advance();
  },
};
