import { describe, expect, it } from 'vitest';
import {
  ENTRY_EVENT_NAME,
  ENTRY_PROPERTY_VALUE,
  FIRST_RUN_ENTRY_EVENT_NAME,
  FIRST_RUN_ENTRY_PROPERTY_VALUE,
  FIRST_RUN_STEP_DEFINITIONS,
  STEP_DEFINITIONS,
  computeFirstRunFunnelSteps,
  computeFunnelSteps,
} from '../onboarding-funnel';

describe('STEP_DEFINITIONS', () => {
  it('lists the six beats in scenario order, then completed', () => {
    expect(STEP_DEFINITIONS.map((s) => s.key)).toEqual([
      'hello',
      'see',
      'card',
      'talk',
      'write',
      'ready',
      'completed',
    ]);
    expect(STEP_DEFINITIONS.slice(0, -1).every((s) => s.event === 'Onboarding Beat Completed')).toBe(
      true,
    );
    expect(STEP_DEFINITIONS[STEP_DEFINITIONS.length - 1].event).toBe('Onboarding Completed');
  });

  it('enters the funnel on the hello beat', () => {
    expect(ENTRY_EVENT_NAME).toBe('Onboarding Beat Completed');
    expect(ENTRY_PROPERTY_VALUE).toBe('hello');
    expect(STEP_DEFINITIONS[0].key).toBe('hello');
  });
});

describe('FIRST_RUN_STEP_DEFINITIONS', () => {
  it('lists the five steps in walkthrough order, then completed', () => {
    expect(FIRST_RUN_STEP_DEFINITIONS.map((s) => s.key)).toEqual([
      'openWork',
      'setReminder',
      'drift',
      'backToWork',
      'summary',
      'completed',
    ]);
    expect(
      FIRST_RUN_STEP_DEFINITIONS.slice(0, -1).every(
        (s) => s.event === 'First Run Step Completed',
      ),
    ).toBe(true);
    expect(FIRST_RUN_STEP_DEFINITIONS[FIRST_RUN_STEP_DEFINITIONS.length - 1].event).toBe(
      'First Run Completed',
    );
  });

  it('enters the funnel on the openWork step', () => {
    expect(FIRST_RUN_ENTRY_EVENT_NAME).toBe('First Run Step Completed');
    expect(FIRST_RUN_ENTRY_PROPERTY_VALUE).toBe('openWork');
    expect(FIRST_RUN_STEP_DEFINITIONS[0].key).toBe('openWork');
  });
});

describe('computeFunnelSteps', () => {
  const byKey = (steps: { key: string; users: number }[], key: string) =>
    steps.find((s) => s.key === key)!.users;

  it('counts a skipped beat as having reached the step', () => {
    const { totalUsers, steps } = computeFunnelSteps([
      ['a', 'Onboarding Beat Completed', 'hello'],
      ['a', 'Onboarding Beat Completed', 'see'],
      ['a', 'Onboarding Beat Completed', 'card'],
      ['a', 'Onboarding Beat Completed', 'talk'],
      // Skipped, but the row shape carries no `skipped` column — reaching the
      // beat at all is what counts, matching the old `_Skipped` semantics.
      ['a', 'Onboarding Beat Completed', 'write'],
    ]);
    expect(totalUsers).toBe(1);
    expect(byKey(steps, 'write')).toBe(1);
    expect(byKey(steps, 'ready')).toBe(0);
  });

  it('stops a user at the first gap in the ordered funnel', () => {
    const { steps } = computeFunnelSteps([
      ['a', 'Onboarding Beat Completed', 'hello'],
      // see missing
      ['a', 'Onboarding Beat Completed', 'card'],
    ]);
    expect(byKey(steps, 'hello')).toBe(1);
    expect(byKey(steps, 'see')).toBe(0);
    expect(byKey(steps, 'card')).toBe(0);
  });

  it('handles rows arriving out of beat order', () => {
    const { steps } = computeFunnelSteps([
      ['a', 'Onboarding Beat Completed', 'card'],
      ['a', 'Onboarding Beat Completed', 'hello'],
      ['a', 'Onboarding Beat Completed', 'see'],
    ]);
    expect(byKey(steps, 'hello')).toBe(1);
    expect(byKey(steps, 'see')).toBe(1);
    expect(byKey(steps, 'card')).toBe(1);
    expect(byKey(steps, 'talk')).toBe(0);
  });

  it('matches the terminal event by name alone, ignoring the property column', () => {
    const { steps } = computeFunnelSteps([
      ['a', 'Onboarding Beat Completed', 'hello'],
      ['a', 'Onboarding Beat Completed', 'see'],
      ['a', 'Onboarding Beat Completed', 'card'],
      ['a', 'Onboarding Beat Completed', 'talk'],
      ['a', 'Onboarding Beat Completed', 'write'],
      ['a', 'Onboarding Beat Completed', 'ready'],
      ['a', 'Onboarding Completed', ''],
    ]);
    expect(byKey(steps, 'completed')).toBe(1);
  });

  it('reports completion rates against the entrant count', () => {
    const { totalUsers, steps } = computeFunnelSteps([
      ['a', 'Onboarding Beat Completed', 'hello'],
      ['a', 'Onboarding Beat Completed', 'see'],
      ['b', 'Onboarding Beat Completed', 'hello'],
    ]);
    expect(totalUsers).toBe(2);
    expect(steps.find((s) => s.key === 'see')!.completionRate).toBe(50);
  });

  it('ignores legacy Onboarding Step events and malformed rows', () => {
    const { totalUsers } = computeFunnelSteps([
      ['a', 'Onboarding Beat Completed', 'hello'],
      ['a', 'Onboarding Step Name Completed', undefined],
      ['a', 'Onboarding Step ScreenRecording_Skipped Completed', undefined],
      [null as unknown as string, 'Onboarding Beat Completed', 'hello'],
      [] as unknown[],
    ]);
    expect(totalUsers).toBe(1);
  });
});

describe('computeFirstRunFunnelSteps', () => {
  const byKey = (steps: { key: string; users: number }[], key: string) =>
    steps.find((s) => s.key === key)!.users;

  it('counts a dismissed/fallback step as having reached it', () => {
    const { totalUsers, steps } = computeFirstRunFunnelSteps([
      ['a', 'First Run Step Completed', 'openWork'],
      ['a', 'First Run Step Completed', 'setReminder'],
      ['a', 'First Run Step Completed', 'drift'],
    ]);
    expect(totalUsers).toBe(1);
    expect(byKey(steps, 'drift')).toBe(1);
    expect(byKey(steps, 'backToWork')).toBe(0);
  });

  it('stops a user at the first gap', () => {
    const { steps } = computeFirstRunFunnelSteps([
      ['a', 'First Run Step Completed', 'openWork'],
      // setReminder missing
      ['a', 'First Run Step Completed', 'drift'],
    ]);
    expect(byKey(steps, 'openWork')).toBe(1);
    expect(byKey(steps, 'setReminder')).toBe(0);
    expect(byKey(steps, 'drift')).toBe(0);
  });

  it('reaches completed via the terminal event alone', () => {
    const { steps } = computeFirstRunFunnelSteps([
      ['a', 'First Run Step Completed', 'openWork'],
      ['a', 'First Run Step Completed', 'setReminder'],
      ['a', 'First Run Step Completed', 'drift'],
      ['a', 'First Run Step Completed', 'backToWork'],
      ['a', 'First Run Step Completed', 'summary'],
      ['a', 'First Run Completed', ''],
    ]);
    expect(byKey(steps, 'completed')).toBe(1);
  });

  it('does not mix rows from the onboarding funnel in', () => {
    const { totalUsers } = computeFirstRunFunnelSteps([
      ['a', 'Onboarding Beat Completed', 'hello'],
      ['a', 'Onboarding Completed', ''],
    ]);
    expect(totalUsers).toBe(0);
  });
});
