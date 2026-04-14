/**
 * Focus Assistant service — analyzes screenshots via Gemini Vision to detect
 * whether the user is focused or distracted.
 *
 * Ported from Swift: FocusAssistant.swift
 *
 * Key behaviors matching Swift:
 * - Smart analysis filtering (shouldSkipAnalysis)
 * - Exponential error backoff (5s → 10s → ... → 300s max)
 * - Cooldown after distraction detection (configurable, default 10 min)
 * - Cooldown cleared on context change (user switched apps)
 * - Max 3 concurrent analyses (backpressure)
 * - State change deduplication via lastNotifiedState
 * - Context enrichment caching (2 min TTL)
 */

import { invoke } from "@tauri-apps/api/core";
import type { CapturedFrame } from "@/services/proactiveAssistant";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type FocusStatus = "focused" | "distracted";

export interface ScreenAnalysis {
  status: FocusStatus;
  app_or_site: string;
  description: string;
  message?: string;
  /** Timestamp of when analysis completed. */
  timestamp: Date;
  /** Frame number that produced this analysis. */
  frameNumber: number;
}

export interface FocusSession {
  id: string;
  status: FocusStatus;
  app_or_site: string;
  description: string;
  message?: string;
  created_at: Date;
  /** Computed duration in seconds (time until next session or now). */
  duration_seconds: number | null;
}

/** Callback for state changes that the store should react to. */
export interface FocusAssistantCallbacks {
  onStatusChange: (analysis: ScreenAnalysis, previousStatus: FocusStatus | null) => void;
  onCooldownStart: (endTime: Date) => void;
  onCooldownEnd: () => void;
  onError: (error: unknown) => void;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta";

/** Max analysis history entries to send to Gemini for context. */
const MAX_HISTORY_ENTRIES = 5;

/** Max concurrent analysis tasks (backpressure). */
const MAX_PENDING_TASKS = 3;

/** Error backoff base delay in seconds. */
const ERROR_BACKOFF_BASE_S = 5;

/** Maximum error backoff in seconds (5 minutes). */
const ERROR_BACKOFF_MAX_S = 300;

/** Context enrichment cache TTL in milliseconds (2 minutes). */
const CONTEXT_CACHE_TTL_MS = 120_000;

/** Default cooldown duration in seconds (10 minutes). */
const DEFAULT_COOLDOWN_S = 600;

/** Apps that should never be analyzed (lock screen, login window). */
const EXCLUDED_SYSTEM_APPS = new Set([
  "loginwindow",
  "ScreenSaverEngine",
  "LockScreen",
]);

// (Default analysis removed — errors now throw and are caught by processFrame's backoff logic.)

// ---------------------------------------------------------------------------
// API key cache
// ---------------------------------------------------------------------------

let cachedApiKey: string | null = null;

async function getGeminiApiKey(): Promise<string> {
  if (cachedApiKey) return cachedApiKey;
  const key = await invoke<string | null>("get_gemini_api_key");
  if (!key) {
    throw new Error("GEMINI_API_KEY not configured");
  }
  cachedApiKey = key;
  return key;
}

// ---------------------------------------------------------------------------
// System prompt (matching Swift app)
// ---------------------------------------------------------------------------

const FOCUS_SYSTEM_PROMPT = `You are a focus coach. Analyze the PRIMARY/MAIN window in screenshots to determine if the user is focused or distracted.

IMPORTANT: Look at the MAIN APPLICATION WINDOW, not log text or terminal output. If you see a code editor with logs that mention "YouTube" - that's just log text, the user is CODING, not on YouTube. Text in logs/terminals mentioning a site does NOT mean the user is on that site.

CONTEXT-AWARE ANALYSIS:
Each request may include the user's active goals, current tasks, recent memories, time of day, and analysis history. Use this context when available, but DO NOT let it prevent you from flagging obvious distractions.

- GOALS & TASKS: If the user's screen activity clearly relates to their active goals or current tasks, they are FOCUSED.
- HISTORY: Use recent analysis history to notice patterns, acknowledge transitions, and vary your responses.

Set status to "distracted" if the PRIMARY window is:
- YouTube, Twitch, Netflix, TikTok (actual video site visible, not just text mentioning it)
- Social media feeds: Twitter/X, Instagram, Facebook, Reddit (casual browsing, not researching a specific work topic)
- News sites, entertainment sites, games
- Any content consumption with no clear work purpose

Set status to "focused" if the PRIMARY window is:
- Code editors, IDEs, terminals, command line
- Documents, spreadsheets, slides, design tools
- Email, work chat (Slack, Teams), research
- Browsing that is clearly work-related (Stack Overflow, docs, PRs, Jira, etc.)

When in doubt, lean toward "distracted" — it's better to nudge the user once too often than to silently let them drift.

Always provide a short coaching message (100 characters max for notification banner):
- If distracted: Create a unique nudge to refocus. Vary your approach — be playful, direct, or motivational.
- If focused: Acknowledge their work with variety — don't just say "Nice focus!" every time.`;

// ---------------------------------------------------------------------------
// FocusAssistant — stateful analysis engine
// ---------------------------------------------------------------------------

export class FocusAssistant {
  // --- Analysis state ---
  private lastStatus: FocusStatus | null = null;
  private lastNotifiedState: FocusStatus | null = null;
  private lastAnalyzedApp = "";
  private lastAnalyzedWindowTitle = "";
  private lastProcessedFrameNum = 0;
  private analysisHistory: ScreenAnalysis[] = [];

  // --- Error backoff ---
  private consecutiveErrorCount = 0;
  private errorBackoffEndTime: Date | null = null;

  // --- Cooldown ---
  private cooldownEndTime: Date | null = null;
  private cooldownDurationS = DEFAULT_COOLDOWN_S;

  // --- Backpressure ---
  private pendingCount = 0;

  // --- Context enrichment cache ---
  private contextCache: string | null = null;
  private contextCacheTime = 0;

  // --- Callbacks ---
  private callbacks: FocusAssistantCallbacks | null = null;

  // --- Settings ---
  private excludedApps = new Set<string>();

  // -------------------------------------------------------------------------
  // Configuration
  // -------------------------------------------------------------------------

  setCallbacks(callbacks: FocusAssistantCallbacks): void {
    this.callbacks = callbacks;
  }

  setCooldownDuration(seconds: number): void {
    this.cooldownDurationS = seconds;
  }

  setExcludedApps(apps: Set<string>): void {
    this.excludedApps = apps;
  }

  setNotificationsEnabled(_enabled: boolean): void {
    // Notifications are handled by the store's callbacks, not the assistant itself.
    // This method exists so the store can mirror the setting here if needed in the future.
  }

  // -------------------------------------------------------------------------
  // Public API
  // -------------------------------------------------------------------------

  /**
   * Submit a captured frame for analysis. This is the main entry point
   * called by the proactive assistant coordinator.
   */
  async analyze(frame: CapturedFrame): Promise<void> {
    // Reject system/excluded apps
    if (EXCLUDED_SYSTEM_APPS.has(frame.appName)) return;
    if (this.excludedApps.has(frame.appName)) return;

    // Smart filtering
    if (this.shouldSkipAnalysis(frame.appName, frame.windowTitle)) {
      return;
    }

    // Backpressure: drop frame if too many pending
    if (this.pendingCount >= MAX_PENDING_TASKS) {
      return;
    }

    // Update last analyzed context IMMEDIATELY (prevents duplicate queuing)
    this.lastAnalyzedApp = frame.appName;
    this.lastAnalyzedWindowTitle = frame.windowTitle;

    // Process in background
    this.pendingCount++;
    this.processFrame(frame).finally(() => {
      this.pendingCount--;
    });
  }

  /**
   * Called by the coordinator when a context switch is detected.
   * Clears cooldown so the new context gets analyzed immediately.
   */
  onContextSwitch(): void {
    if (this.cooldownEndTime) {
      this.cooldownEndTime = null;
      this.callbacks?.onCooldownEnd();
    }
  }

  /**
   * Reset all state (called when monitoring stops).
   */
  reset(): void {
    this.lastStatus = null;
    this.lastNotifiedState = null;
    this.lastAnalyzedApp = "";
    this.lastAnalyzedWindowTitle = "";
    this.lastProcessedFrameNum = 0;
    this.analysisHistory = [];
    this.consecutiveErrorCount = 0;
    this.errorBackoffEndTime = null;
    this.cooldownEndTime = null;
    this.pendingCount = 0;
    this.contextCache = null;
    this.contextCacheTime = 0;
  }

  getLastStatus(): FocusStatus | null {
    return this.lastStatus;
  }

  getAnalysisHistory(): ScreenAnalysis[] {
    return [...this.analysisHistory];
  }

  getCooldownEndTime(): Date | null {
    return this.cooldownEndTime;
  }

  isInCooldown(): boolean {
    if (!this.cooldownEndTime) return false;
    return new Date() < this.cooldownEndTime;
  }

  // -------------------------------------------------------------------------
  // Smart analysis filtering (matching Swift shouldSkipAnalysis)
  // -------------------------------------------------------------------------

  private shouldSkipAnalysis(appName: string, windowTitle: string): boolean {
    // 1. Error backoff check
    if (this.errorBackoffEndTime && new Date() < this.errorBackoffEndTime) {
      return true;
    }

    // 2. No status yet — always analyze
    if (this.lastStatus === null) {
      return false;
    }

    // 3. Context changed — clear cooldown, always analyze
    const contextChanged =
      appName !== this.lastAnalyzedApp ||
      windowTitle !== this.lastAnalyzedWindowTitle;

    if (contextChanged) {
      // Clear cooldown on context switch
      if (this.cooldownEndTime) {
        this.cooldownEndTime = null;
        this.callbacks?.onCooldownEnd();
      }
      return false;
    }

    // 4. In cooldown period — skip
    if (this.cooldownEndTime && new Date() < this.cooldownEndTime) {
      return true;
    }

    // 5. Same context + focused state — skip (no need to re-analyze)
    if (this.lastStatus === "focused") {
      return true;
    }

    // 6. Distracted or unknown — analyze
    return false;
  }

  // -------------------------------------------------------------------------
  // Frame processing
  // -------------------------------------------------------------------------

  private async processFrame(frame: CapturedFrame): Promise<void> {
    try {
      const analysis = await this.analyzeScreenshot(frame);

      // Reset error state on success
      this.consecutiveErrorCount = 0;
      this.errorBackoffEndTime = null;

      // Skip stale frames
      if (frame.frameNumber <= this.lastProcessedFrameNum) {
        return;
      }
      this.lastProcessedFrameNum = frame.frameNumber;

      // Add to history (max 10)
      this.analysisHistory.push(analysis);
      if (this.analysisHistory.length > 10) {
        this.analysisHistory.shift();
      }

      // State change detection
      const previousStatus = this.lastNotifiedState;
      this.lastStatus = analysis.status;

      if (analysis.status !== this.lastNotifiedState) {
        // Update lastNotifiedState BEFORE other actions (prevents race)
        this.lastNotifiedState = analysis.status;

        if (analysis.status === "distracted") {
          // Start cooldown
          const cooldownEnd = new Date(
            Date.now() + this.cooldownDurationS * 1000,
          );
          this.cooldownEndTime = cooldownEnd;
          this.callbacks?.onCooldownStart(cooldownEnd);
        }

        // Notify store of state change
        this.callbacks?.onStatusChange(analysis, previousStatus);
      }
    } catch (err) {
      // Exponential backoff
      this.consecutiveErrorCount++;
      const backoffS = Math.min(
        ERROR_BACKOFF_BASE_S *
          Math.pow(2, this.consecutiveErrorCount - 1),
        ERROR_BACKOFF_MAX_S,
      );
      this.errorBackoffEndTime = new Date(Date.now() + backoffS * 1000);

      console.error(
        `[FocusAssistant] Analysis failed (attempt ${this.consecutiveErrorCount}, backoff ${backoffS}s):`,
        err,
      );
      this.callbacks?.onError(err);
    }
  }

  // -------------------------------------------------------------------------
  // Gemini API call
  // -------------------------------------------------------------------------

  private async analyzeScreenshot(
    frame: CapturedFrame,
  ): Promise<ScreenAnalysis> {
    const prompt = this.buildPrompt(
      frame.appName,
      frame.windowTitle,
    );

    const apiKey = await getGeminiApiKey();
    const url = `${GEMINI_BASE}/models/gemini-2.5-flash:generateContent?key=${apiKey}`;

    const body = {
      contents: [
        {
          parts: [
            { text: prompt },
            {
              inline_data: {
                mime_type: "image/jpeg",
                data: frame.imageBase64,
              },
            },
          ],
        },
      ],
      generationConfig: {
        response_mime_type: "application/json",
        response_schema: {
          type: "object",
          properties: {
            status: {
              type: "string",
              enum: ["focused", "distracted"],
            },
            app_or_site: { type: "string" },
            description: { type: "string" },
            message: { type: "string" },
          },
          required: ["status", "app_or_site", "description"],
        },
      },
    };

    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const text = await response.text().catch(() => "(no body)");
      throw new Error(`Gemini returned ${response.status}: ${text}`);
    }

    const json = await response.json();
    const rawText: string | undefined =
      json?.candidates?.[0]?.content?.parts?.[0]?.text;

    if (!rawText) {
      throw new Error("Unexpected Gemini response shape");
    }

    const parsed = JSON.parse(rawText);

    if (!parsed.status || !parsed.app_or_site || !parsed.description) {
      throw new Error("Parsed response missing required fields");
    }

    if (parsed.status !== "focused" && parsed.status !== "distracted") {
      parsed.status = "focused";
    }

    return {
      status: parsed.status,
      app_or_site: parsed.app_or_site,
      description: parsed.description,
      message: parsed.message,
      timestamp: new Date(),
      frameNumber: frame.frameNumber,
    };
  }

  // -------------------------------------------------------------------------
  // Prompt building
  // -------------------------------------------------------------------------

  private buildPrompt(appName: string, windowTitle: string): string {
    const now = new Date();
    const timeStr = now.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
    const dateStr = now.toLocaleDateString([], {
      weekday: "long",
      month: "long",
      day: "numeric",
    });

    const lines: string[] = [
      FOCUS_SYSTEM_PROMPT,
      "",
      "--- CONTEXT ---",
      `Current time: ${timeStr} on ${dateStr}`,
      `Active app: ${appName || "unknown"}`,
      `Window title: ${windowTitle || "unknown"}`,
    ];

    // Context enrichment (cached)
    const enrichment = this.getContextEnrichment();
    if (enrichment) {
      lines.push("", enrichment);
    }

    if (this.analysisHistory.length > 0) {
      const recent = this.analysisHistory.slice(-MAX_HISTORY_ENTRIES);
      lines.push("", "Recent analysis history (oldest -> newest):");
      recent.forEach((entry, i) => {
        lines.push(
          `  ${i + 1}. [${entry.status}] ${entry.app_or_site} — ${entry.description}`,
        );
      });
    }

    lines.push("", "Analyze the screenshot and respond with JSON.");
    return lines.join("\n");
  }

  // -------------------------------------------------------------------------
  // Context enrichment cache (2 min TTL)
  // -------------------------------------------------------------------------

  private getContextEnrichment(): string | null {
    const now = Date.now();
    if (this.contextCache && now - this.contextCacheTime < CONTEXT_CACHE_TTL_MS) {
      return this.contextCache;
    }
    // In the future, this could fetch goals/tasks/memories from backend.
    // For now, return null (no enrichment beyond history).
    this.contextCache = null;
    this.contextCacheTime = now;
    return null;
  }
}

// ---------------------------------------------------------------------------
// Singleton instance
// ---------------------------------------------------------------------------

export const focusAssistant = new FocusAssistant();
