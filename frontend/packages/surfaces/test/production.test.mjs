import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

test("production entry gates fixtures and marks the explicit host platform", async () => {
  // RETAINED-SOURCE-ASSERTION: entrypoint query gating and host-marker wiring are bootstrap structure.
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
  assert.match(source, /stores\.openTasks\(\)/);
  assert.match(source, /now=\{TASK_FIXED_NOW\}/);
  // red-proof: dropping the detail-fixture fallback strands the documented
  // qa=conversation-detail URL on a not-found view unless a hidden row ID is
  // supplied; dropping the tasks guard lets an arbitrary state select a task
  // fixture or leaves the production Tasks navigation pointing at Memories.
});

test("bridge-unavailable state gives a distinct recovery step and executable retry", async () => {
  const source = await read("src/production/main.tsx");
  const homeStyles = await read("src/production/home.css");
  assert.match(source, /nextAction=\{t\(locale, "qa\.bridgeNext"\)\}/);
  assert.match(source, /retry=\{\{ onRetry: \(\) => window\.location\.reload\(\) \}\}/);
  assert.doesNotMatch(homeStyles, /home-search input:focus-visible/);
  // red-proof: repeating the bridge diagnosis as the next action, omitting the
  // recovery control, or restoring Home's outline reset fails this guard.
});

test("production and lab surfaces do not teach navigation into the dev rig", async () => {
  const [production, lab] = await Promise.all([
    read("src/production/main.tsx"),
    read("src/lab/main.tsx"),
  ]);
  assert.doesNotMatch(production, /href=["'{][^\n]*rig=dev/);
  assert.doesNotMatch(lab, /href=["'{][^\n]*rig=dev/);
  // The explicit developer invocation remains supported, but a visible page
  // can no longer send a person into it.
  assert.match(production, /query\.get\("rig"\) === "dev"/);
  // red-proof: restore either production bridge-unavailable link or the lab
  // hero link. The source contains a user-facing href and this fails.
});

test("conversation production slice stays within the ratified list/detail contract", async () => {
  // RETAINED-SOURCE-ASSERTION: allowed fields and forbidden transcript/create capabilities define the contract boundary.
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
  assert.match(editableActions, /conversation-delete-trigger/);
  assert.match(source, /\{canPatch && confirmingDelete &&/);
  assert.match(source, /const deleteConversation[\s\S]*store\.delete\(conversation\.id\)/);
  assert.doesNotMatch(source, /globalThis\.confirm|window\.confirm/);
  assert.match(source, /conversations\.discardedBody/);
  assert.match(source, /conversation\.starred \? t\(locale, "conversations\.unstar"\) : t\(locale, "conversations\.star"\)/);
  // red-proof: moving delete outside canPatch lets locked/discarded rows mutate
  // and makes this contract guard fail; swapping the visible star labels makes
  // the action announce the opposite of what it will do.
});

test("conversation rows are compact, day-grouped, and only attribute safe sources", async () => {
  // RETAINED-SOURCE-ASSERTION: safe-source allowlisting and host-selected CSS rules span branches beyond fixtures.
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
  // RETAINED-SOURCE-ASSERTION: shared-primitive adoption and deterministic appearance wiring are structural reuse facts.
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
  // RETAINED-SOURCE-ASSERTION: inherited CSS token declarations are not observable through jsdom layout/style resolution.
  const styles = await read("src/production/conversations.css");
  const backLink = styles.match(/\.conversation-back\s*\{([\s\S]*?)\}/)?.[1] ?? "";
  assert.match(backLink, /color:\s*var\(--content-primary\)/);
  assert.match(backLink, /text-decoration:\s*none/);
  // red-proof: removing either declaration restores the browser-blue,
  // underlined link that diverges from the native Ink surface.
});

test("production chrome preserves QA context while clearing fixture selection", async () => {
  // RETAINED-SOURCE-ASSERTION: URL parameter preservation/removal is shared navigation wiring across every route.
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

test("desktop glass chrome keeps host-selected layout without changing mobile navigation", async () => {
  // RETAINED-SOURCE-ASSERTION: platform CSS selectors and the absence of viewport branching are stylesheet structure.
  const styles = await read("src/production/styles.css");
  assert.match(styles, /grid-template-rows: var\(--desktop-nav-height\) var\(--desktop-panel-gap\) minmax\(0, 1fr\)/);
  assert.match(styles, /data-native-glass="true"/);
  assert.match(styles, /\.memory-card-header \{ order: 2;/);
  assert.match(styles, /\.memory-content \{ order: 1;/);
  assert.match(styles, /html\[data-platform="mobile"\] \.production-nav \.nav-mobile/);
  // STRUCTURAL CSS ASSERTION: jsdom cannot evaluate the host-selected grid and
  // ordering rules. The chrome hierarchy itself renders in memories-rendering.
});

test("memory cards keep locked and provenance behavior honest", async () => {
  // RETAINED-SOURCE-ASSERTION: forbidden raw provenance/backend text and mutation wiring span all conditional branches.
  const source = await read("src/production/MemoriesProduction.tsx");
  assert.match(source, /presentMemoryContent\(memory\.content\)/);
  assert.match(source, /locked\.body/);
  assert.match(source, /await store\.discardDeadLetter\(view\.opId\)/);
  assert.match(source, /memory\.locked \? \(/);
  assert.match(source, /store\.patch\(memory\.id, \{ visibility: targetVisibility \}\)/);
  assert.match(source, /store\.delete\(memory\.id\)/);
  const lockedBranch = source.match(/\{memory\.locked \? \(([\s\S]*?)\) : editing/)?.[1] ?? "";
  assert.doesNotMatch(lockedBranch, /store\.patch\(memory\.id, \{ content/);
  assert.doesNotMatch(source, /provenance-prefix/);
  assert.match(source, /<p className="memory-content">\{visibleText\}<\/p>/);
  assert.doesNotMatch(source, /failure\.detail|letter\.summary|view\.summary/);
  assert.doesNotMatch(source, /setReview/);
  assert.doesNotMatch(source, /memories\.(accept|reject)/);
  assert.doesNotMatch(source, /t\("en"/);
  // red-proof: rendering failure.detail or the provenance prefix in the body
  // would expose backend/debug text or duplicate the source label.
});

test("fixture matrix covers the truthful production states", async () => {
  // RETAINED-SOURCE-ASSERTION: the fixture-state catalog and fixed-clock declaration are structural QA inventory.
  const source = await read("src/production/memory-fixtures.ts");
  for (const state of ["loading", "empty", "unavailable", "saved-failed", "queued", "sending", "retrying", "needs-auth", "dead", "locked", "long"]) {
    assert.match(source, new RegExp(`\\"${state}\\"`));
  }
  assert.match(source, /FIXED_NOW = Date\.UTC/);
  // red-proof: replacing fixed fixture time with Date.now() makes screenshot
  // evidence drift between runs and invalidates visual comparisons.
});

test("i18n hardcoded-copy guard walks nested JSX text and expressions", async () => {
  // RETAINED-SOURCE-ASSERTION: this test intentionally verifies the static checker's AST coverage, not UI behavior.
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
  // RETAINED-SOURCE-ASSERTION: ID boundary parsing and platform-selector CSS are construction-time constraints.
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
