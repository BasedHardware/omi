#!/usr/bin/env node
/**
 * Enforces hard rule 15: a shared wire must be tested against its REAL shape.
 *
 * WHY THIS SCRIPT EXISTS. In one night, three separate defects had the same
 * shape and none of them could be caught by either side's test suite:
 *
 *   - a backend with 448 green tests that had never served a single request,
 *     because the modules were only ever referenced by their own unit tests;
 *   - a bridge that reported itself active while serving zero domain requests;
 *   - an entitlement UI built against a reserved `/listen` frame that no server
 *     emits, while the server emitted a different frame nobody consumed.
 *
 * Each half was individually correct and individually green. What was missing
 * in all three was the same thing: nothing consumed the OTHER side's real wire
 * shape. A test that hand-authors the counterpart's payload is testing its
 * author's memory of the wire, which is precisely the thing that was wrong.
 *
 * So the rule is structural rather than cultural: for every declared wire seam,
 * (1) a shared corpus of record must cover every frame the schema declares, and
 * (2) at least one test must actually READ that corpus. A convention would be
 * forgotten by the next agent at 4am; a check script is not.
 *
 * WHAT THIS CANNOT DO. It cannot prove a test asserts anything useful about
 * what it read — that is what rule 14's red-proofs are for. It proves the
 * weaker, mechanical thing that was missing in all three defects: the real
 * shape is present, and something loads it.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname;
const failures = [];

const read = (rel) => readFileSync(join(ROOT, rel), "utf8");
const readJson = (rel) => JSON.parse(read(rel));

/**
 * The seam registry. Adding a wire that two components speak means adding a row
 * here — that is the point of the ratchet, and it is deliberately a small,
 * boring edit so there is no excuse to skip it.
 */
const WIRE_SEAMS = [
  {
    name: "listen-protocol",
    schemaOfRecord: "contracts/wire/listen/listen-protocol.schema.json",
    corpus: "packages/wire-listen/fixtures/corpus.json",
    /** Every frame the schema says a server can put on the wire. */
    declaredFrames(schema) {
      const frames = [];
      for (const [defName, def] of Object.entries(schema.$defs ?? {})) {
        if (!def || typeof def !== "object") continue;
        if (def["x-omi-role"] !== "server-event") continue;
        const type = def["x-omi-event-type"] ?? def.properties?.type?.const;
        if (typeof type !== "string") continue;
        // A frame declared but not emitted is still covered: the reserved
        // entitlement frame is exactly the case that burned us, and "nobody
        // emits it yet" is what made it invisible.
        frames.push({ defName, type, emitted: def["x-omi-emitted"] === true });
      }
      return frames;
    },
    /** Every frame type the shared corpus actually contains. */
    corpusFrames(corpus) {
      const types = new Set();
      const visit = (json) => {
        if (Array.isArray(json)) return; // transcript batches carry no type
        if (!json || typeof json !== "object") return;
        if (typeof json.type === "string") types.add(json.type);
      };
      for (const scenario of corpus.scenarios ?? []) {
        for (const frame of scenario.frames ?? []) visit(frame.json);
      }
      return types;
    },
    /**
     * Tests that must READ the corpus. Listed explicitly rather than globbed so
     * that deleting the last consumer is a visible edit to this file.
     */
    consumers: [
      "packages/testkit/src/test/listen-conformance.test.ts",
      "packages/testkit/src/test/listen-entitlement-equivalence.test.ts",
    ],
    /** How a consumer proves it read the real thing. */
    consumptionEvidence: ["fixtures/corpus.json"],
  },
  {
    name: "ratified-memory-read",
    // The ratified package IS the schema of record; its manifest names the corpora.
    schemaOfRecord: "contracts/ratified/fixtures/manifest.json",
    corpus: "contracts/ratified/fixtures/manifest.json",
    declaredFrames(manifest) {
      return (manifest.files ?? []).map((f) => ({ defName: f, type: f, emitted: true }));
    },
    corpusFrames(manifest) {
      return new Set(manifest.files ?? []);
    },
    consumers: ["packages/testkit/src/test/platform-memories-adapter.test.ts"],
    // The loader, not the raw path: these corpora are read through testkit's
    // shared loader so both ends resolve the same files.
    consumptionEvidence: ["readRatifiedCorpus", "readRatifiedFixtureManifest"],
  },
  {
    /**
     * The client-facing WRITE wire — `POST /v1/{domain}/ops`, ratified by
     * COORD-write-path-rulings (B1/B2/B4/B6).
     *
     * A NEW SHARED WIRE MEANS A NEW ROW. This one exists because the two write
     * spikes explicitly did not satisfy rule 15: they copied the client's op
     * shape into their own test files instead of consuming a corpus of record,
     * and their own memo says the first real landing must add the registry row
     * and corpus. This is that row.
     *
     * SCHEMA OF RECORD vs MODULE. `write-ops-outcomes.json` enumerates every
     * outcome the wire can answer with. It could drift from `src/write/ops.ts`
     * and become a second source of truth, so the ratified package's own test
     * ("the write-ops schema of record matches the module's own tables")
     * asserts they are equal. Three links, each checked somewhere different:
     * module <-> schema (that test), schema <-> corpus (here), corpus <-> both
     * sides (the consumers below, plus the platform's).
     *
     * THE SERVER-SIDE CONSUMER IS NOT LISTED HERE, and that is deliberate. It
     * is `platform/contract-tests/ratified-contracts.test.ts`, in a sibling
     * repository. Reaching across `../../platform/` from this script would
     * make `pnpm verify` in a core-only checkout fail on a missing sibling,
     * which is a worse defect than the one it would catch. The platform's own
     * L0 step runs that file, and it reads these bytes out of the INSTALLED
     * tarball — a stronger consumption than a path this script could check.
     */
    name: "ratified-write-ops",
    schemaOfRecord: "contracts/ratified/fixtures/write-ops-outcomes.json",
    corpus: "contracts/ratified/fixtures/write-ops-conformance.json",
    /** Every outcome the schema says this route can answer with. */
    declaredFrames(schema) {
      return (schema.outcomes ?? []).map((row) => ({
        defName: row.outcome,
        type: row.outcome,
        // Every outcome is reachable the day the route lands. `emitted` exists
        // for the listen protocol's reserved-frame case and has no analogue
        // here; a write outcome nobody can produce would be a contract defect,
        // not a reservation.
        emitted: true,
      }));
    },
    /** Every outcome the shared corpus actually exercises. */
    corpusFrames(corpus) {
      const types = new Set();
      for (const row of corpus ?? []) {
        if (typeof row?.wireOutcome === "string") types.add(row.wireOutcome);
      }
      return types;
    },
    consumers: ["packages/testkit/src/test/write-ops-conformance.test.ts"],
    consumptionEvidence: ["readRatifiedCorpus", "readRatifiedWriteOpsSchema"],
  },
  {
    /**
     * The client-facing tasks READ wire — `GET /v1/tasks`, ratified by
     * `DAVID-tasks-read-epoch-and-ci` D1 (opaque ids, cursor pagination,
     * completeness envelope) and D2 (all thirteen fields).
     *
     * A NEW SHARED WIRE MEANS A NEW ROW, and this one is a wire two components
     * genuinely speak: `packages/adapters-platform/src/tasks.ts` on the client
     * and the platform service's tasks read route on the server. The memories
     * seam above is the precedent for why this cannot be left to each side's
     * own suite — the two doors agreed on every node-level assertion while
     * serving one record under two different public ids.
     *
     * COVERAGE IS CHECKED AGAINST BOTH TABLES the schema of record declares:
     * `cases` (what the wire can answer) and `refusalLaws` (what it must
     * refuse). A read wire's refusals are half its contract — "this page is
     * complete" is only meaningful because a lagging one is rejected — so a
     * schema listing only the happy cases would leave the expensive half of
     * the shape to each side's imagination, which is the whole of rule 15.
     */
    name: "ratified-tasks-read",
    schemaOfRecord: "contracts/ratified/fixtures/tasks-read-shape.json",
    corpus: "contracts/ratified/fixtures/tasks-read-conformance.json",
    declaredFrames(schema) {
      return [...(schema.cases ?? []), ...(schema.refusalLaws ?? [])].map((row) => ({
        defName: row.case,
        type: row.case,
        // Nothing here is a reservation. Every case is producible by any server
        // that serves this wire and every refusal is reachable by any client
        // that can send bytes, so `emitted` has no analogue — the listen
        // protocol's reserved-frame case is what that flag exists for.
        emitted: true,
      }));
    },
    corpusFrames(corpus) {
      const types = new Set();
      for (const row of corpus ?? []) {
        if (typeof row?.wireCase === "string") types.add(row.wireCase);
      }
      return types;
    },
    consumers: ["packages/testkit/src/test/platform-tasks-adapter.test.ts"],
    // The SERVER-side consumer is deliberately not listed, for the same reason
    // the write-ops seam does not list one: it lives in the sibling `platform`
    // repository, and reaching across `../../platform/` from this script would
    // make `pnpm verify` in a core-only checkout fail on a missing sibling —
    // a worse defect than the one it would catch. The platform's own L0 runs
    // its conformance file against these bytes out of the INSTALLED tarball,
    // which is a stronger consumption than a path this script could check.
    consumptionEvidence: ["readRatifiedCorpus", "readRatifiedTasksReadShape"],
  },
];

for (const seam of WIRE_SEAMS) {
  let schema;
  let corpus;
  try {
    schema = readJson(seam.schemaOfRecord);
    corpus = readJson(seam.corpus);
  } catch (err) {
    failures.push(`${seam.name}: cannot read schema/corpus — ${err.message}`);
    continue;
  }

  // ── 1. Coverage: every declared frame is in the shared corpus ─────────────
  const declared = seam.declaredFrames(schema);
  const covered = seam.corpusFrames(corpus);
  if (declared.length === 0) {
    failures.push(`${seam.name}: schema of record declares no frames — selector is probably stale`);
  }
  for (const frame of declared) {
    if (!covered.has(frame.type)) {
      failures.push(
        `${seam.name}: frame "${frame.type}" (${seam.defName ?? frame.defName}) is declared in ` +
          `${seam.schemaOfRecord} but absent from ${seam.corpus}. ` +
          `Add a corpus entry — a frame with no shared fixture is a frame each side will ` +
          `imagine differently (rule 15).`,
      );
    }
  }

  // ── 2. Consumption: something actually reads the corpus ───────────────────
  if (seam.consumers.length === 0) {
    failures.push(`${seam.name}: no consumer test declared — the corpus proves nothing unread (rule 15)`);
  }
  for (const consumer of seam.consumers) {
    let source;
    try {
      source = read(consumer);
    } catch {
      failures.push(`${seam.name}: declared consumer ${consumer} does not exist (rule 15)`);
      continue;
    }
    const reads = seam.consumptionEvidence.some((token) => source.includes(token));
    if (!reads) {
      failures.push(
        `${seam.name}: ${consumer} is declared a corpus consumer but never references ` +
          `${seam.consumptionEvidence.join(" or ")}. A test that hand-authors the wire shape ` +
          `tests its author's memory of it, not the wire (rule 15).`,
      );
    }
  }
}

if (failures.length) {
  console.error(`core/ wire conformance check FAILED (${failures.length}):`);
  for (const f of failures) console.error("  " + f);
  process.exit(1);
}
console.log(`core/ wire conformance check passed (${WIRE_SEAMS.length} seams).`);
