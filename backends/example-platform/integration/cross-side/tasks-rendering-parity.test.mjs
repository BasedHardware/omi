/**
 * TASKS RENDERING HARNESS (was R8 parity; legacy generation retired)
 * ===================================================================
 *
 * After David's 2026-08-16 ruling retired the legacy generation, this file
 * no longer compares two generations. What remains:
 *
 *   - the replica of `TasksProduction.tsx`'s grouping/sort/indent/truncation
 *     is still pinned against the real source (`assertSourceStillMatches`)
 *   - the platform adapter is still exercised through the REAL write door
 *     (`POST /v1/tasks/ops`) and the REAL `fetchPlatformTaskPage` against a
 *     live local service
 *
 * COVERAGE LOST: R8 "the production tasks surface renders identically off
 * either generation over seeded-equivalent data". There is no second
 * generation to compare. The field-by-field cross-generation equality
 * assertion is gone with the legacy adapter.
 */

import { spawn } from "node:child_process";
import { once } from "node:events";
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import { after, before, describe, test } from "node:test";

const { fetchPlatformTaskPage } = await import(
  new URL("../../frontend/packages/adapters-platform/dist/index.js", import.meta.url).href
);
const { REPO_PATHS } = await import(new URL("../lib/provenance.mjs", import.meta.url).href);
const PLATFORM_REPO = REPO_PATHS.platform;
const BOOT_TIMEOUT_MS = 20_000;
const ACTIVE_EPOCH = 7;

const PRODUCTION_SOURCE_PATH = new URL(
  "../../frontend/packages/surfaces/src/production/TasksProduction.tsx",
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
    'if (task.dueAt === null) return "noDeadline";',
    "if (task.dueAt < now) return \"overdue\";",
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
  if (task.dueAt === null) return "noDeadline";
  if (task.dueAt < now) return "overdue";
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
  const groups = { overdue: [], today: [], tomorrow: [], later: [], noDeadline: [] };
  for (const task of tasks) groups[groupFor(task, now, utcCalendarDay)].push(task);
  const result = {};
  for (const group of ["overdue", "today", "tomorrow", "later", "noDeadline"]) {
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

// ── Seeded content for the platform write door ─────────────────────────────
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

describe("the production tasks surface derives presentation from the platform adapter", () => {
  test("the replica algorithm still matches TasksProduction.tsx's real source", () => {
    assertSourceStillMatches();
  });

  test("all thirteen fields survive the real platform adapter, over seeded content", async () => {
    await seedPlatform(SEED_COUNT);
    const platformHttp = realHttpClient(baseUrl, TOKEN);
    const platformOutcome = await fetchPlatformTaskPage(platformHttp, { limit: SEED_COUNT + 1 });
    assert.equal(platformOutcome.kind, "page", `platform read failed: ${JSON.stringify(platformOutcome)}`);
    assert.equal(platformOutcome.page.items.length, SEED_COUNT);

    for (const item of platformOutcome.page.items) {
      assert.deepEqual(
        Object.keys(item).sort(),
        ["completed", "completedAt", "createdAt", "description", "dueAt", "id",
          "indentLevel", "owner", "provenance", "revision", "sortOrder", "source", "updatedAt"],
      );
    }
  });

  test("surface bytes group every seeded row the way TasksProduction.tsx would", async () => {
    await post("/v1/qa/control/reset", {});
    await seedPlatform(SEED_COUNT);
    const platformHttp = realHttpClient(baseUrl, TOKEN);
    const platformOutcome = await fetchPlatformTaskPage(platformHttp, { limit: SEED_COUNT + 1 });
    assert.equal(platformOutcome.kind, "page");
    const platformAsTasks = platformOutcome.page.items.map(platformItemAsTaskShape);
    const platformBytes = surfaceBytes(platformAsTasks, SEED_NOW);

    for (const group of ["overdue", "today", "tomorrow", "later", "noDeadline"]) {
      assert.ok(platformBytes[group].every((row) => row.hasId), `platform group "${group}" has a row with no id`);
    }

    const totalRows = ["overdue", "today", "tomorrow", "later", "noDeadline"].reduce((sum, g) => sum + platformBytes[g].length, 0);
    assert.equal(totalRows, SEED_COUNT);
    assert.ok(platformBytes.today.length > 0, "seed must populate today so grouping is not vacuously empty");
  });
});
