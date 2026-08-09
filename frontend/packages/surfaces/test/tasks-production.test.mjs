import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

test("task fixtures cover the truthful lifecycle and queue matrix", async () => {
  const source = await read("src/production/task-fixtures.ts");
  for (const state of ["loading", "empty", "unavailable", "saved-failed", "queued", "sending", "retrying", "needs-auth", "dead", "normal", "long", "operation-failed"]) {
    assert.match(source, new RegExp('"' + state + '"'));
  }
  assert.match(source, /FIXED_NOW = Date\.UTC/);
  assert.match(source, /fixtureStore\(state: FixtureState, now = FIXED_NOW\)/);
  assert.match(source, /parseRecordId/);
  assert.match(source, /completed:/);
  assert.match(source, /dueAt:/);
  assert.match(source, /provenance:/);
  assert.doesNotMatch(source, /Date\.now\(\)/);
  // red-proof: replacing the injected now with Date.now() makes group
  // boundaries and screenshots drift with the wall clock.
});

test("tasks derive UTC calendar groups and preserve no-due tasks in Later", async () => {
  const source = await read("src/production/TasksProduction.tsx");
  assert.match(source, /calendarDay\?:/);
  assert.match(source, /groupFor\(task, now, dayFormatter\)/);
  assert.match(source, /if \(task\.dueAt === null\) return "later"/);
  assert.match(source, /86_400_000/);
  assert.match(source, /type GroupKey = "today" \| "tomorrow" \| "later"/);
  assert.match(source, /tasks\.noDueDate/);
  assert.doesNotMatch(source, /new Date\(\)\.getDate/);
  // red-proof: replacing groupFor with a fixed bucket would put tomorrow and
  // unscheduled rows in Today and make the fixture matrix visually untestable.
});

test("task discovery filters the loaded snapshot without claiming backend search", async () => {
  const source = await read("src/production/TasksProduction.tsx");
  assert.match(source, /<ProductionSearchField/);
  assert.match(source, /tasks\.filterSavedPlaceholder/);
  assert.match(source, /task\.description\.toLocaleLowerCase\(locale\)\.includes\(needle\)/);
  assert.doesNotMatch(source, /store\.search|searchTasks|fetchSearch/);
  // red-proof: routing the field through a fabricated store.search capability
  // fails this test because the ratified task store only exposes list/create/patch/delete.
});

test("task actions stay within the task contract", async () => {
  const source = await read("src/production/TasksProduction.tsx");
  assert.match(source, /store\.create\(description, dueAt\)/);
  assert.match(source, /const patch: TaskPatch = \{\}/);
  assert.match(source, /patch\.description = description/);
  assert.match(source, /patch\.dueAt = dueAt/);
  assert.match(source, /store\.patch\(task\.id, patch\)/);
  assert.match(source, /store\.patch\(task\.id, \{ completed: !task\.completed \}/);
  assert.match(source, /store\.delete\(task\.id\)/);
  assert.match(source, /store\.discardDeadLetter\(view\.opId\)/);
  assert.doesNotMatch(source, /goal|priority|appName|backendGroup/i);
  // red-proof: adding a goal/priority/backend grouping branch would claim a
  // capability absent from the current task contract.
});

test("source and provenance are localized or suppressed, never leaked", async () => {
  const source = await read("src/production/TasksProduction.tsx");
  assert.doesNotMatch(source, /\{task\.source\}/);
  assert.doesNotMatch(source, /\{task\.provenance\}/);
  assert.doesNotMatch(source, /task\.source|task\.provenance|failure\.detail|letter\.summary/);
  // red-proof: rendering task.source or provenance directly would expose raw
  // backend values, including blank/unknown provenance, as product copy.
});

test("keyboard shortcuts mutate only a selected task and are input-safe", async () => {
  const source = await read("src/production/TasksProduction.tsx");
  assert.match(source, /event\.key\.toLowerCase\(\) === "n"/);
  assert.match(source, /event\.key\.toLowerCase\(\) === "d"/);
  assert.ok(source.includes('modifier && (event.key === "]" || event.key === "[")'));
  assert.match(source, /Math\.max\(0, Math\.min\(3, selectedTask\.indentLevel/);
  assert.match(source, /closest\("input, textarea, select/);
  assert.match(source, /select, button, a/);
  assert.match(source, /selectedTaskId/);
  // red-proof: removing input-safety would turn typing Meta/Control-N or Meta-[
  // inside the task editor into a destructive or structural mutation.
});

test("mutation failures stay localized and dead letters remain discardable", async () => {
  const source = await read("src/production/TasksProduction.tsx");
  const fixtures = await read("src/production/task-fixtures.ts");
  assert.match(source, /setOperationError\(translate\("lifecycle\.error"\)\)/);
  assert.match(source, /store\.discardDeadLetter\(view\.opId\)/);
  // The dead-letter row binding was renamed `letter` -> `view` when the panel
  // started routing through `deadLetterView`. Both spellings are banned here
  // now: a rename must not be able to defang this check a second time, which
  // is exactly what it did the first time — the patterns went vacuously green
  // against a panel that had simply stopped using the old identifier.
  assert.doesNotMatch(source, /letter\.failure|view\.failure|failure\.detail|letter\.summary|view\.summary/);
  assert.match(fixtures, /state === "operation-failed"/);
  assert.match(fixtures, /refreshFailuresRemaining/);
  assert.match(source, /return true/);
  assert.match(source, /current\.trim\(\) === description/);
  // red-proof: rendering a dead-letter backend detail or swallowing a failed
  // fixture operation would make terminal failures invisible to the user.
});

test("tasks use the shared production chrome and stable ready callback", async () => {
  const source = await read("src/production/TasksProduction.tsx");
  assert.match(source, /import "\.\/tasks\.css"/);
  assert.match(source, /className="production-shell tasks-production-shell"/);
  assert.match(source, /ProductionChrome locale=\{locale\} active="tasks" placement="top"/);
  assert.match(source, /ProductionChrome locale=\{locale\} active="tasks" placement="bottom"/);
  assert.match(source, /import "\.\/tasks\.css"/);
  assert.match(source, /className="production-shell tasks-production-shell"/);
  assert.match(source, /readyRef\.current/);
  assert.match(source, /parseDateInput/);
  assert.doesNotMatch(source, /Date\.parse\(/);
  // red-proof: removing readyRef permits StrictMode's second effect pass to
  // emit duplicate readiness, while Date.parse UTC would shift local dates.
  // Dropping the stylesheet or production-shell class leaves the route without
  // its responsive layout or shared bottom-navigation behavior.
});

test("all task UI copy is translator-backed and desktop/mobile affordances exist", async () => {
  const source = await read("src/production/TasksProduction.tsx");
  const styles = await read("src/production/tasks.css");
  assert.match(source, /translate: Translate/);
  assert.match(source, /tasks\.shortcuts/);
  assert.match(source, /tasks\.shortcutNew/);
  assert.match(source, /tasks\.shortcutDelete/);
  assert.match(source, /tasks\.shortcutIndent/);
  assert.match(source, /tasks\.shortcutOutdent/);
  assert.match(source, /tasks-mobile-fab/);
  assert.match(styles, /html\[data-platform="desktop"\]/);
  assert.match(styles, /html\[data-platform="mobile"\]/);
  assert.match(styles, /tasks-mobile-fab/);
  assert.match(styles, /task-card\.is-completed/);
  assert.match(styles, /task-card\.is-selected/);
  assert.match(source, /data-indent-level=\{indentLevel\}/);
  assert.match(styles, /task-card\.is-indent-3/);
  assert.match(source, /confirm\(translate\("tasks\.deleteConfirm"\)\)/);
  assert.doesNotMatch(styles, /#(?:[0-9a-f]{3,8})\b/i);
  assert.doesNotMatch(styles, /@media\s*\(/);
  // red-proof: a raw JSX sentence or purple literal would bypass locale and
  // semantic-token checks while still looking correct in one screenshot.
});

test("task polish keeps rows scannable and create, edit, and focus flows accessible", async () => {
  const source = await read("src/production/TasksProduction.tsx");
  const styles = await read("src/production/tasks.css");
  assert.match(source, /tasks-group-count/);
  assert.match(source, /grouped\[group\]\.length/);
  assert.match(source, /aria-expanded=\{createOpen\}/);
  assert.match(source, /requestAnimationFrame\(\(\) => draftRef\.current\?\.focus\(\)\)/);
  assert.match(source, /dateInputValue\(task\.dueAt\)/);
  assert.match(source, /tabIndex=\{0\}/);
  assert.match(source, /event\.key === "ArrowDown" \|\| event\.key === "ArrowUp"/);
  assert.match(source, /querySelectorAll<HTMLElement>\("\.task-card"\)/);
  assert.match(styles, /tasks-create\.is-open/);
  assert.match(styles, /task-check\[aria-pressed="true"\]/);
  assert.match(styles, /task-card:not\(\.is-selected\) \.task-actions/);
  assert.match(styles, /tasks-shortcuts \{ position: sticky/);
  // red-proof: always displaying the mobile composer and every row action
  // restores the screenshot's form-heavy layout and destroys scan density.
});
