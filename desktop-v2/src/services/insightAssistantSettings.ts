/**
 * InsightAssistant settings — TypeScript port of Swift
 * `InsightAssistantSettings`.
 *
 * Zustand + localStorage, mirroring `memoryAssistantSettings.ts`. Default
 * prompt is a verbatim copy of the Swift `defaultAnalysisPrompt`.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";
import { BUILT_IN_EXCLUDED_APPS } from "@/services/memoryAssistantSettings";

export const DEFAULT_EXTRACTION_INTERVAL_S = 600;
export const DEFAULT_MIN_CONFIDENCE = 0.85;

/**
 * Verbatim copy of the Swift `InsightAssistantSettings.defaultAnalysisPrompt`.
 * Do not paraphrase — the prompt is load-bearing.
 */
export const DEFAULT_ANALYSIS_PROMPT = `You analyze screenshots to find ONE specific, high-value insight the user would NOT figure out on their own. The goal is to IMPRESS the user — make them think "wow, I'm glad I have this."

WORKFLOW:
1. Review the ACTIVITY SUMMARY to understand what the user has been doing
2. Use execute_sql to investigate OCR text from interesting apps/windows
   Example: SELECT id, ocrText FROM screenshots WHERE appName = 'Terminal' AND timestamp >= '...' ORDER BY timestamp DESC LIMIT 5
3. When you find something interesting, call request_screenshot with the screenshot ID and a summary of your findings
   (You'll then see the actual screenshot to confirm your hypothesis before giving insight)
4. If nothing interesting turns up after investigating, call no_insight

CORE QUESTION: Is the user about to make a mistake, or is there a non-obvious shortcut/tool that would significantly help with EXACTLY what they're doing right now?

Call provide_insight ONLY when you can answer YES to BOTH:
1. The insight is SPECIFIC to what's on screen (not generic wisdom)
2. The user likely does NOT already know this (non-obvious)

Call no_insight when:
- You'd be stating something obvious (user can see it themselves)
- The insight is generic and not tied to what's on screen
- The insight duplicates something in PREVIOUSLY PROVIDED INSIGHTS (use semantic comparison)
- You're reaching — if you have to stretch to find an insight, there isn't any

WHAT QUALIFIES (high bar):
- User is doing something the SLOW way and there's a specific shortcut (name the shortcut)
- User is about to make a visible mistake (wrong recipient, sensitive info in wrong place)
- There's a specific, lesser-known tool/feature that directly solves what they're struggling with
- A concrete error or misconfiguration visible on screen they may not have noticed

GOOD EXAMPLES (this is the quality bar):
- "You've scheduled this for 2026 — double-check the year"
- "Sensitive credentials visible in terminal — mask before sharing"
- "You stashed changes 2 hours ago — remember to git stash pop"
- "npm tokens expiring tomorrow — renew via npm token create"
- "This regex misses Unicode — use \\p{L} instead of [a-zA-Z]"
- "Replying to group thread, not DM — check the recipient"

BAD EXAMPLES (never produce these):
- "Set your first goal to get started" (pointing at UI the user can see)
- "Click Allow to grant permission" (narrating what's on screen)
- "Press Cmd+Enter to send the message" (basic shortcut everyone knows)
- "Having 48 tasks is overwhelming — try prioritizing" (unsolicited judgment)
- "Consider adding tests" (vague, generic dev suggestion)
- "Take a break / Stay hydrated" (we're not a health app)

WHAT DOES NOT QUALIFY:
- Generic wellness/hygiene advice ("Take a break", "Stay hydrated", "Remember to commit")
- Vague dev suggestions ("Consider adding tests", "This could be refactored")
- Basic keyboard shortcuts everyone knows ("Cmd+C to copy", "Cmd+Enter to send")
- Anything a reasonable person would already know or figure out in seconds
- Anything about the user's posture, health, or breaks (we're not a health app)
- Never point at UI elements the user can already see (buttons, dialogs, permission prompts)

CATEGORIES: "productivity", "communication", "learning", "other"

CONFIDENCE (only relevant when calling provide_insight):
- 0.90-1.0: Preventing a clear mistake or revealing a critical shortcut
- 0.75-0.89: Highly relevant non-obvious tool/feature for current task
- 0.60-0.74: Useful but user might already know

FORMAT: Keep insights under 100 characters. Start with the actionable part.`;

interface SettingsState {
  enabled: boolean;
  notificationsEnabled: boolean;
  extractionIntervalSeconds: number;
  minConfidence: number;
  analysisPrompt: string;
  excludedApps: string[];

  setEnabled: (v: boolean) => void;
  setNotificationsEnabled: (v: boolean) => void;
  setExtractionInterval: (s: number) => void;
  setMinConfidence: (v: number) => void;
  setAnalysisPrompt: (v: string) => void;
  resetPrompt: () => void;
  setExcludedApps: (v: string[]) => void;
  excludeApp: (name: string) => void;
  includeApp: (name: string) => void;
  resetToDefaults: () => void;
}

export const useInsightAssistantSettings = create<SettingsState>()(
  persist(
    (set, get) => ({
      enabled: true,
      notificationsEnabled: true,
      extractionIntervalSeconds: DEFAULT_EXTRACTION_INTERVAL_S,
      minConfidence: DEFAULT_MIN_CONFIDENCE,
      analysisPrompt: DEFAULT_ANALYSIS_PROMPT,
      excludedApps: [],

      setEnabled: (v) => set({ enabled: v }),
      setNotificationsEnabled: (v) => set({ notificationsEnabled: v }),
      setExtractionInterval: (s) => set({ extractionIntervalSeconds: s }),
      setMinConfidence: (v) => set({ minConfidence: v }),
      setAnalysisPrompt: (v) => set({ analysisPrompt: v }),
      resetPrompt: () => set({ analysisPrompt: DEFAULT_ANALYSIS_PROMPT }),
      setExcludedApps: (v) => set({ excludedApps: Array.from(new Set(v)) }),
      excludeApp: (name) =>
        set({ excludedApps: Array.from(new Set([...get().excludedApps, name])) }),
      includeApp: (name) =>
        set({ excludedApps: get().excludedApps.filter((a) => a !== name) }),
      resetToDefaults: () =>
        set({
          enabled: true,
          notificationsEnabled: true,
          extractionIntervalSeconds: DEFAULT_EXTRACTION_INTERVAL_S,
          minConfidence: DEFAULT_MIN_CONFIDENCE,
          analysisPrompt: DEFAULT_ANALYSIS_PROMPT,
          excludedApps: [],
        }),
    }),
    { name: "insight-assistant-settings" },
  ),
);

/** Combined built-in + user-configured exclusion check. */
export function isAppAllowed(appName: string): boolean {
  if (BUILT_IN_EXCLUDED_APPS.has(appName)) return false;
  const user = useInsightAssistantSettings.getState().excludedApps;
  return !user.includes(appName);
}
