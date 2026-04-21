import type { ChatStepHandler } from "../types";

export const trustHandler: ChatStepHandler = {
  stepId: "trust",
  acceptsTypedAnswer: false,
  buildOpenerInstruction: () =>
    "Before permissions, reassure them in two short sentences: Nooto is open source, local-first, and primary data never leaves their machine. End with 'Sound good?'",
  fallbackOpener: () =>
    "Before we touch anything, two things: Nooto is open source and local-first. Primary data stays on your machine. Sound good?",
  widget: () => ({
    type: "acknowledge",
    label: "Sounds good",
  }),
  onCapture: async (_r, ctx) => {
    ctx.companion.addNote("trust acknowledged");
    ctx.onboarding.advance();
  },
};
