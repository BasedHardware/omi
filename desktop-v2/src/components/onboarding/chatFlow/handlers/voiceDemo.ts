import type { ChatStepHandler } from "../types";

export const voiceDemoHandler: ChatStepHandler = {
  stepId: "voice_demo",
  acceptsTypedAnswer: false,
  buildOpenerInstruction: (signals) => {
    const note = signals.notes.find((n) => n.startsWith("voice:"));
    const shortcut = note?.replace("voice: ", "") ?? "your key";
    return `Acknowledge they set push-to-talk to ${shortcut}. One sentence encouraging them to try it when ready.`;
  },
  fallbackOpener: () =>
    "Saved. Hold that key any time to talk to me — we can move on.",
  widget: () => ({ type: "acknowledge", label: "Got it" }),
  onCapture: async (_r, ctx) => {
    ctx.onboarding.advance();
  },
};
