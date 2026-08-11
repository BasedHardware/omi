/**
 * Immutable lifecycle vocabulary used by the agent-verifiable polish matrix.
 *
 * These are QA-only selectors. They map onto truthful domain fixture states;
 * they never enter a live route and never claim to be account data.
 */
export const POLISH_EVIDENCE_STATES = {
  memories: ["loading", "empty", "ready", "error", "offline", "busy"],
  tasks: ["loading", "empty", "ready", "error", "offline", "busy", "complete"],
  conversations: ["loading", "empty", "ready", "error", "offline", "busy"],
  folders: ["loading", "empty", "ready", "error", "offline"],
  chat: ["loading", "empty", "ready", "error", "offline", "busy", "complete", "cancelled"],
  listen: ["loading", "empty", "ready", "error", "offline", "busy", "complete"],
  settings: ["loading", "empty", "ready", "error", "offline"],
} as const;

export type PolishEvidenceDomain = keyof typeof POLISH_EVIDENCE_STATES;
export type PolishEvidenceState = (typeof POLISH_EVIDENCE_STATES)[PolishEvidenceDomain][number];

export type PolishFixtureSelection = {
  readonly domain: PolishEvidenceDomain;
  readonly state: PolishEvidenceState;
  readonly fixture: string;
};

/** Function export keeps the fixture matrix observable to the render harness. */
export function polishEvidenceStates(): typeof POLISH_EVIDENCE_STATES {
  return POLISH_EVIDENCE_STATES;
}

const FIXTURE_BY_STATE: Readonly<Record<PolishEvidenceDomain, Readonly<Record<string, string>>>> = {
  memories: {
    loading: "loading", empty: "empty", ready: "normal", error: "unavailable",
    offline: "degraded", busy: "paged",
  },
  tasks: {
    loading: "loading", empty: "empty", ready: "normal", error: "unavailable",
    offline: "saved-failed", busy: "sending", complete: "complete",
  },
  conversations: {
    loading: "loading", empty: "empty", ready: "normal", error: "unavailable",
    offline: "saved-failed", busy: "sending",
  },
  folders: {
    loading: "loading", empty: "empty", ready: "ready", error: "error", offline: "offline",
  },
  chat: {
    loading: "loading", empty: "empty", ready: "ready", error: "unavailable",
    offline: "saved-failed", busy: "streaming", complete: "normal", cancelled: "cancelled",
  },
  listen: {
    loading: "loading", empty: "empty", ready: "ready", error: "error",
    offline: "offline", busy: "busy", complete: "complete",
  },
  settings: {
    loading: "loading", empty: "signed-out", ready: "signed-in", error: "unavailable",
    offline: "saving-failed",
  },
};

export function resolvePolishFixture(domain: string | null, state: string | null): PolishFixtureSelection | null {
  if (domain === null || state === null) return null;
  const normalizedDomain = domain === "memories-platform" ? "memories" : domain;
  if (!Object.hasOwn(POLISH_EVIDENCE_STATES, normalizedDomain)) return null;
  const typedDomain = normalizedDomain as PolishEvidenceDomain;
  const states = POLISH_EVIDENCE_STATES[typedDomain] as readonly string[];
  if (!states.includes(state)) return null;
  const fixture = FIXTURE_BY_STATE[typedDomain][state];
  return fixture === undefined
    ? null
    : { domain: typedDomain, state: state as PolishEvidenceState, fixture };
}
