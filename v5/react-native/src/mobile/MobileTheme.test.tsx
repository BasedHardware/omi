import {NativeModules} from 'react-native';
import {
  loadMobileAppearance,
  parseMobileAppearance,
  resetMobileAppearanceForTests,
  resolveMobileScheme,
  saveMobileAppearance,
} from './MobileTheme';

afterEach(() => {
  delete (globalThis as {localStorage?: unknown}).localStorage;
  delete (NativeModules as {OmiNative?: unknown}).OmiNative;
  resetMobileAppearanceForTests();
});

test('System follows the OS scheme; an unknown OS scheme stays dark', () => {
  expect(resolveMobileScheme('system', 'light')).toBe('light');
  expect(resolveMobileScheme('system', 'dark')).toBe('dark');
  expect(resolveMobileScheme('system', null)).toBe('dark');
  expect(resolveMobileScheme('light', 'dark')).toBe('light');
  expect(resolveMobileScheme('dark', 'light')).toBe('dark');
});

test('unknown stored values fall back to System', () => {
  expect(parseMobileAppearance('light')).toBe('light');
  expect(parseMobileAppearance('sepia')).toBe('system');
  expect(parseMobileAppearance(null)).toBe('system');
});

test('the choice persists in web storage and survives without it', () => {
  const store = new Map<string, string>();
  (globalThis as {localStorage?: unknown}).localStorage = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => store.set(key, value),
  };
  saveMobileAppearance('light');
  expect(store.get('omi.mobile.appearance')).toBe('light');
  expect(loadMobileAppearance()).toBe('light');
  delete (globalThis as {localStorage?: unknown}).localStorage;
  // Without web storage the in-process choice still holds.
  saveMobileAppearance('dark');
  expect(loadMobileAppearance()).toBe('dark');
});

test('a throwing storage never breaks the appearance', () => {
  (globalThis as {localStorage?: unknown}).localStorage = {
    getItem: () => {
      throw new Error('blocked');
    },
    setItem: () => {
      throw new Error('blocked');
    },
  };
  expect(() => saveMobileAppearance('light')).not.toThrow();
  expect(loadMobileAppearance()).toBe('light');
});

test('the phone apps restore the stored choice from the native constant', () => {
  const setAppearance = jest.fn(() => Promise.resolve('dark'));
  (NativeModules as {OmiNative?: unknown}).OmiNative = {
    getConstants: () => ({appearance: 'light'}),
    setAppearance,
  };
  expect(loadMobileAppearance()).toBe('light');
  saveMobileAppearance('dark');
  expect(setAppearance).toHaveBeenCalledWith('dark');
  expect(loadMobileAppearance()).toBe('dark');
});

test('a failed native write keeps the in-process choice', async () => {
  (NativeModules as {OmiNative?: unknown}).OmiNative = {
    appearance: 'sepia',
    setAppearance: jest.fn(() => Promise.reject(new Error('disk'))),
  };
  expect(loadMobileAppearance()).toBe('system');
  expect(() => saveMobileAppearance('light')).not.toThrow();
  await Promise.resolve();
  expect(loadMobileAppearance()).toBe('light');
});
