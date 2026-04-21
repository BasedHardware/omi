import type { ChatStepHandler, StepId } from "../types";
import type { DesktopPlatform } from "@/lib/platform";

interface Spec {
  stepId: StepId;
  kind: string;
  label: string;
  includeForPlatform?: (p: DesktopPlatform) => boolean;
  /** Gemini instruction fed to the opener. */
  instruction: string;
  /** Static copy when Gemini is unavailable. */
  fallback: string;
  /** Small helper line shown next to the grant button. */
  helper?: string;
  /** If true, on Linux the step becomes an Acknowledge widget instead of a
   *  permission prompt (Linux doesn't have app-level prompts for most). */
  linuxInformational?: boolean;
}

export function buildPermissionHandler(spec: Spec): ChatStepHandler {
  return {
    stepId: spec.stepId,
    acceptsTypedAnswer: false,
    includeForPlatform: spec.includeForPlatform,
    skippable: true,
    buildOpenerInstruction: () => spec.instruction,
    fallbackOpener: () => spec.fallback,
    widget: (_s, platform) => {
      if (spec.linuxInformational && platform === "linux") {
        return { type: "acknowledge", label: "Got it" };
      }
      return {
        type: "permission_grant",
        kind: spec.kind,
        label: spec.label,
        skippable: true,
        helper: spec.helper,
      };
    },
    summarize: (r) => {
      if ("granted" in r) return r.granted ? "Granted" : "Skipped";
      if ("ack" in r) return "Got it";
      return null;
    },
    onCapture: async (r, ctx) => {
      if ("granted" in r) {
        ctx.onboarding.setPermission(spec.kind, r.granted ? "granted" : "not_granted");
        ctx.companion.addNote(
          r.granted ? `${spec.kind} granted` : `${spec.kind} skipped`,
        );
      } else if ("ack" in r) {
        ctx.companion.addNote(`${spec.kind} acknowledged`);
      }
      ctx.onboarding.advance();
    },
  };
}
