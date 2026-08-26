// Source of truth: desktop/macos/Desktop/Sources/Onboarding/OnboardingView.swift
//
// Every entry below mirrors an `AnalyticsManager.shared.onboardingStepCompleted(
// step:, stepName:)` call in that file, in the order the app advances through
// `currentStep`. PostHogManager.onboardingStepCompleted formats the event as
// `Onboarding Step <stepName> Completed`, so each `stepName` (including its
// `_Skipped` variant, where the step's view has an `onSkip` handler) maps to
// exactly one string here.
//
// IF YOU RENAME, ADD, OR REMOVE A STEP IN OnboardingView.swift, MIRROR IT HERE.
// This list drifted for months: it still listed a Notifications step that no
// longer exists and a Research step that stopped being emitted in Apr 2026
// (both rendered as permanent ~0 funnel rows), while HowDidYouHear, DataSources
// and Exports were missing entirely and Goal dropped its skip variant.

export type OnboardingStepDefinition = {
  key: string;
  label: string;
  eventNames: string[];
};

/** `Onboarding Step <stepName> Completed`, per PostHogManager.swift. */
function stepEvent(stepName: string): string {
  return `Onboarding Step ${stepName} Completed`;
}

/** A step whose view has no `onSkip` handler — completion is the only exit. */
function step(key: string, label: string, stepName: string): OnboardingStepDefinition {
  return { key, label, eventNames: [stepEvent(stepName)] };
}

/** A step with an `onSkip` handler — skippers must count as having reached it. */
function skippableStep(
  key: string,
  label: string,
  stepName: string,
): OnboardingStepDefinition {
  return {
    key,
    label,
    eventNames: [stepEvent(stepName), stepEvent(`${stepName}_Skipped`)],
  };
}

export const STEP_DEFINITIONS: OnboardingStepDefinition[] = [
  step('name', 'Name', 'Name'), // OnboardingView step 0
  step('language', 'Language', 'Language'), // step 1
  step('how_did_you_hear', 'How Did You Hear', 'HowDidYouHear'), // step 2
  step('trust', 'Trust', 'Trust'), // step 3
  skippableStep('screen_recording', 'Screen Recording', 'ScreenRecording'), // step 4
  skippableStep('full_disk_access', 'Full Disk Access', 'FullDiskAccess'), // step 5
  skippableStep('file_scan', 'File Scan', 'FileScan'), // step 6
  skippableStep('microphone', 'Microphone', 'Microphone'), // step 7
  skippableStep('accessibility', 'Accessibility', 'Accessibility'), // step 8
  skippableStep('automation', 'Automation', 'Automation'), // step 9
  skippableStep('floating_bar_shortcut', 'Floating Bar Shortcut', 'FloatingBarShortcut'), // step 10
  skippableStep('floating_bar', 'Floating Bar', 'FloatingBar'), // step 11
  skippableStep('voice_shortcut', 'Voice Shortcut', 'VoiceShortcut'), // step 12
  skippableStep('voice_demo', 'Voice Demo', 'VoiceDemo'), // step 13
  skippableStep('data_sources', 'Data Sources', 'DataSources'), // step 14
  skippableStep('exports', 'Exports', 'Exports'), // step 15
  skippableStep('goal', 'Goal', 'Goal'), // step 16
  skippableStep('tasks', 'Tasks', 'Tasks'), // step 17
  // PostHogManager.onboardingCompleted() — not a numbered step.
  { key: 'completed', label: 'Completed', eventNames: ['Onboarding Completed'] },
];

/** The entry event that defines a first-ever entrant into the flow. */
export const ENTRY_EVENT_NAME = stepEvent('Name');

export const ALL_EVENT_NAMES: string[] = STEP_DEFINITIONS.flatMap((s) => s.eventNames);

export type OnboardingFunnelStep = {
  key: string;
  label: string;
  users: number;
  completionRate: number;
};

/**
 * Collapse `[actor_id, event]` rows into an ordered funnel. A user counts for a
 * step only if they completed (or skipped) every step up to and including it.
 */
export function computeFunnelSteps(rows: unknown[][]): {
  totalUsers: number;
  steps: OnboardingFunnelStep[];
} {
  const eventToStepIndex = new Map<string, number>();
  STEP_DEFINITIONS.forEach((s, index) => {
    s.eventNames.forEach((eventName) => eventToStepIndex.set(eventName, index));
  });

  const actorSteps = new Map<string, Set<number>>();

  for (const row of rows) {
    const actorId = row?.[0] as string | undefined;
    const eventName = row?.[1] as string | undefined;
    const stepIndex = eventName == null ? undefined : eventToStepIndex.get(eventName);
    if (!actorId || stepIndex == null) continue;

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
      totalUsers > 0 ? Math.round((usersByStep[index] / totalUsers) * 10000) / 100 : 0,
  }));

  return { totalUsers, steps };
}
