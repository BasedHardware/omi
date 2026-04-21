import { invoke } from "@tauri-apps/api/core";
import type { ChatStepHandler } from "../types";

export const goalHandler: ChatStepHandler = {
  stepId: "goal",
  acceptsTypedAnswer: true,
  buildOpenerInstruction: (signals) => {
    const context = [
      signals.projectNames.length > 0
        ? `Projects: ${signals.projectNames.slice(0, 3).join(", ")}`
        : null,
      signals.technologies.length > 0
        ? `Stack: ${signals.technologies.slice(0, 3).join(", ")}`
        : null,
      signals.webSummary ? `Web: ${signals.webSummary}` : null,
    ]
      .filter(Boolean)
      .join(". ");
    return `Ask what one thing they most want Nooto to help them move on right now. Offer a few suggestions grounded in their signals if you have any (${context || "nothing specific yet"}), or leave the suggestions generic. One friendly sentence total, no preamble.`;
  },
  fallbackOpener: () =>
    "What's the one thing you want me to help you move on right now?",
  widget: (signals) => {
    // Build chip suggestions from real signals when possible.
    const chips: { id: string; label: string }[] = [];
    if (signals.projectNames.length > 0) {
      const p = signals.projectNames[0];
      chips.push({ id: `ship_${p}`, label: `Ship ${p}` });
    }
    if (signals.technologies.length > 0) {
      chips.push({
        id: `focus_${signals.technologies[0]}`,
        label: `Focus on ${signals.technologies[0]}`,
      });
    }
    if (chips.length < 3) {
      chips.push({ id: "deep_work", label: "Protect deep work" });
    }
    if (chips.length < 4) {
      chips.push({ id: "inbox_zero", label: "Stay on top of inbox" });
    }
    return {
      type: "chips",
      options: chips,
      // Free text comes in via the main PromptInput at the bottom; no
      // duplicate inline input inside the bubble.
      allowFreeText: false,
    };
  },
  summarize: (r) => {
    if ("text" in r) return r.text;
    if ("chip" in r) return r.chip.replace(/^(ship_|focus_)/, "").replace(/_/g, " ");
    return null;
  },
  onCapture: async (r, ctx) => {
    let goal = "";
    if ("text" in r) goal = r.text.trim();
    else if ("chip" in r) {
      // Use the chip id as raw goal text (handlers could also look up labels)
      goal = r.chip.replace(/^(ship_|focus_)/, "").replace(/_/g, " ");
    }
    if (!goal) return;
    ctx.onboarding.setGoal(goal);
    try {
      await invoke("set_onboarding_goal", { goal });
    } catch {
      /* best-effort */
    }
    ctx.companion.addNote(`goal: ${goal}`);
    ctx.onboarding.advance();
  },
};
