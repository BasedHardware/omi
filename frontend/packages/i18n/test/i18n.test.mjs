import test from "node:test";
import assert from "node:assert/strict";
import {
  EN_MESSAGES,
  FALLBACK_LOCALES,
  SUPPORTED_LOCALES,
  TRANSLATED_LOCALES,
  formatDate,
  formatDuration,
  formatNumber,
  getTranslationCoverage,
  resolveLocale,
  t,
} from "../dist/index.js";

test("keeps the legacy 49-locale identity and explicit fallback count", () => {
  assert.equal(SUPPORTED_LOCALES.length, 49);
  assert.equal(new Set(SUPPORTED_LOCALES).size, 49);
  assert.deepEqual(TRANSLATED_LOCALES, ["en"]);
  assert.equal(FALLBACK_LOCALES.length, 48);
  assert.deepEqual(getTranslationCoverage(), {
    supportedLocaleCount: 49,
    translatedLocaleCount: 1,
    fallbackLocaleCount: 48,
    translatedLocales: ["en"],
    fallbackLocales: FALLBACK_LOCALES,
  });
});

test("reports English fallback rather than pretending a translation exists", () => {
  assert.equal(resolveLocale("en-US").source, "translated");
  assert.equal(resolveLocale("ja").source, "english-fallback");
  assert.equal(resolveLocale("unknown").locale, "en");
  assert.equal(resolveLocale("unknown").source, "english-fallback");
  assert.equal(t("ja", "tasks.title"), EN_MESSAGES["tasks.title"]);
});

test("requires and safely interpolates typed placeholders at runtime", () => {
  assert.equal(t("en", "tasks.dueDate", { date: "Aug 7, 2026" }), "Due Aug 7, 2026");
  assert.throws(() => t("en", "tasks.dueDate", undefined), /Missing interpolation variable/);
  assert.equal(t("en", "queue.sending", { count: 3 }), "Sending changes: 3");
});

test("provides deterministic Intl helpers from caller-supplied values", () => {
  assert.match(formatDate(Date.UTC(2026, 7, 7), "en-US"), /2026/);
  assert.equal(formatNumber(1234.5, "en-US"), "1,234.5");
  assert.match(formatDuration(3661, "en-US"), /1 hr/);
});

test("catalog does not claim capabilities outside the ratified production slices", () => {
  // red-proof: restoring a removed invented key must fail this guard.
  const forbidden = /chat|transcript|participant|priority|tags?|tier|offline|connected|expired/i;
  for (const key of Object.keys(EN_MESSAGES)) assert.equal(forbidden.test(key), false, key);
  for (const value of Object.values(EN_MESSAGES)) assert.equal(forbidden.test(value), false, value);
});
