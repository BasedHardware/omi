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
    ctx.onboarding.advance();
  },
};
