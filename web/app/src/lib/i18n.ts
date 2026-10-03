// UI translation. Catalogs are keyed by the English source text (the convention the
// desktop apps use too), so untranslated strings fall back to English and a string is
// translated by adding one entry — no key naming scheme to maintain.
//
// The language is resolved once per page load: the saved choice in localStorage, or
// the browser language when it is 'system' (the default). Changing it reloads every
// open tab, so `t()` can stay a plain function instead of a hook. The active catalog
// is a lazy chunk loaded before the app mounts (register-client-route); English
// loads nothing. Never call `t()` at module scope — use a getter or a function.

export type UiLanguage = 'en' | 'es';
export type UiLanguagePreference = 'system' | UiLanguage;

export const UI_LANGUAGE_STORAGE_KEY = 'omi.uiLanguage';

export const UI_LANGUAGES: { code: UiLanguagePreference; label: string }[] = [
  { code: 'system', label: 'System default' },
  { code: 'en', label: 'English' },
  { code: 'es', label: 'Español' },
];

type Catalog = Record<string, string>;

const catalogLoaders: Record<
  Exclude<UiLanguage, 'en'>,
  () => Promise<{ default: Catalog }>
> = {
  es: () => import('./i18n/es.json'),
};
const catalogs: Partial<Record<UiLanguage, Catalog>> = {};

export function resolveUiLanguage(
  preference: string | null | undefined,
  systemLanguages: readonly string[],
): UiLanguage {
  if (preference === 'en' || preference === 'es') return preference;
  for (const tag of systemLanguages) {
    const base = tag.split(/[-_]/)[0]?.toLowerCase();
    if (base === 'es') return 'es';
    if (base === 'en') return 'en';
  }
  return 'en';
}

function systemLanguages(): readonly string[] {
  if (typeof navigator === 'undefined') return [];
  // Server runtimes (Bun) define navigator without languages; keep only real tags.
  const tags = navigator.languages?.length ? navigator.languages : [navigator.language];
  return tags.filter((tag): tag is string => typeof tag === 'string');
}

export function readUiLanguagePreference(): UiLanguagePreference {
  try {
    const saved = localStorage.getItem(UI_LANGUAGE_STORAGE_KEY);
    return saved === 'en' || saved === 'es' ? saved : 'system';
  } catch {
    return 'system';
  }
}

let current: UiLanguage = resolveUiLanguage(
  readUiLanguagePreference(),
  systemLanguages(),
);

export function uiLanguage(): UiLanguage {
  return current;
}

// Test seam: switch the active language without a page reload.
export function setUiLanguageForTesting(language: UiLanguage): void {
  current = language;
}

/** Load the catalog for `language` (default: this page's language). Resolves
 *  immediately for English and an already-loaded catalog; a failed load leaves the
 *  UI in English rather than blocking the app. */
export async function loadUiCatalog(language: UiLanguage = current): Promise<void> {
  if (language === 'en' || catalogs[language]) return;
  try {
    catalogs[language] = (await catalogLoaders[language]()).default;
  } catch {
    // English fallback.
  }
}

export function translate(
  language: UiLanguage,
  text: string,
  vars?: Record<string, unknown>,
): string {
  const translated = language === 'en' ? text : catalogs[language]?.[text] ?? text;
  if (!vars) return translated;
  return translated.replace(/\{(\w+)\}/g, (match, name: string) => {
    const value = Object.hasOwn(vars, name) ? vars[name] : undefined;
    return value == null ? match : String(value);
  });
}

/** Translate English UI text. `{name}` placeholders are filled from `vars`. */
export function t(text: string, vars?: Record<string, unknown>): string {
  return translate(current, text, vars);
}

/**
 * Translate a message whose wording depends on a count: `one` when `count` is 1,
 * `other` otherwise (the plural rule English and Spanish share). `{count}` is
 * filled in, so write both forms as whole sentences, never word + "s".
 */
export function tn(
  count: number,
  one: string,
  other: string,
  vars?: Record<string, unknown>,
): string {
  if (count === 1 && one === other) return tc('one', one, { ...vars, count });
  return t(count === 1 ? one : other, { ...vars, count });
}

/**
 * Translate a short English word whose meaning depends on where it appears
 * ("Open" the button vs "Open" the task filter). The catalog key is
 * `context|text`; English and missing entries show `text`.
 */
export function tc(
  context: string,
  text: string,
  vars?: Record<string, unknown>,
): string {
  const key = `${context}|${text}`;
  const hasEntry = current !== 'en' && key in (catalogs[current] ?? {});
  return hasEntry ? translate(current, key, vars) : translate('en', text, vars);
}

/** Locale for Intl/Date formatting: the chosen UI language, or the browser default in English. */
export function uiLocale(): string | undefined {
  return current === 'en' ? undefined : current;
}

/**
 * Locale for screens that always formatted dates and numbers as `en-US`: unchanged in
 * English, the UI language otherwise, so Spanish never shows English month names.
 */
export function formatLocale(): string {
  return current === 'en' ? 'en-US' : current;
}

/** Save the interface language and reload so every string switches together. */
export function setUiLanguagePreference(preference: UiLanguagePreference): void {
  try {
    if (preference === 'system') localStorage.removeItem(UI_LANGUAGE_STORAGE_KEY);
    else localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, preference);
  } catch {
    return;
  }
  if (resolveUiLanguage(preference, systemLanguages()) !== current)
    window.location.reload();
}

/** Reload this tab when another tab changes the interface language. */
export function installUiLanguageSync(): void {
  if (typeof window === 'undefined') return;
  window.addEventListener('storage', (event) => {
    if (event.key !== UI_LANGUAGE_STORAGE_KEY) return;
    if (resolveUiLanguage(readUiLanguagePreference(), systemLanguages()) !== current) {
      window.location.reload();
    }
  });
}
