import type { ChatStepHandler } from "../types";

export const fileScanHandler: ChatStepHandler = {
  stepId: "file_scan",
  acceptsTypedAnswer: false,
  buildOpenerInstruction: () =>
    "Nooto is about to scan their home folder for projects (filenames only, never contents). One sentence — curious and forward-looking, not clinical.",
  fallbackOpener: () =>
    "I'm going to take a quick look at your home folder — just filenames — to see what you're working on.",
  widget: () => ({ type: "file_scan_progress" }),
  summarize: () => "Scan complete",
  onCapture: async (_r, ctx) => {
    ctx.companion.addNote("file scan complete");
    ctx.onboarding.advance();
  },
};
