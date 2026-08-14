import { EN_MESSAGES } from "./catalog.js";

export { EN_MESSAGES } from "./catalog.js";

/** The legacy app's English template plus its 48 translation IDs. */
export const SUPPORTED_LOCALES = [
  "ar",
  "be",
  "bg",
  "bn",
  "bs",
  "ca",
  "cs",
  "da",
  "de",
  "el",
  "en",
  "es",
  "et",
  "fa",
  "fi",
  "fr",
  "he",
  "hi",
  "hr",
  "hu",
  "id",
  "it",
  "ja",
  "kn",
  "ko",
  "lt",
  "lv",
  "mk",
  "mr",
  "ms",
  "nl",
  "no",
  "pl",
  "pt",
  "ro",
  "ru",
  "sk",
  "sl",
  "sr",
  "sv",
  "ta",
  "te",
  "th",
  "tl",
  "tr",
  "uk",
  "ur",
  "vi",
  "zh",
] as const;

export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];
export type MessageCatalog = typeof EN_MESSAGES;
export type MessageKey = keyof MessageCatalog;
export const TRANSLATED_LOCALES = ["en"] as const satisfies readonly SupportedLocale[];
export const FALLBACK_LOCALES = SUPPORTED_LOCALES.filter(
  (locale): locale is Exclude<SupportedLocale, "en"> => locale !== "en",
);

export type TranslationSource = "translated" | "english-fallback";

export type LocaleResolution = {
  requested: string;
  locale: SupportedLocale;
  source: TranslationSource;
  isFallback: boolean;
};

type PlaceholderNames<S extends string> = S extends `${string}{${infer Name}}${infer Rest}`
  ? Name extends `${string},${string}`
    ? PlaceholderNames<Rest>
    : Name | PlaceholderNames<Rest>
  : never;

export type MessageVariables<K extends MessageKey> = [
  PlaceholderNames<MessageCatalog[K]>,
] extends [never]
  ? never
  : Record<PlaceholderNames<MessageCatalog[K]>, string | number>;

type TranslationArguments<K extends MessageKey> = [
  PlaceholderNames<MessageCatalog[K]>,
] extends [never]
  ? [variables?: never]
  : [variables: MessageVariables<K>];

const PLACEHOLDER_PATTERN = /\{([A-Za-z][A-Za-z0-9_.-]*)\}/g;

function normalizeRequestedLocale(requested: string): string {
  return requested.trim().replaceAll("_", "-").toLowerCase();
}

export function resolveLocale(requested: string): LocaleResolution {
  const normalized = normalizeRequestedLocale(requested);
  const language = normalized.split("-")[0] ?? "en";
  const locale = SUPPORTED_LOCALES.includes(language as SupportedLocale)
    ? (language as SupportedLocale)
    : "en";
  // English is the only translated catalog. A non-English supported ID and an
  // unknown ID both resolve to English, but both must remain visibly fallback.
  const isFallback = language !== "en";
  return {
    requested,
    locale,
    source: isFallback ? "english-fallback" : "translated",
    isFallback,
  };
}

export function getTranslationCoverage(): {
  supportedLocaleCount: number;
  translatedLocaleCount: number;
  fallbackLocaleCount: number;
  translatedLocales: readonly SupportedLocale[];
  fallbackLocales: readonly SupportedLocale[];
} {
  return {
    supportedLocaleCount: SUPPORTED_LOCALES.length,
    translatedLocaleCount: TRANSLATED_LOCALES.length,
    fallbackLocaleCount: FALLBACK_LOCALES.length,
    translatedLocales: TRANSLATED_LOCALES,
    fallbackLocales: FALLBACK_LOCALES,
  };
}

function intlLocale(locale: SupportedLocale): string {
  try {
    return new Intl.Locale(locale).toString();
  } catch {
    return "en";
  }
}

function interpolate(template: string, variables: Record<string, string | number> | undefined): string {
  return template.replace(PLACEHOLDER_PATTERN, (whole, name: string) => {
    if (!variables || !Object.hasOwn(variables, name)) {
      throw new Error(`Missing interpolation variable {${name}}`);
    }
    return String(variables[name]);
  });
}

/** Translate a canonical key; all non-English IDs explicitly report English fallback in `resolveLocale`. */
export function t<K extends MessageKey>(
  requestedLocale: string,
  key: K,
  ...args: TranslationArguments<K>
): string {
  const template = EN_MESSAGES[key];
  const variables = args[0] as Record<string, string | number> | undefined;
  return interpolate(template, variables);
}

export const formatMessage = t;

export function formatDate(
  value: Date | number,
  requestedLocale = "en",
  options: Intl.DateTimeFormatOptions = { dateStyle: "medium" },
): string {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) throw new RangeError("formatDate received an invalid date");
  const locale = resolveLocale(requestedLocale).locale;
  return new Intl.DateTimeFormat(intlLocale(locale), options).format(date);
}

export function formatNumber(
  value: number,
  requestedLocale = "en",
  options: Intl.NumberFormatOptions = {},
): string {
  const locale = resolveLocale(requestedLocale).locale;
  return new Intl.NumberFormat(intlLocale(locale), options).format(value);
}

export type DurationStyle = "long" | "short" | "narrow";

/** Formats a supplied duration in seconds; it never reads the wall clock. */
export function formatDuration(
  totalSeconds: number,
  requestedLocale = "en",
  style: DurationStyle = "short",
): string {
  if (!Number.isFinite(totalSeconds) || totalSeconds < 0) {
    throw new RangeError("formatDuration expects a finite, non-negative number of seconds");
  }
  const locale = intlLocale(resolveLocale(requestedLocale).locale);
  let remaining = Math.round(totalSeconds);
  const units = [
    { unit: "day", seconds: 86_400 },
    { unit: "hour", seconds: 3_600 },
    { unit: "minute", seconds: 60 },
    { unit: "second", seconds: 1 },
  ] as const;
  const values: Array<{ unit: (typeof units)[number]["unit"]; value: number }> = [];
  for (const unit of units) {
    const value = Math.floor(remaining / unit.seconds);
    remaining %= unit.seconds;
    if (value > 0 || (values.length === 0 && unit.unit === "second")) {
      values.push({ unit: unit.unit, value });
    }
    if (values.length === 2) break;
  }
  const parts = values.map(({ unit, value }) =>
    new Intl.NumberFormat(locale, {
      style: "unit",
      unit,
      unitDisplay: style,
      maximumFractionDigits: 0,
    }).format(value),
  );
  return new Intl.ListFormat(locale, { style, type: "unit" }).format(parts);
}
