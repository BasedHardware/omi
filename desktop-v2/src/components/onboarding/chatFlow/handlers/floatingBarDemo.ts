import type { ChatStepHandler } from "../types";

export const floatingBarDemoHandler: ChatStepHandler = {
  stepId: "floating_bar_demo",
  acceptsTypedAnswer: false,
  buildOpenerInstruction: (signals) => {
    const note = signals.notes.find((n) => n.startsWith("floating bar:"));
    const shortcut = note?.replace("floating bar: ", "") ?? "your shortcut";
    return `Acknowledge they set their floating bar shortcut to ${shortcut}. One sentence — encourage them to try it later and move on.`;
  },
  fallbackOpener: () =>
    "Saved. You can try that shortcut any time — tap continue when you're ready.",
  widget: () => ({
    type: "acknowledge",
    label: "Try it later",
  }),
  onCapture: async (_r, ctx) => {
    ctx.onboarding.advance();
  },
};
