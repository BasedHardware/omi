import type { ChatStepHandler } from "../types";

export const researchHandler: ChatStepHandler = {
  stepId: "research",
  acceptsTypedAnswer: false,
  buildOpenerInstruction: () =>
    "Tell them you're piecing together what's on their machine (projects, tech, apps) with a quick public web lookup. One warm sentence — no apology, no emoji.",
  fallbackOpener: () =>
    "Giving you a little second brain. Pulling what's on your machine and a quick web lookup.",
  widget: () => ({ type: "research_panel" }),
  summarize: () => "Second brain ready",
  onCapture: async (_r, ctx) => {
    ctx.companion.addNote("research complete");
    ctx.onboarding.advance();
  },
};
