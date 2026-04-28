/**
 * Proactive Task Trigger — wires the proactive frame stream into the
 * TaskAssistant pipeline.
 *
 * Two firing rules (Swift parity, see `TaskAssistant.swift`):
 *
 * 1. **Context-switch path**: every frame distributed by `proactiveAssistant.ts`
 *    is checked. The coordinator already debounces (3s analysis delay after
 *    the latest context change), so each delivery is a stable post-switch
 *    sample.
 *
 * 2. **Periodic fallback**: `EXTRACTION_INTERVAL_S` (default 600s = 10min)
 *    timer that re-runs analysis on the latest captured frame even if no
 *    context switch happened in that window. Catches cases where the user
 *    stays in one app and a new request appears (e.g. Slack notification
 *    arrives but the user doesn't switch apps).
 *
 * Inflight guard: only one extraction runs at a time. If a new frame arrives
 * mid-extraction, we skip it (the next one will come within ~3s anyway).
 */

import {
  CapturedFrame,
  addFrameListener,
  startMonitoring,
  stopMonitoring,
} from "@/services/proactiveAssistant";
import {
  shouldAnalyzeFrame,
  extractTaskFromFrame,
  persistExtractedTask,
  MESSAGING_APPS,
} from "@/services/taskAssistant";
import { recordFrame as recordResearchFrame } from "@/services/researchIntent";
import { useTaskAssistantSettings } from "@/services/taskAssistantSettings";
import { notify } from "@/services/notifications";

let unsubscribeFrame: (() => void) | null = null;
let fallbackTimerId: ReturnType<typeof setInterval> | null = null;
let latestFrame: CapturedFrame | null = null;
let lastExtractionAt = 0;
let inflight = false;

async function runExtraction(
  frame: CapturedFrame,
  options: { researchHint?: string } = {},
): Promise<void> {
  if (inflight) return;
  if (!shouldAnalyzeFrame(frame)) return;
  inflight = true;
  lastExtractionAt = Date.now();
  try {
    const result = await extractTaskFromFrame(frame, options);
    if (result.hasNewTask && result.task) {
      await persistExtractedTask(frame, result);

      if (useTaskAssistantSettings.getState().notificationsEnabled) {
        void notify("New task", result.task.title);
      }
    }
  } catch (err) {
    console.warn("[TaskTrigger] extraction failed:", err);
  } finally {
    inflight = false;
  }
}

/** Start listening for frames + arm the periodic fallback. Idempotent. */
export function startTaskTrigger(): void {
  if (unsubscribeFrame) return;

  const off = addFrameListener((frame) => {
    latestFrame = frame;
    // Multi-frame "user is researching this" detector. When it fires we
    // bypass the normal context-switch path and analyze immediately with a
    // hint, since single-frame heuristics miss "decide on X" tasks.
    const research = recordResearchFrame(frame);
    if (research.flagged) {
      void runExtraction(frame, { researchHint: research.hint });
      return;
    }
    void runExtraction(frame);
  });
  startMonitoring();
  unsubscribeFrame = () => {
    off();
    stopMonitoring();
  };

  const intervalS = useTaskAssistantSettings.getState().extractionIntervalSeconds;
  // Messaging apps get a faster cadence — when the user types a quick "I'll
  // do that" / "vou fazer isso" we want the next sweep to catch it before
  // they context-switch, not 10 minutes later. Cap at 1/4 the global rate
  // so we never under-shoot it.
  const messagingIntervalS = Math.max(60, Math.min(120, Math.floor(intervalS / 4)));
  // Tick four times per (global) interval — same cadence as before, but the
  // per-frame check now considers a per-app threshold.
  const tickMs = Math.max(30, Math.floor(intervalS / 4)) * 1000;
  fallbackTimerId = setInterval(() => {
    if (!latestFrame) return;
    const elapsed = (Date.now() - lastExtractionAt) / 1000;
    const threshold = MESSAGING_APPS.has(latestFrame.appName) ? messagingIntervalS : intervalS;
    if (elapsed < threshold) return;
    void runExtraction(latestFrame);
  }, tickMs);

  console.info(
    `[TaskTrigger] started (fallback default=${intervalS}s, messaging=${messagingIntervalS}s)`,
  );
}

/** Stop the trigger and release subscriptions. */
export function stopTaskTrigger(): void {
  if (unsubscribeFrame) {
    unsubscribeFrame();
    unsubscribeFrame = null;
  }
  if (fallbackTimerId !== null) {
    clearInterval(fallbackTimerId);
    fallbackTimerId = null;
  }
  latestFrame = null;
  lastExtractionAt = 0;
  inflight = false;
  console.info("[TaskTrigger] stopped");
}
