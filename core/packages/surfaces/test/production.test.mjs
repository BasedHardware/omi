import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

test("production entry gates fixtures and marks the explicit host platform", async () => {
  const source = await read("src/production/main.tsx");
  assert.match(source, /requestedQa === "memories"/);
  assert.match(source, /dataset\["platform"\]/);
  assert.match(source, /dataset\["theme"\]/);
  assert.match(source, /OMI_PRODUCTION_READY/);
  // red-proof: removing the qa=memories guard would make arbitrary URL state
  // values enter the synthetic fixture path in a production shell.
  assert.match(source, /const fixtureValue = query\.get\("state"\);/);
  assert.match(source, /requestedQa === "memories"/);
  assert.match(source, /fixtureConversationDetailId\(conversationFixture\)/);
  assert.match(source, /fixtureConversationStore\(conversationFixture, requestedQa === "conversation-detail"\)/);
  assert.match(source, /requestedQa === "tasks"/);
  assert.match(source, /TASK_FIXTURE_STATES\.includes/);
  assert.match(source, /TasksStore\.open\(bridge, env, http\)/);
  assert.match(source, /now=\{TASK_FIXED_NOW\}/);
  // red-proof: dropping the detail-fixture fallback strands the documented
  // qa=conversation-detail URL on a not-found view unless a hidden row ID is
  // supplied; dropping the tasks guard lets an arbitrary state select a task
  // fixture or leaves the production Tasks navigation pointing at Memories.
});

test("desktop-only Rewind stays out of mobile captured tabs", async () => {
  const source = await read("src/production/ProductionChrome.tsx");
  const mobileTabs = source.match(/<div className="nav-mobile">([\s\S]*?)<\/div>/)?.[1] ?? "";
  assert.match(source, /nav\.rewind/);
  assert.doesNotMatch(mobileTabs, /nav\.rewind/);
  assert.match(mobileTabs, /nav\.conversations/);
  assert.match(mobileTabs, /nav\.tasks/);
  // red-proof: adding Rewind to nav-mobile violates the binding's desktop-only rule.
});

test("conversation production slice stays within the ratified list/detail contract", async () => {
  const source = await read("src/production/ConversationsProduction.tsx");
  const fixtures = await read("src/production/conversation-fixtures.ts");
  assert.match(source, /store\.patch\(conversation\.id/);
  assert.match(source, /folderId/);
  assert.match(source, /formatDuration/);
  assert.match(source, /conversation-detail/);
  assert.doesNotMatch(source, /store\.create/);
  assert.match(source, /store\.delete\(conversation\.id\)/);
  assert.match(fixtures, /delete\(conversationId\)/);
  assert.doesNotMatch(source, /failure\.detail/);
  assert.doesNotMatch(source, /participants|transcript|generate|chat/i);
  for (const state of ["loading", "empty", "empty-summary", "fallbacks", "unavailable", "saved-failed", "queued", "sending", "retrying", "needs-auth", "dead", "normal", "locked", "discarded", "long"]) {
    assert.match(fixtures, new RegExp(`\\"${state}\\"`));
  }
  assert.match(fixtures, /isLocked: true/);
  assert.match(fixtures, /discarded: true/);
  assert.match(fixtures, /parseRecordId/);
  assert.match(fixtures, /if \(state === "empty" && detail\)/);
  assert.match(source, /\{canPatch && <div className="conversation-detail-actions">/);
  const editableActions = source.match(/\{canPatch && <div className="conversation-detail-actions">([\s\S]*?)<\/div>\}/)?.[1] ?? "";
  assert.match(editableActions, /store\.delete\(conversation\.id\)/);
  assert.match(editableActions, /confirm\(t\(locale, "conversations\.deleteConfirm"\)\)/);
  assert.match(source, /conversations\.discardedBody/);
  assert.match(source, /conversation\.starred \? t\(locale, "conversations\.unstar"\) : t\(locale, "conversations\.star"\)/);
  // red-proof: moving delete outside canPatch lets locked/discarded rows mutate
  // and makes this contract guard fail; swapping the visible star labels makes
  // the action announce the opposite of what it will do.
});

test("conversation rows are compact, day-grouped, and only attribute safe sources", async () => {
  const source = await read("src/production/ConversationsProduction.tsx");
  const fixtures = await read("src/production/conversation-fixtures.ts");
  assert.match(source, /conversation-day-group/);
  assert.match(source, /dayLabel\(timestamp, locale, Boolean\(fixture\)\)/);
  assert.match(source, /filter === "starred" \? rows\.filter/);
  assert.match(source, /\{ value: "all", label: t\(locale, "conversations\.all"\) \}/);
  assert.match(source, /<ProductionFilterChips[^>]+value=\{filter\}[^>]+onValueChange=\{setFilter\}/);
  assert.match(source, /sourceAttribution\(conversation\.source, locale\)/);
  const attribution = source.match(/function sourceAttribution\([\s\S]*?\n\}/)?.[0] ?? "";
  assert.match(attribution, /source\.trim\(\)\.toLowerCase\(\) === "omi"/);
  assert.match(attribution, /: null;/);
  assert.doesNotMatch(attribution, /return source;/);
  assert.match(source, /conversations\.dateUnavailable/);
  assert.match(source, /conversations\.noDuration/);
  assert.match(fixtures, /Date\.UTC/);
  assert.match(fixtures, /startedAt: null/);
  const rowSource = source.match(/function ConversationRow\([\s\S]*?function ConversationDetail/)?.[0] ?? "";
  assert.match(rowSource, /conversation\.starred \? t\(locale, "conversations\.unstar"\) : t\(locale, "conversations\.star"\)/);
  // red-proof: returning the raw source string, removing the day group, or
  // bringing back a wall-clock fixture makes the relevant assertion fail;
  // reversing the visible star label makes the row action contradict its aria
  // label and the current starred state.
});

test("production controls share search and filter primitives and expose deterministic appearance selection", async () => {
  const primitives = await read("src/production/ProductionPrimitives.tsx");
  const conversations = await read("src/production/ConversationsProduction.tsx");
  const memories = await read("src/production/MemoriesProduction.tsx");
  const tasks = await read("src/production/TasksProduction.tsx");
  const chrome = await read("src/production/ProductionChrome.tsx");
  const entry = await read("src/production/main.tsx");
  assert.match(primitives, /export function ProductionSearchField/);
  assert.match(primitives, /type="search"/);
  assert.match(primitives, /export function ProductionFilterChips/);
  for (const source of [conversations, memories, tasks]) assert.match(source, /<ProductionSearchField/);
  for (const source of [conversations, memories]) assert.match(source, /<ProductionFilterChips/);
  assert.match(chrome, /<option value="system">/);
  assert.match(chrome, /params\.set\("theme", selection\)/);
  assert.match(entry, /themeNameFor\(platform, colorModeFor\(themeSelection\)\)/);
  assert.match(entry, /platform === "mobile" \? "dark" : "light"/);
  // red-proof: duplicating a route-local search field, removing the explicit
  // system choice, or reversing either platform default fails this guard.
});

test("conversation links inherit production colors instead of browser defaults", async () => {
  const styles = await read("src/production/conversations.css");
  const backLink = styles.match(/\.conversation-back\s*\{([\s\S]*?)\}/)?.[1] ?? "";
  assert.match(backLink, /color:\s*var\(--content-primary\)/);
  assert.match(backLink, /text-decoration:\s*none/);
  // red-proof: removing either declaration restores the browser-blue,
  // underlined link that diverges from the native Ink surface.
});

test("production chrome preserves QA context while clearing fixture selection", async () => {
  const source = await read("src/production/ProductionChrome.tsx");
  assert.match(source, /params\.delete\("qa"\)/);
  assert.match(source, /params\.delete\("state"\)/);
  assert.match(source, /params\.get\("platform"\)|location\.search/);
  assert.match(source, /href\("tasks"\)/);
  assert.match(source, /href\("home"\)/);
  assert.match(source, /active === "home" \? "page"/);
  assert.match(source, /active === "tasks" \? "page"/);
  assert.match(source, /export function ProductionLibrarySegment/);
  // red-proof: route links must not strand mobile/platform/profile QA on the
  // prior fixture, while profile remains available for the bridge shell. A
  // Home and Tasks must identify themselves in both navs without inheriting
  // the Library-only segmented rail.
});

test("desktop glass chrome keeps the reference hierarchy without changing mobile navigation", async () => {
  const chrome = await read("src/production/ProductionChrome.tsx");
  const styles = await read("src/production/styles.css");
  assert.match(chrome, /nav-utilities/);
  assert.match(chrome, /export function ProductionLibrarySegment/);
  assert.match(styles, /grid-template-rows: var\(--desktop-nav-height\) var\(--desktop-panel-gap\) minmax\(0, 1fr\)/);
  assert.match(styles, /data-native-glass="true"/);
  assert.match(styles, /\.memory-card-header \{ order: 2;/);
  assert.match(styles, /\.memory-content \{ order: 1;/);
  assert.match(styles, /html\[data-platform="mobile"\] \.production-nav \.nav-mobile/);
  // red-proof: restoring metadata above desktop memory copy, flattening the
  // two glass islands, or dropping the mobile-specific navigation fails here.
});

test("memory cards keep locked and provenance behavior honest", async () => {
  const source = await read("src/production/MemoriesProduction.tsx");
  assert.match(source, /splitProvenance\(memory\.content\)/);
  assert.match(source, /locked\.body/);
  assert.match(source, /await store\.discardDeadLetter\(letter\.opId\)/);
  assert.match(source, /memory\.locked \? \(/);
  assert.match(source, /store\.patch\(memory\.id, \{ visibility: targetVisibility \}\)/);
  assert.match(source, /store\.delete\(memory\.id\)/);
  const lockedBranch = source.match(/\{memory\.locked \? \(([\s\S]*?)\) : editing/)?.[1] ?? "";
  assert.doesNotMatch(lockedBranch, /store\.patch\(memory\.id, \{ content/);
  assert.doesNotMatch(source, /provenance-prefix/);
  assert.match(source, /<p className="memory-content">\{visibleText\}<\/p>/);
  assert.doesNotMatch(source, /failure\.detail/);
  assert.doesNotMatch(source, /setReview/);
  assert.doesNotMatch(source, /memories\.(accept|reject)/);
  assert.doesNotMatch(source, /t\("en"/);
  // red-proof: rendering failure.detail or the provenance prefix in the body
  // would expose backend/debug text or duplicate the source label.
});

test("fixture matrix covers the truthful production states", async () => {
  const source = await read("src/production/memory-fixtures.ts");
  for (const state of ["loading", "empty", "unavailable", "saved-failed", "queued", "sending", "retrying", "needs-auth", "dead", "locked", "long"]) {
    assert.match(source, new RegExp(`\\"${state}\\"`));
  }
  assert.match(source, /FIXED_NOW = Date\.UTC/);
  // red-proof: replacing fixed fixture time with Date.now() makes screenshot
  // evidence drift between runs and invalidates visual comparisons.
});

test("i18n hardcoded-copy guard walks nested JSX text and expressions", async () => {
  const source = await read("../../scripts/check-i18n-parity.mjs");
  assert.match(source, /ts\.isJsxText\(node\)/);
  assert.match(source, /ts\.isJsxExpression\(node\)/);
  assert.match(source, /visitAst\(sourceFile\)/);
  for (const semanticAttribute of ["aria-hidden", "aria-disabled", "aria-live", "viewBox", "focusable"]) {
    assert.match(source, new RegExp(`name === \\"${semanticAttribute}\\"`));
  }
  // red-proof: a checker that only scans top-level JSX would miss a literal
  // nested under a wrapper and let visible English copy ship untranslated.
  // SVG geometry and ARIA state are non-copy; removing any explicit semantic
  // allowlist entry makes the real production chrome fail the aggregate gate.
});

test("fixture ids are parsed RecordIds and platform CSS is attribute-driven", async () => {
  const fixtures = await read("src/production/memory-fixtures.ts");
  const styles = await read("src/production/styles.css");
  assert.match(fixtures, /parseRecordId/);
  assert.doesNotMatch(fixtures, /memory-001|memory-002/);
  assert.match(styles, /html\[data-platform="desktop"\]/);
  assert.match(styles, /html\[data-platform="mobile"\]/);
  assert.doesNotMatch(styles, /html\[data-platform="desktop"\].*memory-grid[^\n]*repeat\(/);
  assert.doesNotMatch(styles, /@media\s*\(min-width/);
  // red-proof: replacing an attribute selector with a width media override
  // would silently make a requested mobile QA fixture render desktop chrome.
});
