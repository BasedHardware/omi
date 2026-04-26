import type { ChatStepHandler } from "../types";

export const floatingBarShortcutHandler: ChatStepHandler = {
  stepId: "floating_bar_shortcut",
  acceptsTypedAnswer: false,
  buildOpenerInstruction: () =>
    "They're confirming the floating-bar shortcut. Nooto has a default — Cmd+\\ — and they can try it, keep it, or change it. One sentence, casual.",
  fallbackOpener: () =>
    "The floating bar opens with Cmd+\\. Try it, keep it, or pick something else.",
  widget: () => ({
    type: "shortcut_capture",
    kind: "floating_bar",
    allowModifierOnly: false,
    defaultChord: "Cmd+\\",
  }),
  summarize: (r) => ("chord" in r ? r.chord : null),
  onCapture: async (r, ctx) => {
    const chord = "chord" in r ? r.chord : "";
    if (!chord) return;
    ctx.onboarding.setFloatingBarShortcut(chord);
    ctx.companion.addNote(`floating bar: ${chord}`);
    ctx.onboarding.advance();
  },
};
