import {
  desktopItinerary,
  desktopProgressSteps,
  mobileSetupSteps,
  nextDesktopStep,
  nextMobileSetupStep,
  previousDesktopStep,
  previousMobileSetupStep,
} from './onboardingFlow';

test('mobile setup follows the Flutter first-run order', () => {
  expect([...mobileSetupSteps]).toEqual([
    'consent',
    'name',
    'language',
    'source',
    'permissions',
    'speech',
    'knowledge',
    'complete',
  ]);
  expect(nextMobileSetupStep('consent')).toBe('name');
  expect(previousMobileSetupStep('name')).toBe('consent');
  expect(nextMobileSetupStep('complete')).toBeNull();
  expect(previousMobileSetupStep('consent')).toBeNull();
});

test('desktop itinerary matches Context for Claude and drops sign-in after restore', () => {
  expect(desktopItinerary(false)).toEqual([
    'welcome',
    'value',
    'signIn',
    'permissions',
    'harnesses',
    'tutorial',
    'finish',
  ]);
  expect(desktopItinerary(true)).toEqual([
    'welcome',
    'value',
    'permissions',
    'harnesses',
    'tutorial',
    'finish',
  ]);
  expect(nextDesktopStep('signIn', true)).toBe('permissions');
  expect(previousDesktopStep('permissions', true)).toBeNull();
  expect(previousDesktopStep('value', false)).toBe('welcome');
  expect(desktopProgressSteps(false)).toEqual(desktopProgressSteps(true));
  expect(desktopProgressSteps(true)).toHaveLength(6);
});
