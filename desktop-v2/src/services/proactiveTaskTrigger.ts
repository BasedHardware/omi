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
  setFrameHandler,
} from "@/services/proactiveAssistant";
import {
  shouldAnalyzeFrame,
  extractTaskFromFrame,
  persistExtractedTask,
} from "@/services/taskAssistant";
import { useTaskAssistantSettings } from "@/services/taskAssistantSettings";

let unsubscribeFrame: (() => void) | null = null;
let fallbackTimerId: ReturnType<typeof setInterval> | null = null;
let latestFrame: CapturedFrame | null = null;
let lastExtractionAt = 0;
let inflight = false;

async function runExtraction(frame: CapturedFrame, reason: string): Promise<void> {
  if (inflight) {
    console.info(`[TaskTrigger] skip ${reason} — extraction in flight`);
    return;
  }
  if (!shouldAnalyzeFrame(frame)) return;
  inflight = true;
  lastExtractionAt = Date.now();
  try {
    console.info(`[TaskTrigger] extract (${reason}) app=${frame.appName}`);
    const result = await extractTaskFromFrame(frame);
    if (result.hasNewTask && result.task) {
      console.info(
        `[TaskTrigger] extracted "${result.task.title}" (conf=${result.task.confidence.toFixed(2)})`,
      );
      await persistExtractedTask(frame, result);
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

  setFrameHandler((frame) => {
    latestFrame = frame;
    void runExtraction(frame, "context-switch");
  });
  unsubscribeFrame = () => setFrameHandler(() => {});

  const intervalS = useTaskAssistantSettings.getState().extractionIntervalSeconds;
  fallbackTimerId = setInterval(() => {
    if (!latestFrame) return;
    const elapsed = (Date.now() - lastExtractionAt) / 1000;
    if (elapsed < intervalS) return;
    void runExtraction(latestFrame, "fallback");
  }, Math.max(30, Math.floor(intervalS / 4)) * 1000);

  console.info(
    `[TaskTrigger] started (fallback interval=${intervalS}s)`,
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
