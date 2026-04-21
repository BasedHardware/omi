/**
 * Chat-step registry — owns the ordered list of onboarding steps, the
 * platform-filtered accessor, and a helper for looking up a step's
 * handler. Handlers are imported once and registered with the companion
 * store at app startup (see OnboardingChat.tsx).
 */
import type { DesktopPlatform } from "@/lib/platform";
import { ONBOARDING_STEP_IDS } from "@/stores/onboardingStore";
import type { ChatStepHandler, StepId } from "./types";

import { nameHandler } from "./handlers/name";
import { languageHandler } from "./handlers/language";
import { trustHandler } from "./handlers/trust";
import { screenRecordingHandler } from "./handlers/screenRecording";
import { fullDiskAccessHandler } from "./handlers/fullDiskAccess";
import { fileScanHandler } from "./handlers/fileScan";
import { microphoneHandler } from "./handlers/microphone";
import { notificationsHandler } from "./handlers/notifications";
import { accessibilityHandler } from "./handlers/accessibility";
import { automationHandler } from "./handlers/automation";
import { floatingBarShortcutHandler } from "./handlers/floatingBarShortcut";
import { floatingBarDemoHandler } from "./handlers/floatingBarDemo";
import { voiceShortcutHandler } from "./handlers/voiceShortcut";
import { voiceDemoHandler } from "./handlers/voiceDemo";
import { researchHandler } from "./handlers/research";
import { goalHandler } from "./handlers/goal";
import { tasksHandler } from "./handlers/tasks";

export const ALL_HANDLERS: ChatStepHandler[] = [
  nameHandler,
  languageHandler,
  trustHandler,
  screenRecordingHandler,
  fullDiskAccessHandler,
  fileScanHandler,
  microphoneHandler,
  notificationsHandler,
  accessibilityHandler,
  automationHandler,
  floatingBarShortcutHandler,
  floatingBarDemoHandler,
  voiceShortcutHandler,
  voiceDemoHandler,
  researchHandler,
  goalHandler,
  tasksHandler,
];

const HANDLER_BY_STEP: Record<string, ChatStepHandler> = Object.fromEntries(
  ALL_HANDLERS.map((h) => [h.stepId, h]),
);

/** Canonical step order from the onboarding store. */
export const STEP_ORDER: readonly StepId[] = ONBOARDING_STEP_IDS;

export function getHandler(stepId: StepId): ChatStepHandler | undefined {
  return HANDLER_BY_STEP[stepId];
}

/** Platform-aware ordered step list. Handlers may opt out of specific
 *  platforms via `includeForPlatform`; if they do, the step disappears
 *  entirely for that platform. */
export function stepIdsForPlatform(platform: DesktopPlatform): StepId[] {
  return STEP_ORDER.filter((id) => {
    const handler = HANDLER_BY_STEP[id];
    if (!handler) return false;
    return handler.includeForPlatform
      ? handler.includeForPlatform(platform)
      : true;
  });
}
