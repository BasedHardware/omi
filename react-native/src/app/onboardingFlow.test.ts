import {
  desktopItinerary,
  desktopProgressSteps,
  mobileItinerary,
  mobileSetupSteps,
  nextDesktopStep,
  nextMobileSetupStep,
  normalizeDeviceLanguage,
  previousDesktopStep,
  previousMobileSetupStep,
} from './onboardingFlow';

test('mobile setup follows the Flutter first-run order without dead stub steps', () => {
  expect([...mobileSetupSteps]).toEqual([
    'consent',
    'language',
    'source',
    'permissions',
    'speech',
    'complete',
  ]);
  expect(nextMobileSetupStep('consent')).toBe('language');
  expect(previousMobileSetupStep('language')).toBe('consent');
  expect(nextMobileSetupStep('complete')).toBeNull();
  expect(previousMobileSetupStep('consent')).toBeNull();
});

test('native phones skip voice enrollment; browsers keep it', () => {
  expect(mobileItinerary(true)).toEqual([
    'consent',
    'language',
    'source',
    'permissions',
    'complete',
  ]);
  expect(mobileItinerary(false)).toEqual([...mobileSetupSteps]);
  // Navigation helpers agree with the phone itinerary end-to-end.
  expect(nextMobileSetupStep('permissions', mobileItinerary(true))).toBe(
    'complete',
  );
  expect(previousMobileSetupStep('complete', mobileItinerary(true))).toBe(
    'permissions',
  );
});

test('desktop itinerary matches Context for Claude and drops sign-in after restore', () => {
  expect(desktopItinerary(false)).toEqual([
    'welcome',
    'value',
    'signIn',
    'permissions',
    'harnesses',
    'data',
    'tutorial',
    'finish',
  ]);
  expect(desktopItinerary(true)).toEqual([
    'welcome',
    'value',
    'permissions',
    'harnesses',
    'data',
    'tutorial',
    'finish',
  ]);
  expect(nextDesktopStep('signIn', true)).toBe('permissions');
  expect(previousDesktopStep('permissions', true)).toBeNull();
  expect(previousDesktopStep('value', false)).toBe('welcome');
  expect(nextDesktopStep('harnesses', true)).toBe('data');
  expect(previousDesktopStep('data', true)).toBe('harnesses');
  expect(previousDesktopStep('tutorial', true)).toBe('data');
  expect(desktopProgressSteps(false)).toEqual(desktopProgressSteps(true));
  expect(desktopProgressSteps(true)).toHaveLength(7);
});

test('normalizeDeviceLanguage maps OS locales onto language codes', () => {
  expect(normalizeDeviceLanguage('en_US')).toBe('en');
  expect(normalizeDeviceLanguage('pt-BR')).toBe('pt');
  expect(normalizeDeviceLanguage(' de ')).toBe('de');
  expect(normalizeDeviceLanguage('zh-Hans-CN')).toBe('zh');
  expect(normalizeDeviceLanguage('')).toBe('en');
  expect(normalizeDeviceLanguage(null)).toBe('en');
  expect(normalizeDeviceLanguage(42)).toBe('en');
  expect(normalizeDeviceLanguage('---')).toBe('en');
});
