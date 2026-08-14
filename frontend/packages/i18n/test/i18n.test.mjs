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

test("catalog does not claim capabilities outside the sanctioned production slices", () => {
  // red-proof: restoring a removed invented key must fail this guard.
  //
  // NARROWED 2026-08-08 (FE-SURFACES), and the narrowing is the point of the comment.
  // This guard was written under glass-parity provisional ruling 5, which said Chat must
  // not be fabricated. Overnight board ruling PR-7 supersedes that for three surfaces:
  // "Chat, Settings, and Listen have no ratified backend, but their surfaces can be built
  // against store ports with deterministic fixtures — which is how every existing surface
  // was built." So `chat`, `transcript` and `offline` are removed from the forbidden set:
  // the first is sanctioned, and the other two are required by the ratified capacity
  // contract's own wording ("N hours awaiting transcription", offline buffering).
  //
  // The guard is NOT merely shrunk. The list below replaces them with the approved
  // deprecations and known contract gaps, which is what must actually never appear —
  // DEP-003 personas, DEP-012 agentic execution, DEP-013 wrapped, DEP-014 insight
  // dashboards, DEP-015 goals authoring, plus the explicitly ruled-out checkout surface.
  // Escalated for David in blocked/FE-SURFACES-i18n-capability-guard.md.
  const forbidden = /participant|priority|tags?|tier|connected|expired/i;
  for (const key of Object.keys(EN_MESSAGES)) assert.equal(forbidden.test(key), false, key);
  for (const value of Object.values(EN_MESSAGES)) assert.equal(forbidden.test(value), false, value);

  // red-proof: adding a "goals.title" or "chat.generate" key must fail this. These are
  // approved cuts, not gaps waiting to be filled, so a catalog entry for one is evidence
  // that a surface fabricated it.
  //
  // EXTENDED 2026-08-08 (coordinator): the concept list now checks VALUES as well as keys.
  // As first written it inspected keys only, while the guard it replaced inspected both —
  // so `"home.section": "Your Goals"` would have passed. Visible copy is exactly where a
  // fabricated capability shows up to a user, so the value side is the half that matters.
  // `generate` is word-bounded because "generated" is legitimate copy about propositions
  // (memoriesPlatform.readOnlyNote); the cut is the Generate *capability*, not the verb.
  const deprecatedConcepts = /goal|quicknote|\bgenerate\b|persona|wrapped|insight|checkout|bulkselect/i;
  for (const key of Object.keys(EN_MESSAGES)) assert.equal(deprecatedConcepts.test(key), false, key);
  for (const value of Object.values(EN_MESSAGES)) assert.equal(deprecatedConcepts.test(value), false, value);

  // Key-shaped only: a `rewind.*` key other than the disabled affordance's own title.
  const deprecatedKeyShapes = /rewind\w*\.(?!title)/i;
  for (const key of Object.keys(EN_MESSAGES)) assert.equal(deprecatedKeyShapes.test(key), false, key);
});
