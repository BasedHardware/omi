import type { ChatStepHandler } from "../types";

export const floatingBarShortcutHandler: ChatStepHandler = {
  stepId: "floating_bar_shortcut",
  acceptsTypedAnswer: false,
  buildOpenerInstruction: () =>
    "They're picking a keyboard shortcut for the floating bar (quick-action popover). One sentence: ask them to press the combination they want. Keep it casual.",
  fallbackOpener: () =>
    "Pick a shortcut for the floating bar — press the keys you want to use.",
  widget: () => ({
    type: "shortcut_capture",
    kind: "floating_bar",
    allowModifierOnly: false,
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
