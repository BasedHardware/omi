import {ONBOARDING_HARNESSES} from './onboardingHarnesses';

test('harnesses page lists Apps catalog plus AI assistants, not a Claude connector', () => {
  expect(ONBOARDING_HARNESSES.map(item => item.id)).toEqual([
    'openclaw',
    'hermes',
    'claudeCode',
    'codex',
    'calendar',
    'email',
    'local-files',
    'apple-notes',
    'x',
    'chatgpt',
  ]);
  expect(ONBOARDING_HARNESSES.some(item => item.id === 'claude')).toBe(false);
  expect(
    ONBOARDING_HARNESSES.filter(item => item.kind === 'agent'),
  ).toHaveLength(4);
  expect(
    ONBOARDING_HARNESSES.filter(item => item.kind === 'context'),
  ).toHaveLength(6);
});
