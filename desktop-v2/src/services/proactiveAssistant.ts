/**
 * Proactive Assistant Coordinator — event-driven frame distribution.
 *
 * Ported from the Swift app's ProactiveAssistantsPlugin + AssistantCoordinator.
 *
 * Architecture:
 * - Captures frames every ~1 second
 * - Detects context changes (app switch / window title change)
 * - On context change: starts a 3-second analysis delay
 * - After delay: distributes the latest frame to the FocusAssistant
 * - 60-second fallback: re-distributes even without context change
 *
 * This file is the "main loop" — it owns the capture timer and delay logic.
 * The actual analysis lives in focusAssistant.ts.
 */

import { takeScreenshotWithOcr, getActiveWindow } from "@/services/rewind";
import {
  didContextChange,
  updateContext,
  resetContext,
} from "@/services/contextDetection";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface CapturedFrame {
  /** Base64-encoded JPEG image data. */
  imageBase64: string;
  /** OCR text extracted from the screenshot. */
  ocrText: string;
  /** Name of the active application. */
  appName: string;
  /** Title of the active window. */
  windowTitle: string;
  /** Monotonically increasing frame number. */
  frameNumber: number;
  /** Timestamp of capture. */
  captureTime: Date;
  /** Database ID of the stored screenshot (null if deduped). */
  dbId: number | null;
}

/** Callback invoked when a frame should be analyzed. */
export type FrameHandler = (frame: CapturedFrame) => void;

/** Callback invoked when context changes (for UI updates). */
export type ContextChangeHandler = (appName: string, windowTitle: string) => void;

// ---------------------------------------------------------------------------
// Constants (matching Swift app)
// ---------------------------------------------------------------------------

/** Capture interval in ms — Swift `RewindSettings.captureInterval` default. */
const CAPTURE_INTERVAL_MS = 3_000;

/**
 * Distribution debounce after context change (seconds) — Swift
 * `ProactiveAssistantsPlugin.distributeFrameIfChanged` uses 3s. Lets rapid
 * Cmd-Tab spam settle before the (expensive) LLM analysis fires.
 */
const ANALYSIS_DELAY_S = 3;

/**
 * Fallback distribution interval (seconds) — Swift
 * `ProactiveAssistantsPlugin.distributionFallbackInterval`. Re-distribute
 * even without a context change to catch visual-only updates.
 */
const FALLBACK_INTERVAL_S = 60;

/** Screenshot config for focus analysis — lower quality than Rewind. */
const CAPTURE_CONFIG = { quality: 70, max_width: 1280 };

// ---------------------------------------------------------------------------
// Coordinator state
// ---------------------------------------------------------------------------

let captureTimerId: ReturnType<typeof setInterval> | null = null;
let delayTimerId: ReturnType<typeof setTimeout> | null = null;
let frameNumber = 0;
let lastDistributeTime = 0;
let isInDelayPeriod = false;
let latestFrame: CapturedFrame | null = null;
let isCapturing = false;

/**
 * Ref count for capture-loop consumers. Focus, Memory, and Task each take a
 * slot; the loop only stops when the last consumer releases.
 */
let monitoringRefCount = 0;

/** Fan-out list of frame listeners. Swift parity: AssistantCoordinator. */
const frameListeners = new Set<FrameHandler>();

/** Registered handler for context changes. */
let onContextChange: ContextChangeHandler | null = null;

/** Handler for delay period state changes (for UI countdowns). */
let onDelayStateChange: ((delayEndTime: Date | null) => void) | null = null;

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Subscribe to the proactive frame stream. Returns an unsubscribe function.
 *
 * Multiple consumers (Focus, Memory, Task) can subscribe simultaneously —
 * each frame is fanned out to every listener. Matches the Swift
 * AssistantCoordinator pattern.
 */
export function addFrameListener(handler: FrameHandler): () => void {
  frameListeners.add(handler);
  return () => {
    frameListeners.delete(handler);
  };
}

/**
 * Register the context change handler. Single-slot (only the FocusStore
 * currently uses this for UI state).
 */
export function setContextChangeHandler(handler: ContextChangeHandler): void {
  onContextChange = handler;
}

/**
 * Register the delay state change handler.
 */
export function setDelayStateHandler(handler: (delayEndTime: Date | null) => void): void {
  onDelayStateChange = handler;
}

/**
 * Start the proactive monitoring loop. Ref-counted: callers must pair every
 * `startMonitoring()` with a matching `stopMonitoring()`. The underlying
 * capture timer starts on the first call and stops on the last release.
 */
export function startMonitoring(): void {
  monitoringRefCount++;
  if (captureTimerId !== null) return; // Already running

  isCapturing = true;
  frameNumber = 0;
  lastDistributeTime = Date.now();
  resetContext();

  captureTimerId = setInterval(captureFrame, CAPTURE_INTERVAL_MS);
  console.info("[ProactiveAssistant] Monitoring started");
}

/**
 * Release a capture-loop slot. The loop actually stops only when the ref
 * count reaches 0, so turning off one assistant while another is active
 * keeps the capture pipeline running.
 */
export function stopMonitoring(): void {
  if (monitoringRefCount > 0) monitoringRefCount--;
  if (monitoringRefCount > 0) return;

  if (captureTimerId !== null) {
    clearInterval(captureTimerId);
    captureTimerId = null;
  }
  if (delayTimerId !== null) {
    clearTimeout(delayTimerId);
    delayTimerId = null;
  }

  isCapturing = false;
  isInDelayPeriod = false;
  latestFrame = null;
  resetContext();
  onDelayStateChange?.(null);

  console.info("[ProactiveAssistant] Monitoring stopped");
}

// ---------------------------------------------------------------------------
// Capture loop
// ---------------------------------------------------------------------------

async function captureFrame(): Promise<void> {
  if (!isCapturing) return;

  try {
    // 1. Capture screenshot + active window in parallel
    const [ocrResult, windowInfo] = await Promise.all([
      takeScreenshotWithOcr(CAPTURE_CONFIG),
      getActiveWindow(),
    ]);

    frameNumber++;

    const frame: CapturedFrame = {
      imageBase64: ocrResult.image,
      ocrText: ocrResult.ocr_text,
      appName: windowInfo.app_name,
      windowTitle: windowInfo.window_title,
      frameNumber,
      captureTime: new Date(),
      dbId: ocrResult.db_id,
    };

    // Always keep a reference to the latest frame
    latestFrame = frame;

    // 2. Check for context change
    const contextChanged = didContextChange(
      windowInfo.app_name,
      windowInfo.window_title,
    );

    if (contextChanged) {
      // Update tracked context
      updateContext(windowInfo.app_name, windowInfo.window_title);

      // Notify UI of context change
      onContextChange?.(windowInfo.app_name, windowInfo.window_title);

      if (frameNumber === 1) {
        // Match Swift: the first frame after monitoring starts is
        // distributed immediately with no debounce so the assistant can
        // anchor on whatever the user is doing right now.
        distributeFrame(frame);
      } else {
        // Subsequent context changes: debounce 3s to let rapid switches
        // (Cmd-Tab spam) settle before paying for an LLM call.
        startAnalysisDelay();
      }
    } else if (!isInDelayPeriod) {
      // No context change — check 60s fallback
      const elapsed = (Date.now() - lastDistributeTime) / 1000;
      if (elapsed >= FALLBACK_INTERVAL_S) {
        distributeFrame(frame);
      }
    }
  } catch (err) {
    // Screen capture can fail (permissions, lock screen, etc.)
    // Don't log on every tick — too noisy
  }
}

// ---------------------------------------------------------------------------
// Analysis delay
// ---------------------------------------------------------------------------

function startAnalysisDelay(): void {
  // Cancel any existing delay
  if (delayTimerId !== null) {
    clearTimeout(delayTimerId);
    delayTimerId = null;
  }

  isInDelayPeriod = true;
  const delayEndTime = new Date(Date.now() + ANALYSIS_DELAY_S * 1000);
  onDelayStateChange?.(delayEndTime);

  delayTimerId = setTimeout(() => {
    isInDelayPeriod = false;
    delayTimerId = null;
    onDelayStateChange?.(null);

    // Distribute the latest frame we captured during the delay
    if (latestFrame) {
      distributeFrame(latestFrame);
    }
  }, ANALYSIS_DELAY_S * 1000);
}

// ---------------------------------------------------------------------------
// Frame distribution
// ---------------------------------------------------------------------------

function distributeFrame(frame: CapturedFrame): void {
  lastDistributeTime = Date.now();
  for (const listener of frameListeners) {
    try {
      listener(frame);
    } catch (err) {
      console.warn("[ProactiveAssistant] frame listener threw:", err);
    }
  }
}
