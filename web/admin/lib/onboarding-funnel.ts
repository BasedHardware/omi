// Source of truth: desktop/macos/Desktop/Sources/Onboarding/SecondBrain/SBOnboardingModel.swift
//
// Every entry below mirrors one exit from `SBOnboardingModel.Step`, in the order
// `advance(userAnswer:to:)` walks `Step` raw values. The live app emits one
// PostHog event per exit:
//
//   - `Onboarding Step Completed` { step: 'promise'|'name'|…|'referral',
//     index, elapsed_ms, skipped, exit_reason: 'answered'|'skipped'|'auto_granted',
//     permission?, granted? }
//   - `Onboarding Completed` (terminal; no `step` property)
//
// A step counts as "reached" regardless of whether `skipped` is true — same
// semantics as the old `_Skipped` event-name variants, just carried in a
// property instead of the event name. Permission auto-jumps (already granted)
// also emit, so a pre-granted mic does not look like a funnel drop-off.
//
// `skipped` stays a boolean so existing funnel math still counts skippers as
// having reached the step. It is true for both a user "Skip for now"
// (`exit_reason=skipped`, `granted=false`) and a permission page the user
// never saw (`exit_reason=auto_granted`, `granted=true`). Do not compute a
// skip rate from `skipped` alone; filter on the closed `exit_reason` set.
//
// IF YOU RENAME, ADD, OR REMOVE A STEP IN SBOnboardingModel.swift, MIRROR IT HERE.
//
// The PREVIOUS dashboard (one `Onboarding Step <Name> Completed` event per
// step of the dead `OnboardingView.swift` wizard) is not the live flow. Those
// events keep existing in PostHog history from old builds, but this funnel
// does not map them onto the steps above; the event-name filters built from
// this file never include them.

export type OnboardingStepDefinition = {
  key: string;
  label: string;
  /** The PostHog event name this step is reported under. */
  event: string;
  /**
   * The value of the row's property column that identifies this step.
   * `undefined` for a terminal step matched by event name alone (the
   * completion event carries no `step` property).
   */
  property?: string;
};

const ONBOARDING_STEP_EVENT = "Onboarding Step Completed";
const ONBOARDING_COMPLETED_EVENT = "Onboarding Completed";

function flowStep(key: string, label: string): OnboardingStepDefinition {
  return { key, label, event: ONBOARDING_STEP_EVENT, property: key };
}

export const STEP_DEFINITIONS: OnboardingStepDefinition[] = [
  flowStep("promise", "Promise"),
  flowStep("name", "Name"),
  flowStep("howHeard", "How Did You Hear"),
  flowStep("language", "Language"),
  flowStep("role", "Role"),
  flowStep("mic", "Microphone"),
  flowStep("systemAudio", "System Audio"),
  flowStep("screen", "Screen Recording"),
  flowStep("files", "Files"),
  flowStep("accessibility", "Accessibility"),
  flowStep("automation", "Automation"),
  flowStep("notifications", "Notifications"),
  flowStep("shortcutOpen", "Open Shortcut"),
  flowStep("shortcutTalk", "Talk Shortcut"),
  flowStep("screenDemo", "Screen Demo"),
  flowStep("agents", "Agents"),
  flowStep("context", "Context"),
  flowStep("capture", "Capture"),
  flowStep("referral", "Referral"),
  // Onboarding Completed — not a numbered step.
  { key: "completed", label: "Completed", event: ONBOARDING_COMPLETED_EVENT },
];

/** The entry event + property that defines a first-ever entrant into the flow. */
export const ENTRY_EVENT_NAME = ONBOARDING_STEP_EVENT;
export const ENTRY_PROPERTY_NAME = "step";
export const ENTRY_PROPERTY_VALUE = "promise";

export const ALL_EVENT_NAMES: string[] = Array.from(
  new Set(STEP_DEFINITIONS.map((s) => s.event))
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
  property: string | null | undefined
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
 * regardless of any `skipped` value on the underlying event.
 */
export function computeFunnelSteps(rows: unknown[][]): {
  totalUsers: number;
  steps: OnboardingFunnelStep[];
} {
  const actorSteps = new Map<string, Set<number>>();

  for (const row of rows) {
    const actorId = row?.[0] as string | undefined;
    const eventName = row?.[1] as string | undefined;
    const property = row?.[2] as string | null | undefined;
    if (!actorId || !eventName) continue;
    const stepIndex = stepIndexFor(STEP_DEFINITIONS, eventName, property);
    if (stepIndex == null) continue;

    const completed = actorSteps.get(actorId) ?? new Set<number>();
    completed.add(stepIndex);
    actorSteps.set(actorId, completed);
  }

  const usersByStep = new Array<number>(STEP_DEFINITIONS.length).fill(0);

  for (const completedSteps of Array.from(actorSteps.values())) {
    let furthestSequentialStep = -1;
    for (let stepIndex = 0; stepIndex < STEP_DEFINITIONS.length; stepIndex++) {
      if (!completedSteps.has(stepIndex)) break;
      furthestSequentialStep = stepIndex;
    }

    for (let stepIndex = 0; stepIndex <= furthestSequentialStep; stepIndex++) {
      usersByStep[stepIndex] += 1;
    }
  }

  const totalUsers = usersByStep[0] ?? 0;
  const steps = STEP_DEFINITIONS.map((s, index) => ({
    key: s.key,
    label: s.label,
    users: usersByStep[index],
    completionRate:
      totalUsers > 0
        ? Math.round((usersByStep[index] / totalUsers) * 10000) / 100
        : 0,
  }));

  return { totalUsers, steps };
}
