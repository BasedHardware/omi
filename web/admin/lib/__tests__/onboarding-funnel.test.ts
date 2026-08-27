import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import {
  ALL_EVENT_NAMES,
  ENTRY_EVENT_NAME,
  STEP_DEFINITIONS,
  computeFunnelSteps,
} from '../onboarding-funnel';

const ONBOARDING_VIEW = path.resolve(
  __dirname,
  '../../../../desktop/macos/Desktop/Sources/Onboarding/OnboardingView.swift',
);

/** (step index, stepName) pairs actually emitted by the app, in step order. */
function emittedStepNames(): { step: number; stepName: string }[] {
  const source = readFileSync(ONBOARDING_VIEW, 'utf8');
  const re =
    /onboardingStepCompleted\(\s*step:\s*(\d+),\s*stepName:\s*"([^"]+)"/g;
  const out: { step: number; stepName: string }[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(source)) !== null) {
    out.push({ step: Number(m[1]), stepName: m[2] });
  }
  return out.sort((a, b) => a.step - b.step);
}

describe('STEP_DEFINITIONS vs OnboardingView.swift', () => {
  it('covers exactly the events the app emits, with no dead steps', () => {
    const emitted = emittedStepNames();
    expect(emitted.length).toBeGreaterThan(20); // sanity: the regex matched

    const expected = new Set(
      emitted.map(({ stepName }) => `Onboarding Step ${stepName} Completed`),
    );
    // The terminal event comes from PostHogManager.onboardingCompleted().
    expected.add('Onboarding Completed');

    expect(new Set(ALL_EVENT_NAMES)).toEqual(expected);
  });

  it('orders steps the way the app advances through them', () => {
    const emitted = emittedStepNames();
    const swiftOrder: number[] = [];
    for (const { step } of emitted) {
      if (swiftOrder[swiftOrder.length - 1] !== step) swiftOrder.push(step);
    }

    const routeOrder = STEP_DEFINITIONS.filter((s) => s.key !== 'completed');
    expect(routeOrder.length).toBe(swiftOrder.length);
    routeOrder.forEach((definition, index) => {
      const stepIndex = swiftOrder[index];
      const names = emitted
        .filter((e) => e.step === stepIndex)
        .map((e) => `Onboarding Step ${e.stepName} Completed`);
      expect(new Set(definition.eventNames)).toEqual(new Set(names));
    });
    expect(STEP_DEFINITIONS[STEP_DEFINITIONS.length - 1].key).toBe('completed');
  });

  it('pairs every skippable step with its _Skipped variant', () => {
    // Regression: 'goal' listed only the completed event, so skippers vanished.
    const goal = STEP_DEFINITIONS.find((s) => s.key === 'goal');
    expect(goal?.eventNames).toContain('Onboarding Step Goal_Skipped Completed');
  });

  it('no longer lists the removed Notifications / Research steps', () => {
    expect(ALL_EVENT_NAMES).not.toContain('Onboarding Step Notifications Completed');
    expect(ALL_EVENT_NAMES).not.toContain('Onboarding Step Research Completed');
  });

  it('enters the funnel on the Name step', () => {
    expect(ENTRY_EVENT_NAME).toBe('Onboarding Step Name Completed');
    expect(STEP_DEFINITIONS[0].key).toBe('name');
  });
});

describe('computeFunnelSteps', () => {
  const byKey = (steps: { key: string; users: number }[], key: string) =>
    steps.find((s) => s.key === key)!.users;

  it('counts a skipper as having reached the step', () => {
    const { totalUsers, steps } = computeFunnelSteps([
      ['a', 'Onboarding Step Name Completed'],
      ['a', 'Onboarding Step Language Completed'],
      ['a', 'Onboarding Step HowDidYouHear Completed'],
      ['a', 'Onboarding Step Trust Completed'],
      ['a', 'Onboarding Step ScreenRecording_Skipped Completed'],
    ]);
    expect(totalUsers).toBe(1);
    expect(byKey(steps, 'screen_recording')).toBe(1);
    expect(byKey(steps, 'full_disk_access')).toBe(0);
  });

  it('stops a user at the first gap in the ordered funnel', () => {
    const { steps } = computeFunnelSteps([
      ['a', 'Onboarding Step Name Completed'],
      // Language missing.
      ['a', 'Onboarding Step HowDidYouHear Completed'],
    ]);
    expect(byKey(steps, 'name')).toBe(1);
    expect(byKey(steps, 'language')).toBe(0);
    expect(byKey(steps, 'how_did_you_hear')).toBe(0);
  });

  it('reports completion rates against the entrant count', () => {
    const { totalUsers, steps } = computeFunnelSteps([
      ['a', 'Onboarding Step Name Completed'],
      ['a', 'Onboarding Step Language Completed'],
      ['b', 'Onboarding Step Name Completed'],
    ]);
    expect(totalUsers).toBe(2);
    expect(steps.find((s) => s.key === 'language')!.completionRate).toBe(50);
  });

  it('ignores unknown events and malformed rows', () => {
    const { totalUsers } = computeFunnelSteps([
      ['a', 'Onboarding Step Name Completed'],
      ['a', 'Some Other Event'],
      [null as unknown as string, 'Onboarding Step Name Completed'],
      [] as unknown[],
    ]);
    expect(totalUsers).toBe(1);
  });
});
