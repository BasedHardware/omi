import '@testing-library/jest-dom/vitest';
import { configure } from '@testing-library/react';

// findBy/waitFor default to 1 s, which loaded hosts miss on slow first renders; keep the wait bounded at 5 s.
configure({ asyncUtilTimeout: 5000 });

// Node 25+ omits the experimental localStorage global unless a file flag is set.
if (
  typeof globalThis.localStorage === 'undefined' ||
  typeof globalThis.localStorage.clear !== 'function'
) {
  const store = new Map<string, string>();
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: {
      getItem: (key: string) => (store.has(key) ? store.get(key)! : null),
      setItem: (key: string, value: string) => {
        store.set(key, String(value));
      },
      removeItem: (key: string) => {
        store.delete(key);
      },
      clear: () => {
        store.clear();
      },
      key: (index: number) => Array.from(store.keys())[index] ?? null,
      get length() {
        return store.size;
      },
    },
  });
}
