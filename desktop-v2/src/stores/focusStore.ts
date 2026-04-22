/**
 * Focus store — Zustand store that wires together the proactive assistant
 * coordinator and the focus assistant, exposing all state to the UI.
 *
 * Ported from Swift: FocusStorage.swift + FocusViewModel
 *
 * Architecture:
 * - proactiveAssistant.ts captures frames and detects context changes
 * - focusAssistant.ts analyzes frames via Gemini with smart filtering
 * - This store manages UI state, session history, stats, and persistence
 */

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { LazyStore } from "@tauri-apps/plugin-store";
import type { FocusStatus, ScreenAnalysis, FocusSession } from "@/services/focusAssistant";
import { focusAssistant } from "@/services/focusAssistant";
import {
  startMonitoring,
  stopMonitoring,
  addFrameListener,
  setContextChangeHandler,
  setDelayStateHandler,
} from "@/services/proactiveAssistant";
import { sendDistractionAlert, sendFocusNotification } from "@/services/notifications";

// Re-export types for consumers.
export type { FocusStatus, ScreenAnalysis, FocusSession };

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Maximum number of sessions to retain in state. */
const MAX_SESSIONS = 200;

/** Default cooldown duration in seconds (10 minutes). */
const DEFAULT_COOLDOWN_S = 600;

/**
 * Frame-listener unsubscribe held outside the Zustand state (functions are
 * not JSON-serializable and would break persistence).
 */
let frameUnsubscribe: (() => void) | null = null;

// ---------------------------------------------------------------------------
// Tauri persistence (same pattern as chatStore)
// ---------------------------------------------------------------------------

const tauriStore = new LazyStore("focus-history.json");

const tauriStorage = createJSONStorage(() => ({
  getItem: async (name: string) => {
    const val = await tauriStore.get<string>(name);
    return val ?? null;
  },
  setItem: async (name: string, value: string) => {
    await tauriStore.set(name, value);
    await tauriStore.save();
  },
  removeItem: async (name: string) => {
    await tauriStore.delete(name);
    await tauriStore.save();
  },
}));

// ---------------------------------------------------------------------------
// State shape
// ---------------------------------------------------------------------------

interface FocusState {
  /** Whether focus monitoring is enabled. */
  focusEnabled: boolean;
  /** Most recent focus status. */
  currentStatus: FocusStatus | null;
  /** Full result of the most recent analysis. */
  lastAnalysis: ScreenAnalysis | null;
  /** Currently detected app (before analysis completes). */
  detectedAppName: string | null;
  /** When the analysis delay ends (null if not in delay). */
  delayEndTime: Date | null;
  /** When the cooldown ends (null if not in cooldown). */
  cooldownEndTime: Date | null;
  /** True while an analysis is in flight. */
  isAnalyzing: boolean;
  /** Whether distraction notifications are enabled. */
  notificationsEnabled: boolean;
  /** Cooldown duration in seconds. */
  cooldownDurationS: number;
  /** Session history (newest first). */
  sessions: FocusSession[];
  /** Timestamp (ms) of when focus monitoring started. null when stopped. */
  monitoringStartedAt: number | null;

  // Actions
  toggleFocus: () => void;
  startFocusMonitoring: () => void;
  stopFocusMonitoring: () => void;
  toggleNotifications: () => void;
  setCooldownDuration: (seconds: number) => void;
  deleteSession: (id: string) => void;
  clearSessions: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let nextSessionId = 1;

function generateSessionId(): string {
  return `fs_${Date.now()}_${nextSessionId++}`;
}

/** Compute durations for sessions (newest-first array). */
function computeDurations(sessions: FocusSession[]): FocusSession[] {
  const now = new Date();
  return sessions.map((session, i) => {
    let endTime: Date;
    if (i === 0) {
      // Most recent — extends to now
      endTime = now;
    } else {
      // Ended when the next (more recent) session started
      endTime = sessions[i - 1].created_at;
    }
    const duration = Math.max(
      0,
      Math.floor((endTime.getTime() - session.created_at.getTime()) / 1000),
    );
    return { ...session, duration_seconds: duration };
  });
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useFocusStore = create<FocusState>()(
  persist(
    (set, get) => ({
      focusEnabled: false,
      currentStatus: null,
      lastAnalysis: null,
      detectedAppName: null,
      delayEndTime: null,
      cooldownEndTime: null,
      isAnalyzing: false,
      notificationsEnabled: true,
      cooldownDurationS: DEFAULT_COOLDOWN_S,
      sessions: [],
      monitoringStartedAt: null,

      // -----------------------------------------------------------------------
      // toggleFocus
      // -----------------------------------------------------------------------
      toggleFocus: () => {
        if (get().focusEnabled) {
          get().stopFocusMonitoring();
        } else {
          get().startFocusMonitoring();
        }
      },

      // -----------------------------------------------------------------------
      // startFocusMonitoring
      // -----------------------------------------------------------------------
      startFocusMonitoring: () => {
        if (frameUnsubscribe) return;

        // Configure the focus assistant
        focusAssistant.setCooldownDuration(get().cooldownDurationS);
        focusAssistant.setNotificationsEnabled(get().notificationsEnabled);
        focusAssistant.setCallbacks({
          onStatusChange: (analysis, previousStatus) => {
            const state = get();

            // Create session entry
            const session: FocusSession = {
              id: generateSessionId(),
              status: analysis.status,
              app_or_site: analysis.app_or_site,
              description: analysis.description,
              message: analysis.message,
              created_at: analysis.timestamp,
              duration_seconds: null,
            };

            // Notification logic
            if (state.notificationsEnabled) {
              if (analysis.status === "distracted") {
                sendDistractionAlert(
                  analysis.app_or_site ?? "unknown",
                  analysis.message ?? "Time to refocus!",
                );
              } else if (
                analysis.status === "focused" &&
                previousStatus === "distracted"
              ) {
                sendFocusNotification(
                  "Focus",
                  analysis.message ?? "Great, you're back on track!",
                );
              }
            }

            // Update store
            set((s) => {
              const updatedSessions = [session, ...s.sessions].slice(
                0,
                MAX_SESSIONS,
              );
              return {
                currentStatus: analysis.status,
                lastAnalysis: analysis,
                isAnalyzing: false,
                sessions: updatedSessions,
              };
            });
          },

          onCooldownStart: (endTime) => {
            set({ cooldownEndTime: endTime });
          },

          onCooldownEnd: () => {
            set({ cooldownEndTime: null });
          },

          onError: (_err) => {
            set({ isAnalyzing: false });
          },
        });

        // Wire up proactive assistant handlers
        frameUnsubscribe = addFrameListener((frame) => {
          set({ isAnalyzing: true });
          focusAssistant.analyze(frame);
        });

        setContextChangeHandler((appName, _windowTitle) => {
          set({ detectedAppName: appName });
          focusAssistant.onContextSwitch();
        });

        setDelayStateHandler((delayEndTime) => {
          set({ delayEndTime });
        });

        // Start the capture loop
        set({
          focusEnabled: true,
          currentStatus: null,
          lastAnalysis: null,
          monitoringStartedAt: Date.now(),
        });
        startMonitoring();

        console.info("[FocusStore] Monitoring started");
      },

      // -----------------------------------------------------------------------
      // stopFocusMonitoring
      // -----------------------------------------------------------------------
      stopFocusMonitoring: () => {
        if (frameUnsubscribe) {
          frameUnsubscribe();
          frameUnsubscribe = null;
          stopMonitoring();
        }
        focusAssistant.reset();

        set({
          focusEnabled: false,
          isAnalyzing: false,
          delayEndTime: null,
          cooldownEndTime: null,
          detectedAppName: null,
          monitoringStartedAt: null,
        });

        console.info("[FocusStore] Monitoring stopped");
      },

      // -----------------------------------------------------------------------
      // toggleNotifications
      // -----------------------------------------------------------------------
      toggleNotifications: () => {
        const next = !get().notificationsEnabled;
        focusAssistant.setNotificationsEnabled(next);
        set({ notificationsEnabled: next });
      },

      // -----------------------------------------------------------------------
      // setCooldownDuration
      // -----------------------------------------------------------------------
      setCooldownDuration: (seconds: number) => {
        focusAssistant.setCooldownDuration(seconds);
        set({ cooldownDurationS: seconds });
      },

      // -----------------------------------------------------------------------
      // deleteSession
      // -----------------------------------------------------------------------
      deleteSession: (id: string) => {
        set((s) => ({
          sessions: s.sessions.filter((session) => session.id !== id),
        }));
      },

      // -----------------------------------------------------------------------
      // clearSessions
      // -----------------------------------------------------------------------
      clearSessions: () => {
        set({ sessions: [] });
      },
    }),
    {
      name: "focus-state",
      storage: tauriStorage,
      partialize: (state) => ({
        focusEnabled: state.focusEnabled,
        notificationsEnabled: state.notificationsEnabled,
        cooldownDurationS: state.cooldownDurationS,
        sessions: state.sessions.slice(0, MAX_SESSIONS),
      }),
      // Rehydrate dates from JSON
      merge: (persisted: unknown, current: FocusState) => {
        const p = persisted as Partial<FocusState> | undefined;
        if (!p) return current;
        return {
          ...current,
          focusEnabled: false, // Always start stopped — user re-enables
          notificationsEnabled: p.notificationsEnabled ?? current.notificationsEnabled,
          cooldownDurationS: p.cooldownDurationS ?? current.cooldownDurationS,
          sessions: (p.sessions ?? []).map((s) => ({
            ...s,
            created_at: new Date(s.created_at),
          })),
        };
      },
    },
  ),
);

// ---------------------------------------------------------------------------
// Computed selectors (used by FocusPage)
// ---------------------------------------------------------------------------

/** Get today's sessions with computed durations. */
export function useTodaySessions(): FocusSession[] {
  const sessions = useFocusStore((s) => s.sessions);
  const todayStart = new Date();
  todayStart.setHours(0, 0, 0, 0);

  const todaySessions = sessions.filter(
    (s) => new Date(s.created_at) >= todayStart,
  );
  return computeDurations(todaySessions);
}

/** Get all sessions with computed durations. */
export function useAllSessions(): FocusSession[] {
  const sessions = useFocusStore((s) => s.sessions);
  return computeDurations(sessions);
}

/** Compute today's focus stats. */
export function useFocusStats(): {
  focusMinutes: number;
  distractedMinutes: number;
  focusRate: number;
  sessionCount: number;
  topDistractions: { app: string; count: number; totalSeconds: number }[];
} {
  const sessions = useTodaySessions();

  let focusSeconds = 0;
  let distractedSeconds = 0;
  const distractionMap = new Map<
    string,
    { count: number; totalSeconds: number }
  >();

  for (const session of sessions) {
    const duration = session.duration_seconds ?? 0;
    if (session.status === "focused") {
      focusSeconds += duration;
    } else {
      distractedSeconds += duration;
      const existing = distractionMap.get(session.app_or_site) ?? {
        count: 0,
        totalSeconds: 0,
      };
      existing.count++;
      existing.totalSeconds += duration;
      distractionMap.set(session.app_or_site, existing);
    }
  }

  const totalSeconds = focusSeconds + distractedSeconds;
  const focusRate = totalSeconds > 0 ? (focusSeconds / totalSeconds) * 100 : 0;

  const topDistractions = Array.from(distractionMap.entries())
    .map(([app, data]) => ({ app, ...data }))
    .sort((a, b) => b.totalSeconds - a.totalSeconds)
    .slice(0, 5);

  return {
    focusMinutes: Math.round(focusSeconds / 60),
    distractedMinutes: Math.round(distractedSeconds / 60),
    focusRate: Math.round(focusRate),
    sessionCount: sessions.length,
    topDistractions,
  };
}
