/**
 * TASKS RENDERING-PARITY HARNESS (R8, ratchet item 5's second half)
 * ===================================================================
 *
 * "The production tasks surface renders identically off either generation
 * over seeded-equivalent data" (R7/R8), satisfied at the seeded-parity venue
 * R7 names — never a real account, and the flip stays PARKED (R7):
 * `openTasks()` is untouched by this file, and nothing here calls it.
 *
 * WHAT WAS FOUND BEFORE THIS FILE, so the shape below isn't arbitrary:
 *
 *   - `PlatformTaskItem` and `Task` are FIELD-COMPLETE with each other — all
 *     thirteen fields, same names, same types, checked by reading both
 *     interfaces directly (`core/contracts/src/domain/{tasks,platform-tasks}.ts`).
 *     The one difference is `id`'s nominal TS type (`RecordId`, a branded
 *     string, vs a plain `string`) — erased at runtime, so mapping one to the
 *     other invents nothing and decides nothing.
 *   - `TasksProduction.tsx` (`core/packages/surfaces/src/production/`) has NO
 *     unit-test seam — it is a Vite/React bundle, no jsdom or
 *     `@testing-library` anywhere in this workspace. Its actual field usage
 *     was read directly rather than assumed: `id`, `description`, `dueAt`,
 *     `completed`, `indentLevel` are RENDERED (indent as a CSS class AND a
 *     keyboard-driven patch); `owner`/`source`/`provenance`/`createdAt`/
 *     `updatedAt`/`revision` are on the type but never read by this
 *     component. So "renders identically" is decided by five fields, not
 *     thirteen, and this file says so rather than silently narrowing scope.
 *
 * WHAT THIS FILE DOES, since it cannot render React: it derives the exact
 * DATA a render would need — grouping (today/tomorrow/later), sort order
 * within a group, and the five rendered per-task values — using functions
 * whose bodies are PINNED against `TasksProduction.tsx`'s own source text
 * below (`assertSourceStillMatches`), so a change to the real algorithm that
 * is not mirrored here fails LOUDLY rather than silently validating a stale
 * copy. This is the same discipline `tasks-production.test.mjs` already uses
 * for this exact file (regex-matching source, because there is nothing to
 * import) — extended here to comparing TWO generations' data through it,
 * which that file does not do.
 *
 * SEEDING, real on both sides:
 *   - platform: the REAL write door (`POST /v1/tasks/ops`) against the REAL
 *     registered app, booted via `platform/integration/control/live-service.ts`
 *     — reused from `tasks-wire-agreement.test.mjs` rather than a second boot
 *     script (rule 17's reasoning: a second door is the defect, not a
 *     convenience).
 *   - legacy: there is no legacy backend to boot in this program (it is the
 *     OLD production system). So legacy is seeded through a SCRIPTED
 *     `HttpClient` feeding the REAL legacy adapter function,
 *     `fetchTasks` (`@omi-core/adapters-legacy`) — never a hand-rolled
 *     `Task[]`. The scripted body is the real legacy WIRE SHAPE (snake_case,
 *     ISO-8601 timestamps, `action_items` envelope), read directly from
 *     `adapters-legacy/src/tasks.ts`'s own parser rather than guessed.
 *
 * NOT YET RUN BY L2, for the same reason `tasks-wire-agreement.test.mjs`
 * isn't: `integration/lanes.mjs` names its cross-side step by filename and is
 * STACK's file under the charter's churn-magnet table.
 * (`data/run-2026-08-09/blocked/READ-l2-does-not-run-the-tasks-cross-side-test.md`
 * already covers this same class of gap for the sibling file.)
 */

import { spawn } from "node:child_process";
import { once } from "node:events";
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import { after, before, describe, test } from "node:test";

const { fetchTasks } = await import(
  new URL("../../core/packages/adapters-legacy/dist/index.js", import.meta.url).href
);
const { fetchPlatformTaskPage } = await import(
  new URL("../../core/packages/adapters-platform/dist/index.js", import.meta.url).href
);
const { REPO_PATHS } = await import(new URL("../lib/provenance.mjs", import.meta.url).href);
const PLATFORM_REPO = REPO_PATHS.platform;
const BOOT_TIMEOUT_MS = 20_000;
const ACTIVE_EPOCH = 7;

const PRODUCTION_SOURCE_PATH = new URL(
  "../../core/packages/surfaces/src/production/TasksProduction.tsx",
  import.meta.url,
);

let child;
let baseUrl;
let TOKEN;

// ── The replica, pinned against the real source ──────────────────────────

/**
 * Every fragment here must be textually present in the real component.
 * red-proof: change any one of these strings and re-run — every one is
 * independently APPLIED AND OBSERVED RED (see the landing commit).
 */
function assertSourceStillMatches() {
  const source = readFileSync(PRODUCTION_SOURCE_PATH, "utf8");
  const mustContain = [
    // groupFor's exact day-boundary logic
    'if (task.dueAt === null) return "later";',
    "const tomorrow = calendarDay(now + 86_400_000);",
    // the sort comparator's exact precondition ordering
    "if (left.dueAt === null && right.dueAt !== null) return 1;",
    "if (left.dueAt !== null && right.dueAt === null) return -1;",
    // the indent clamp, verbatim
    "const indentLevel = Math.max(0, Math.min(3, task.indentLevel));",
    // the truncation threshold, verbatim
    "const isLong = task.description.length > 240;",
    'const visibleDescription = !expanded && isLong ? `${task.description.slice(0, 240)}…` : task.description;',
  ];
  const missing = mustContain.filter((fragment) => !source.includes(fragment));
  assert.deepEqual(
    missing, [],
    `TasksProduction.tsx no longer contains: ${JSON.stringify(missing)} — ` +
    `this file's replica has drifted from the real render algorithm and must be updated to match.`,
  );
}

function utcCalendarDay(timestamp) {
  return new Date(timestamp).toISOString().slice(0, 10);
}

/** Mirrors `groupFor` (`TasksProduction.tsx`), pinned above. */
function groupFor(task, now, calendarDay) {
  if (task.dueAt === null) return "later";
  const current = calendarDay(now);
  const due = calendarDay(task.dueAt);
  if (due === current) return "today";
  const tomorrow = calendarDay(now + 86_400_000);
  if (due === tomorrow) return "tomorrow";
  return "later";
}

/** Mirrors the sort comparator inside `TasksProduction`'s `grouped` memo, pinned above. */
function sortWithinGroup(tasks) {
  return [...tasks].sort((left, right) => {
    if (left.dueAt === null && right.dueAt !== null) return 1;
    if (left.dueAt !== null && right.dueAt === null) return -1;
    if (left.dueAt !== right.dueAt) return (left.dueAt ?? Number.MAX_SAFE_INTEGER) - (right.dueAt ?? Number.MAX_SAFE_INTEGER);
    return left.description < right.description ? -1 : left.description > right.description ? 1 : 0;
  });
}

/**
 * The five fields `TasksProduction.tsx` actually renders, derived exactly as
 * it derives them (`TaskCard`, pinned above) — everything the component turns
 * a `Task` into for display, EXCLUDING `id`'s literal value (a generation-
 * specific opaque key, asserted present but never compared byte-for-byte;
 * see the header) and the four fields the component never reads at all
 * (`owner`, `source`, `provenance`, `createdAt`, `updatedAt`, `revision`).
 */
function renderedFields(task) {
  const isLong = task.description.length > 240;
  return {
    hasId: typeof task.id === "string" && task.id.length > 0,
    visibleDescription: !isLong ? task.description : `${task.description.slice(0, 240)}…`,
    completed: task.completed,
    indentClass: `is-indent-${Math.max(0, Math.min(3, task.indentLevel))}`,
    dueDisplay: task.dueAt === null ? "no-due-date" : `due:${utcCalendarDay(task.dueAt)}`,
  };
}

/** The full "surface bytes" this harness claims: grouped, ordered, per-task rendered fields. */
function surfaceBytes(tasks, now) {
  const groups = { today: [], tomorrow: [], later: [] };
  for (const task of tasks) groups[groupFor(task, now, utcCalendarDay)].push(task);
  const result = {};
  for (const group of ["today", "tomorrow", "later"]) {
    result[group] = sortWithinGroup(groups[group]).map(renderedFields);
  }
  return result;
}

// ── Mechanical adapter: PlatformTaskItem -> Task-shaped. Invents nothing. ──
// Every field on the right already exists on `item` with the same name and
// type (verified against both interfaces directly); only `id`'s NOMINAL type
// changes, and `RecordId = string & { brand }` is erased at runtime.
function platformItemAsTaskShape(item) {
  return {
    id: item.id,
    description: item.description,
    completed: item.completed,
    completedAt: item.completedAt,
    dueAt: item.dueAt,
    owner: item.owner,
    source: item.source,
    provenance: item.provenance,
    sortOrder: item.sortOrder,
    indentLevel: item.indentLevel,
    createdAt: item.createdAt,
    updatedAt: item.updatedAt,
    revision: item.revision,
  };
}

// ── Seeded-equivalent content, one definition shared by both generations ───
const SEED_NOW = Date.UTC(2026, 7, 9, 12, 0, 0);
function seedContent(index) {
  return {
    description: `Rendering-parity task ${index}`,
    completed: index % 3 === 0,
    completedAt: index % 3 === 0 ? SEED_NOW - 3_600_000 : null,
    // index 0 -> today, 1 -> tomorrow, 2 -> later, repeating
    dueAt: index % 3 === 2 ? null : SEED_NOW + (index % 3) * 86_400_000,
    owner: null,
    source: "assistant",
    provenance: ["assistant:summarizer-v3"],
    sortOrder: index + 0.5,
    indentLevel: index % 4,
    createdAt: SEED_NOW - 7_200_000,
    updatedAt: SEED_NOW - 1_800_000,
  };
}
const SEED_COUNT = 6;

// ── Legacy side: scripted HttpClient, real adapter parse ───────────────────
function legacyWireRow(index, content) {
  return {
    id: `legacy-task-${index}`,
    description: content.description,
    completed: content.completed,
    completed_at: content.completedAt === null ? null : new Date(content.completedAt).toISOString(),
    due_at: content.dueAt === null ? null : new Date(content.dueAt).toISOString(),
    owner: content.owner,
    source: content.source,
    provenance: content.provenance,
    sort_order: content.sortOrder,
    indent_level: content.indentLevel,
    created_at: new Date(content.createdAt).toISOString(),
    updated_at: new Date(content.updatedAt).toISOString(),
  };
}

class ScriptedLegacyHttp {
  constructor(actionItems) { this.actionItems = actionItems; }
  async request(_method, _path) {
    return { status: 200, json: { action_items: this.actionItems }, text: JSON.stringify({ action_items: this.actionItems }) };
  }
}

// ── Platform side: real server, real write door, real client parse ─────────
function realHttpClient(base, token) {
  return {
    async request(method, path, body) {
      const response = await fetch(`${base}${path}`, {
        method,
        headers: {
          ...(token === null ? {} : { authorization: `Bearer ${token}` }),
          ...(body === undefined ? {} : { "content-type": "application/json" }),
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
      const text = await response.text();
      let json;
      try { json = JSON.parse(text); } catch { json = null; }
      return { status: response.status, json, text };
    },
  };
}

const post = async (path, body) => {
  const response = await fetch(`${baseUrl}${path}`, {
    method: "POST",
    headers: { authorization: `Bearer ${TOKEN}`, "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return { status: response.status, text: await response.text() };
};

const cutOver = async () => {
  const observation = (overrides) => ({
    control_revision: 1, account_generation: "legacy", account_epoch: null,
    lifecycle_state: "active", deletion_epoch: null, ...overrides,
  });
  await post("/v1/qa/control/observe", observation({}));
  await post("/v1/qa/control/observe", observation({ control_revision: 2, account_generation: "migrating" }));
  await post("/v1/qa/control/observe", observation({ control_revision: 3, account_generation: "new", account_epoch: ACTIVE_EPOCH }));
  const activated = await post("/v1/qa/control/activate", { epoch: ACTIVE_EPOCH, at_control_revision: 3 });
  assert.match(activated.text, /"activated":true/, `cut-over did not activate: ${activated.text}`);
};

const seedPlatform = async (count) => {
  await cutOver();
  for (let index = 0; index < count; index += 1) {
    const writeId = index.toString(16).padStart(64, "0");
    const applied = await post("/v1/tasks/ops", {
      write_id: writeId, account_epoch: ACTIVE_EPOCH, domain: "tasks",
      op: { op: "create", record_id: `parity-${index}`, content: seedContent(index) },
    });
    assert.equal(applied.status, 200, `platform seed ${index} was not applied: ${applied.text}`);
  }
};

before(async () => {
  // Identical boot to `tasks-wire-agreement.test.mjs`: readiness from the
  // CHILD's own announced port, never a pinned one.
  child = spawn("bun", ["run", "integration/control/live-service.ts"], {
    cwd: PLATFORM_REPO,
    env: { ...process.env, TZ: "UTC" },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stdout = "";
  let stderr = "";
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdout.on("data", (chunk) => { stdout += chunk; });
  child.stderr.on("data", (chunk) => { stderr += chunk; });

  const deadline = Date.now() + BOOT_TIMEOUT_MS;
  while (Date.now() < deadline) {
    for (const line of stdout.split("\n")) {
      if (!line.includes("live_service_listening")) continue;
      try {
        const event = JSON.parse(line);
        if (event.event === "live_service_listening" && typeof event.url === "string") {
          baseUrl = event.url;
          TOKEN = event.devToken;
        }
      } catch { /* partial line */ }
    }
    if (baseUrl !== undefined) return;
    if (child.exitCode !== null) {
      throw new Error(`backend exited before readiness (status ${child.exitCode})\n`
        + `stdout: ${stdout.trim() || "(empty)"}\nstderr: ${stderr.trim() || "(empty)"}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error(`backend never announced a listening port\nstderr: ${stderr.trim() || "(empty)"}`);
});

after(async () => {
  if (child && child.exitCode === null) {
    child.kill();
    await once(child, "exit");
  }
});

describe("the production tasks surface derives identical presentation off either generation", () => {
  test("the replica algorithm still matches TasksProduction.tsx's real source", () => {
    assertSourceStillMatches();
  });

  test("all thirteen fields survive both real adapters, over the same seeded content", async () => {
    await seedPlatform(SEED_COUNT);
    const platformHttp = realHttpClient(baseUrl, TOKEN);
    const platformOutcome = await fetchPlatformTaskPage(platformHttp, { limit: SEED_COUNT + 1 });
    assert.equal(platformOutcome.kind, "page", `platform read failed: ${JSON.stringify(platformOutcome)}`);
    assert.equal(platformOutcome.page.items.length, SEED_COUNT);

    const legacyRows = Array.from({ length: SEED_COUNT }, (_, index) => legacyWireRow(index, seedContent(index)));
    const legacyHttp = new ScriptedLegacyHttp(legacyRows);
    const legacyTasks = await fetchTasks(legacyHttp);
    assert.ok(legacyTasks, "the real legacy adapter could not parse the scripted wire rows");
    assert.equal(legacyTasks.length, SEED_COUNT);

    // Both real adapters produced real domain objects; neither is empty, and
    // both sides survived their own real parse path, not a fixture shortcut.
    for (const item of platformOutcome.page.items) {
      assert.deepEqual(
        Object.keys(item).sort(),
        ["completed", "completedAt", "createdAt", "description", "dueAt", "id",
          "indentLevel", "owner", "provenance", "revision", "sortOrder", "source", "updatedAt"],
      );
    }
    for (const task of legacyTasks) {
      assert.deepEqual(
        Object.keys(task).sort(),
        ["completed", "completedAt", "createdAt", "description", "dueAt", "id",
          "indentLevel", "owner", "provenance", "revision", "sortOrder", "source", "updatedAt"],
      );
    }
  });

  test("surface bytes agree, field by field, for the fields the surface actually renders", async () => {
    await post("/v1/qa/control/reset", {});
    await seedPlatform(SEED_COUNT);
    const platformHttp = realHttpClient(baseUrl, TOKEN);
    const platformOutcome = await fetchPlatformTaskPage(platformHttp, { limit: SEED_COUNT + 1 });
    assert.equal(platformOutcome.kind, "page");
    const platformAsTasks = platformOutcome.page.items.map(platformItemAsTaskShape);

    const legacyRows = Array.from({ length: SEED_COUNT }, (_, index) => legacyWireRow(index, seedContent(index)));
    const legacyTasks = await fetchTasks(new ScriptedLegacyHttp(legacyRows));

    const legacyBytes = surfaceBytes(legacyTasks, SEED_NOW);
    const platformBytes = surfaceBytes(platformAsTasks, SEED_NOW);

    // The claim, over EACH group, so a mismatch names its group rather than
    // dumping an undifferentiated diff.
    for (const group of ["today", "tomorrow", "later"]) {
      assert.deepEqual(
        platformBytes[group].map((row) => ({ ...row, hasId: undefined })),
        legacyBytes[group].map((row) => ({ ...row, hasId: undefined })),
        `group "${group}" diverges between generations for identical seeded content`,
      );
      // `id` is generation-specific by construction (opaque key, never
      // compared by value) — checked present on every row instead.
      assert.ok(platformBytes[group].every((row) => row.hasId), `platform group "${group}" has a row with no id`);
      assert.ok(legacyBytes[group].every((row) => row.hasId), `legacy group "${group}" has a row with no id`);
      assert.equal(platformBytes[group].length, legacyBytes[group].length, `group "${group}" has different counts`);
    }

    // And the claim actually exercised all three groups and every seeded row,
    // so an empty comparison cannot read as agreement.
    const totalRows = ["today", "tomorrow", "later"].reduce((sum, g) => sum + platformBytes[g].length, 0);
    assert.equal(totalRows, SEED_COUNT);
  });
});
