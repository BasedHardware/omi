// Source of truth: desktop/macos/Desktop/Sources/Onboarding/Scenario/ (the six
// onboarding "beats") and desktop/macos/Desktop/Sources/ProactiveAssistants/FirstRun/
// (the first-run walkthrough that plays right after onboarding completes).
//
// Both flows report progress as ONE event per flow, carrying the step in a
// PROPERTY rather than in the event name (unlike the retired flow below):
//   - `Onboarding Beat Completed` { beat: 'hello'|'see'|'card'|'talk'|'write'|'ready',
//     index, elapsed_ms, skipped, permission?, granted?, detection? }
//   - `Onboarding Completed` (terminal; no `beat` property)
//   - `First Run Step Completed` { step: 'openWork'|'setReminder'|'drift'|'backToWork'|'summary',
//     elapsed_ms, path: 'observed'|'fallback'|'dismissed' }
//   - `First Run Completed` { steps_completed, total_ms } (terminal; no `step` property)
//
// A beat/step counts as "reached" regardless of whether `skipped`/`path` marks
// it skipped, fallback, or dismissed — same semantics as the old `_Skipped`
// event-name variants below, just carried in a property instead of the event
// name.
//
// IF YOU RENAME, ADD, OR REMOVE A BEAT OR STEP IN THOSE SOURCES, MIRROR IT HERE.
//
// The PREVIOUS flow (one `Onboarding Step <Name> Completed` event per step, 18
// steps, e.g. `Onboarding Step ScreenRecording_Skipped Completed`) is dead —
// the live app no longer emits it. Those events keep existing in PostHog
// history from old builds, but this funnel does not attempt to map them onto
// the beats/steps above; they belong to a "legacy" flow and are excluded
// (the event-name filters built from this file never include them).

export type OnboardingStepDefinition = {
  key: string;
  label: string;
  /** The PostHog event name this step is reported under. */
  event: string;
  /**
   * The value of the row's property column that identifies this step.
   * `undefined` for a terminal step matched by event name alone (the
   * completion events carry no beat/step property).
   */
  property?: string;
};

const ONBOARDING_BEAT_EVENT = 'Onboarding Beat Completed';
const ONBOARDING_COMPLETED_EVENT = 'Onboarding Completed';
const FIRST_RUN_STEP_EVENT = 'First Run Step Completed';
const FIRST_RUN_COMPLETED_EVENT = 'First Run Completed';

function beat(key: string, label: string): OnboardingStepDefinition {
  return { key, label, event: ONBOARDING_BEAT_EVENT, property: key };
}

function firstRunStep(key: string, label: string): OnboardingStepDefinition {
  return { key, label, event: FIRST_RUN_STEP_EVENT, property: key };
}

export const STEP_DEFINITIONS: OnboardingStepDefinition[] = [
  beat('hello', 'Hello'),
  beat('see', 'See'),
  beat('card', 'Card'),
  beat('talk', 'Talk'),
  beat('write', 'Write'),
  beat('ready', 'Ready'),
  // Onboarding Completed — not a numbered beat.
  { key: 'completed', label: 'Completed', event: ONBOARDING_COMPLETED_EVENT },
];

export const FIRST_RUN_STEP_DEFINITIONS: OnboardingStepDefinition[] = [
  firstRunStep('openWork', 'Open Work'),
  firstRunStep('setReminder', 'Set Reminder'),
  firstRunStep('drift', 'Drift'),
  firstRunStep('backToWork', 'Back To Work'),
  firstRunStep('summary', 'Summary'),
  // First Run Completed — not a numbered step.
  { key: 'completed', label: 'Completed', event: FIRST_RUN_COMPLETED_EVENT },
];

/** The entry event + property that defines a first-ever entrant into the onboarding flow. */
export const ENTRY_EVENT_NAME = ONBOARDING_BEAT_EVENT;
export const ENTRY_PROPERTY_NAME = 'beat';
export const ENTRY_PROPERTY_VALUE = 'hello';

/** The entry event + property that defines a first-ever entrant into the first-run flow. */
export const FIRST_RUN_ENTRY_EVENT_NAME = FIRST_RUN_STEP_EVENT;
export const FIRST_RUN_ENTRY_PROPERTY_NAME = 'step';
export const FIRST_RUN_ENTRY_PROPERTY_VALUE = 'openWork';

export const ONBOARDING_EVENT_NAMES: string[] = Array.from(
  new Set(STEP_DEFINITIONS.map((s) => s.event)),
);
export const FIRST_RUN_EVENT_NAMES: string[] = Array.from(
  new Set(FIRST_RUN_STEP_DEFINITIONS.map((s) => s.event)),
);

export type OnboardingFunnelStep = {
  key: string;
  label: string;
  users: number;
  completionRate: number;
};

function stepIndexFor(
  stepDefinitions: OnboardingStepDefinition[],
  event: string,
  property: string | null | undefined,
): number | undefined {
  for (let i = 0; i < stepDefinitions.length; i++) {
    const def = stepDefinitions[i];
    if (def.event !== event) continue;
    // Terminal steps (no `property`) match on event name alone.
    if (def.property == null || def.property === property) return i;
  }
  return undefined;
}

/**
 * Collapse `[actor_id, event, property]` rows into an ordered funnel. A user
 * counts for a step only if they reached every step up to and including it —
 * `property` is matched against each step definition to find its index,
 * regardless of any `skipped`/`path` value on the underlying event.
 */
function computeFunnel(
  rows: unknown[][],
  stepDefinitions: OnboardingStepDefinition[],
): { totalUsers: number; steps: OnboardingFunnelStep[] } {
  const actorSteps = new Map<string, Set<number>>();

  for (const row of rows) {
    const actorId = row?.[0] as string | undefined;
    const eventName = row?.[1] as string | undefined;
    const property = row?.[2] as string | null | undefined;
    if (!actorId || !eventName) continue;
    const stepIndex = stepIndexFor(stepDefinitions, eventName, property);
    if (stepIndex == null) continue;

    const completed = actorSteps.get(actorId) ?? new Set<number>();
    completed.add(stepIndex);
    actorSteps.set(actorId, completed);
  }

  const usersByStep = new Array<number>(stepDefinitions.length).fill(0);

  for (const completedSteps of Array.from(actorSteps.values())) {
    let furthestSequentialStep = -1;
    for (let stepIndex = 0; stepIndex < stepDefinitions.length; stepIndex++) {
      if (!completedSteps.has(stepIndex)) break;
      furthestSequentialStep = stepIndex;
    }

    for (let stepIndex = 0; stepIndex <= furthestSequentialStep; stepIndex++) {
      usersByStep[stepIndex] += 1;
    }
  }

  const totalUsers = usersByStep[0] ?? 0;
  const steps = stepDefinitions.map((s, index) => ({
    key: s.key,
    label: s.label,
    users: usersByStep[index],
    completionRate:
      totalUsers > 0 ? Math.round((usersByStep[index] / totalUsers) * 10000) / 100 : 0,
  }));

  return { totalUsers, steps };
}

export function computeFunnelSteps(rows: unknown[][]): {
  totalUsers: number;
  steps: OnboardingFunnelStep[];
} {
  return computeFunnel(rows, STEP_DEFINITIONS);
}

export function computeFirstRunFunnelSteps(rows: unknown[][]): {
  totalUsers: number;
  steps: OnboardingFunnelStep[];
} {
  return computeFunnel(rows, FIRST_RUN_STEP_DEFINITIONS);
}
