/**
 * Research-intent tracker — flags windows the user has revisited multiple
 * times in a short window so the proactive task pipeline can extract
 * "decide on X" / "buy Y" tasks the prompt would otherwise pass over.
 *
 * Single-frame extraction misses these because nothing on a single product
 * page screenshot screams "this is a pending decision". Across N visits it
 * becomes obvious. We keep state in memory only — losing it on app restart
 * is fine; the user just needs to revisit the page a few more times.
 *
 * Heuristic:
 *  - Bucket by `windowTitle` (browsers' tab title is what the user sees and
 *    is what differs between, say, two product pages).
 *  - Track each captureTime in a rolling window.
 *  - When ≥ MIN_VISITS distinct visits land inside RECENT_WINDOW_MS, signal
 *    research intent for that bucket exactly once (until it cools off).
 *
 * The signal is emitted as a per-frame boolean and a free-text hint that
 * the prompt builder can splice into the LLM context.
 */
import type { CapturedFrame } from "@/services/proactiveAssistant";

// "Browser" here matches the same default whitelist in taskAssistantSettings —
// duplicating it would couple this file to the settings store; instead we just
// match heuristically off appName which is good enough for the signal.
const BROWSER_APPS = new Set([
  "Safari",
  "Google Chrome",
  "Arc",
  "Firefox",
  "Brave Browser",
  "Microsoft Edge",
]);

const RECENT_WINDOW_MS = 8 * 60 * 1000; // 8 minutes
const MIN_VISITS = 3;
const COOLDOWN_MS = 30 * 60 * 1000; // 30 minutes — once we flagged a title, don't re-fire for half an hour
const MIN_GAP_BETWEEN_VISITS_MS = 20 * 1000; // 20s — same frame captured twice doesn't count as a "visit"

interface BucketState {
  visits: number[]; // capture timestamps (ms)
  flaggedAt: number | null; // last time we surfaced the signal for this bucket
}

const buckets = new Map<string, BucketState>();

function pruneOld(state: BucketState, nowMs: number): void {
  const cutoff = nowMs - RECENT_WINDOW_MS;
  while (state.visits.length && state.visits[0] < cutoff) {
    state.visits.shift();
  }
}

function isMeaningfulTitle(title: string | undefined): boolean {
  if (!title) return false;
  const t = title.trim();
  // Skip empty / "New Tab" / browser homepage placeholders that would
  // otherwise pile up while the user is just opening tabs.
  if (t.length < 4) return false;
  const lower = t.toLowerCase();
  return !["new tab", "untitled", "home", "blank"].includes(lower);
}

export interface ResearchSignal {
  flagged: boolean;
  /** Free-text hint to splice into the LLM prompt when flagged is true. */
  hint?: string;
  /** Number of revisits in the rolling window (always populated, even when
   *  flagged is false — useful for telemetry). */
  visits: number;
}

/** Record a frame and report whether it just crossed the research-intent
 *  threshold. Idempotent for fast-arriving identical frames (the gap
 *  filter dedupes). */
export function recordFrame(frame: CapturedFrame): ResearchSignal {
  if (!BROWSER_APPS.has(frame.appName)) return { flagged: false, visits: 0 };
  const title = frame.windowTitle;
  if (!isMeaningfulTitle(title)) return { flagged: false, visits: 0 };

  const nowMs = frame.captureTime.getTime();
  const state = buckets.get(title) ?? { visits: [], flaggedAt: null };
  pruneOld(state, nowMs);

  const lastVisit = state.visits[state.visits.length - 1];
  if (lastVisit === undefined || nowMs - lastVisit >= MIN_GAP_BETWEEN_VISITS_MS) {
    state.visits.push(nowMs);
  }
  buckets.set(title, state);

  // Cooldown: don't re-fire for the same title until 30 min after the last flag.
  const recentlyFlagged =
    state.flaggedAt !== null && nowMs - state.flaggedAt < COOLDOWN_MS;
  const enoughVisits = state.visits.length >= MIN_VISITS;
  if (enoughVisits && !recentlyFlagged) {
    state.flaggedAt = nowMs;
    const minutesSpan = Math.max(
      1,
      Math.round((nowMs - state.visits[0]) / 60000),
    );
    return {
      flagged: true,
      visits: state.visits.length,
      hint:
        `RESEARCH SIGNAL: the user has revisited this exact view ` +
        `${state.visits.length} times in the last ${minutesSpan} minute(s). ` +
        `This is a strong cue that they are deciding on something — title the task as the decision ` +
        `(e.g., "Decide on <product>: <option A> vs <option B>" or "Buy <item>"), keep it conservative, ` +
        `and skip if the page is just a generic search results listing with no specific item.`,
    };
  }

  return { flagged: false, visits: state.visits.length };
}

/** Test-only / debug helper to clear in-memory state. */
export function _resetResearchIntent(): void {
  buckets.clear();
}
