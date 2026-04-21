import { invoke } from "@tauri-apps/api/core";
import type { ChatStepHandler } from "../types";

export const nameHandler: ChatStepHandler = {
  stepId: "name",
  acceptsTypedAnswer: true,
  buildOpenerInstruction: () =>
    "First time meeting. Ask in one warm sentence what they'd like you to call them. No emoji, no lists.",
  fallbackOpener: () => "Hey — what should I call you?",
  widget: () => ({ type: "none" }),
  summarize: (r) => ("text" in r ? r.text : null),
  onCapture: async (r, ctx) => {
    const name = "text" in r ? r.text.trim() : "";
    if (!name) return;
    ctx.onboarding.setPreferredName(name);
    ctx.companion.updateSignals({ preferredName: name });
    try {
      await invoke("set_user_preferred_name", { name });
    } catch {
      /* best-effort */
    }
    ctx.onboarding.advance();
  },
};
