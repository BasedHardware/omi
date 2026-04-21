import type { ChatStepHandler } from "../types";

export const tasksHandler: ChatStepHandler = {
  stepId: "tasks",
  acceptsTypedAnswer: false,
  buildOpenerInstruction: (signals) =>
    `Close out onboarding. Tell them Nooto will automatically turn commitments from meetings and chats into tasks they can act on${signals.preferredName ? `, ${signals.preferredName}` : ""}. One warm sentence, no list.`,
  fallbackOpener: () =>
    "I'll quietly turn the commitments from your day into tasks. You'll never need to take notes in a meeting again.",
  widget: () => ({ type: "acknowledge", label: "Let's go" }),
  onCapture: async (_r, ctx) => {
    await ctx.onboarding.markCompleted();
    ctx.finishOnboarding();
  },
};
