import {
  loadMobileAppearance,
  parseMobileAppearance,
  resolveMobileScheme,
  saveMobileAppearance,
} from './MobileTheme';

afterEach(() => {
  delete (globalThis as {localStorage?: unknown}).localStorage;
  saveMobileAppearance('system');
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
  // Native shells have no JS store: the choice lasts for the process.
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
