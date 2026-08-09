// LIFECYCLE: permanent
//
// THE L3 WRITE JOURNEY — create, applied, idempotent replay, forced stale
// epoch, dead letter — driven over real HTTP against a live write door, and
// judged by a producer-side counter and a consumer-side observation joined by
// run id.
//
// ── WHY THIS FILE IS SPLIT IN TWO ───────────────────────────────────────────
// `runWriteJourney` gathers FACTS: request bytes, response bytes, statuses, the
// server's own fence tallies. `judgeJourney` turns facts into a VERDICT. The
// split is the same one `run-report.mjs` makes and for the same measured
// reason: every false green in this program's history was a verdict, not a
// fact, and a verdict spread across a driver cannot be red-proofed. Here the
// verdict is a pure function of a plain object, so `write-journey.test.mjs` can
// mutate a fact and watch the assertion go red without booting anything.
//
// ── THE FOUR RULES THIS ENCODES ─────────────────────────────────────────────
//
// 1. **A dispatch-side number never appears in a verdict.** Nothing here counts
//    "requests sent". Every admission and every refusal in a verdict is read
//    back from the SERVER's `GET /v1/qa/control/stats?run=<id>`, on the same
//    process that serves the door — the counters that record each decision
//    where it is produced — and cross-checked against the bytes this driver
//    actually received. There are TWO of them, deliberately: the fence's epoch
//    decision and the route's outcome. A door that passed the fence and then
//    failed to apply moves one and not the other, which no single tally can
//    express. `servedCount=4 status=PASS` while the backend served zero is the
//    exact shape this refuses to be able to state.
//
// 2. **"Not 2xx" is not evidence of a fence.** A 404, a crash, a typo'd path and
//    a server refusing everything all satisfy it. So the stale-epoch refusal is
//    only ever asserted PAIRED with an admission obtained from the same live
//    process, on the same route, with the same body grammar, differing in one
//    field. Absence cannot produce that pair.
//
// 3. **Evidence is structured output, never scraped logs.** The journey returns
//    an object. Nothing in the verdict path reads a log line, and nothing that
//    writes a log line is allowed to be the only witness to a step.
//
// 4. **An assertion that cannot measure says so, and never says "pass".** Steps
//    whose door does not exist yet report `pending` with the missing door named.
//    `pending` is not a pass and can never be counted as one — and it is
//    UNREACHABLE once the door is registered, because `door_agreement` below
//    fails when the tree and the wire disagree about whether the door exists.
//    That is what keeps "excluded from the green gate until the doors exist"
//    from decaying into "excluded from the green gate".
//
// ── STAGING (charter R11) ───────────────────────────────────────────────────
// (a) fence harness door + seeded dev control state — no route needed;
// (b) the same journey rebound through the registered `POST /v1/tasks/ops`;
// (c) the same journey drained through the client op-sender.
// The stage is not a flag anyone passes. It is derived: the door's capability
// is read off the bytes it returns, the tree's claim is read out of the wire
// path registry, and a disagreement between the two is a failure.

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { REPO_PATHS } from "./provenance.mjs";

export const WRITE_JOURNEY_SCHEMA_VERSION = 1;

// The wire constants live in their own module because THIS one runs its CLI at
// import time, and a module that does something at import time must not be
// anybody's source of constants. Re-exported so existing importers do not have
// to learn a second path.
export { OPS_PATH, RUN_ID_HEADER, CONTROL_BASE } from "./write-journey-protocol.mjs";
import { OPS_PATH, RUN_ID_HEADER, CONTROL_BASE } from "./write-journey-protocol.mjs";

/**
 * The corpus this journey is judged against is the one the DOOR was built
 * against — platform's vendored tarball — not core's source copy. If the two
 * ever drift, the server is conformant to the bytes it vendored and to nothing
 * else, and measuring it against the source copy would report a defect in the
 * wrong repository. L0's `contract-tests/ratified-contracts.test.ts` is what
 * holds the two in agreement; this file deliberately does not duplicate it.
 */
export function readVendoredWriteOutcomes(platformRepo = REPO_PATHS.platform) {
  const path = join(
    platformRepo,
    "node_modules/@omi-core/ratified-contracts/fixtures/write-ops-outcomes.json",
  );
  let raw;
  try {
    raw = readFileSync(path, "utf8");
  } catch (error) {
    // Never a silent skip. A journey that cannot find its corpus has no arbiter
    // for the refusal bytes, and a step with no arbiter must stop the run, not
    // quietly grade itself.
    throw new Error(
      `the vendored write-ops corpus is unreadable at ${path} (${error.code ?? error.message}).`
      + ` Install platform's dependencies: cd ${platformRepo} && bun install`,
    );
  }
  const parsed = JSON.parse(raw);
  const byOutcome = new Map(parsed.outcomes.map((row) => [row.outcome, row]));
  return { path, writeIdPattern: parsed.writeIdPattern, byOutcome };
}

/**
 * Does the TREE claim `/v1/tasks/ops` is a registered wire path?
 *
 * This is the independent measurement that keeps `pending` honest. The door's
 * capability is read off the wire; this is read off the source. One says what
 * the running process does, the other says what the repository claims, and
 * `door_agreement` fails when they disagree — which is how "OPS landed the route
 * and STACK's journey quietly stayed in stage (a), still green" becomes
 * impossible rather than merely unlikely.
 */
export function readsWirePathRegistry(wirePath, platformRepo = REPO_PATHS.platform) {
  const path = join(platformRepo, "scripts/lint-import-graph.ts");
  const source = readFileSync(path, "utf8");
  const start = source.indexOf("const WIRE_PATH_REGISTRY");
  if (start === -1) throw new Error(`WIRE_PATH_REGISTRY not found in ${path}`);
  const end = source.indexOf("\n];", start);
  if (end === -1) throw new Error(`WIRE_PATH_REGISTRY is unterminated in ${path}`);
  const body = source.slice(start, end);
  return { path, registered: body.includes(`wirePath: ${JSON.stringify(wirePath)}`) };
}

/**
 * B1: the write id is MINTED from caller entropy and journaled with the op —
 * never derived from its content and never re-minted at send time, because a
 * send-time mint produces a different id on every replay and the server's
 * dedupe registry then never recognises the retry.
 */
export function mintWriteId(randomBytes = null) {
  const bytes = randomBytes ?? crypto.getRandomValues(new Uint8Array(32));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

const textOf = async (response) => ({
  status: response.status,
  text: await response.text(),
  retryAfter: response.headers.get("retry-after"),
});

/**
 * What kind of door is this, according to the bytes it just returned?
 *
 * Read from the CREATE response rather than from a flag a caller passed in: a
 * flag describes what someone believed, and the whole point of this journey is
 * that belief and behaviour are measured separately.
 */
export function classifyDoor(createResponse) {
  let body = null;
  // A 404 gets its own name. "There is no write door in this process" and "the
  // door answered something I do not recognise" are different findings, and
  // the first one is what a tree without OPS's route looks like — the message
  // has to say so rather than sending someone to debug a parser.
  if (createResponse.status === 404) {
    return { capability: "absent", why: "answered 404 — this process serves no write door at all" };
  }
  try {
    body = JSON.parse(createResponse.text);
  } catch {
    return { capability: "unknown", why: "the create response is not JSON" };
  }
  if (body !== null && typeof body === "object" && "applied" in body) {
    return { capability: "applies", why: "its create response carries an `applied` block" };
  }
  if (body !== null && typeof body === "object" && body.fence === "admitted") {
    return {
      capability: "fence-only",
      why: "admitted through the fence and applied nothing (`{fence:\"admitted\"}`)",
    };
  }
  return { capability: "unknown", why: `unrecognised create response body: ${createResponse.text.slice(0, 120)}` };
}

/**
 * Drive the journey. Returns FACTS. Grades nothing.
 *
 * `buildEnvelope` is the shipped client adapter (`buildWriteOpEnvelope`) — the
 * envelope on the wire is the one production would send, not a re-typed copy.
 * Passing it in rather than importing it keeps this module loadable without the
 * built dist, which is what lets the verdict tests run in L1.
 */
export async function runWriteJourney(options) {
  const {
    doorUrl,
    controlUrl,
    token,
    runId,
    activeEpoch,
    buildEnvelope,
    fetchImpl = fetch,
    platformRepo = REPO_PATHS.platform,
    // ── RED-PROOF LEVERS ────────────────────────────────────────────────────
    // Both exist to make the LIVE journey go red on demand
    // (`red-proof-write-journey.sh`), and neither can make it go green: skipping
    // the seed leaves the fence with nothing to admit, and an unstale "stale"
    // epoch removes the refusal the verdict requires. A lever that can only
    // subtract evidence is not an escape hatch, which is why these are
    // parameters rather than something a person does by hand once.
    skipSeed = false,
    staleEpoch = activeEpoch - 1,
  } = options;
  const otherRunId = `${runId}-interleaved`;
  const silentRunId = `${runId}-never-sent`;

  // ── THE DEV CONTROL PLANE IS ON THE PROCESS THAT SERVES THE DOOR ──────────
  // `/v1/qa/control/*`, registered by `apps/service/routes/qa-control.ts` on
  // the same app that answers `/v1/tasks/ops`. A counter in a sidecar is the
  // evidence shape that proved nothing in wave 9 — `servedCount=4 status=PASS`
  // while the backend served zero, both numbers accurate. The producer-side
  // tallies are read from the process that produced them or they are not
  // arbiters.
  //
  // The mutating routes require the bearer, and they OVERWRITE the
  // observation's `account_id` with the authenticated principal's: a QA surface
  // that let a caller name the account whose control state it seeds would be
  // ADR-012 §4's "possession of an identifier as evidence". So `accountId`
  // below is what the door told us its principal is, never what we asked for.
  const control = async (path, body) => {
    const response = await fetchImpl(`${controlUrl}${path}`, {
      method: body === undefined ? "GET" : "POST",
      headers: {
        "content-type": "application/json",
        ...(token === undefined || token === null ? {} : { authorization: `Bearer ${token}` }),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    if (!response.ok) throw new Error(`control ${path} -> ${response.status} ${await response.text()}`);
    return response.json();
  };

  const observation = (overrides) => ({
    account_id: options.accountId,
    control_revision: 1,
    account_generation: "legacy",
    account_epoch: null,
    lifecycle_state: "active",
    deletion_epoch: null,
    ...overrides,
  });

  // ── S0. Dev control seeding — HARNESS (charter R3) ────────────────────────
  // Nothing in `platform` mints control state by design: legacy is the
  // authority, no publisher exists, and fail-closed `control_state_absent` is
  // the correct production posture. This drives the control-plane surface the
  // fence harness already exposes to its own test, for DEV ACCOUNTS ONLY, so
  // the fence has something to admit against. The production publisher is
  // untouched and this is not a step toward one.
  const seed = {
    harness: true,
    ruling: "R3 — dev control seeding is harness and stays harness",
    accountId: options.accountId,
    activeEpoch,
    skipped: skipSeed === true,
    steps: [],
  };
  if (!skipSeed) {
    seed.steps.push({ name: "reset", response: await control(`${CONTROL_BASE}/reset`, {}) });
    // ADR-010 §1's forward activation order, driven through the registered app.
    for (const [name, obs] of [
      ["observe:legacy", observation({})],
      ["observe:migrating", observation({ control_revision: 2, account_generation: "migrating" })],
      ["observe:new", observation({ control_revision: 3, account_generation: "new", account_epoch: activeEpoch })],
    ]) {
      seed.steps.push({ name, response: await control(`${CONTROL_BASE}/observe`, obs) });
    }
    seed.steps.push({
      name: "activate",
      response: await control(`${CONTROL_BASE}/activate`, { epoch: activeEpoch, at_control_revision: 3 }),
    });
  } else {
    await control(`${CONTROL_BASE}/reset`, {});
  }

  const sendOp = async ({ writeId, op, epoch, runIdOverride }) => {
    const built = buildEnvelope({ domain: "tasks", writeId, op }, epoch);
    if (!built.ok) {
      // The shipped adapter refusing to build is a real outcome and a real
      // finding — it is recorded, never worked around by hand-rolling JSON.
      return { envelopeBuild: built, request: null, response: null };
    }
    const response = await fetchImpl(`${doorUrl}${built.path}`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${token}`,
        [RUN_ID_HEADER]: runIdOverride ?? runId,
      },
      body: JSON.stringify(built.envelope),
    });
    return {
      envelopeBuild: { ok: true, path: built.path },
      request: { path: built.path, body: JSON.stringify(built.envelope), writeId, epoch },
      response: await textOf(response),
    };
  };

  const recordId = `task-journey-${runId}`;
  const createWriteId = mintWriteId();
  const createOp = { op: "create", record_id: recordId, content: { title: "pick up oat milk", done: false } };

  // ── S1. create ───────────────────────────────────────────────────────────
  const create = await sendOp({ writeId: createWriteId, op: createOp, epoch: activeEpoch });
  // ── S2/S3. idempotent replay — the BYTE-IDENTICAL envelope, same write id ─
  const replay = await sendOp({ writeId: createWriteId, op: createOp, epoch: activeEpoch });
  // ── S4. forced stale epoch ───────────────────────────────────────────────
  const staleWriteId = mintWriteId();
  const stale = await sendOp({
    writeId: staleWriteId,
    op: { op: "patch", record_id: recordId, patch: { done: true } },
    epoch: staleEpoch,
  });
  // Interleaved traffic under a DIFFERENT run id. A counter that only kept
  // totals would agree with the wrong answer without this.
  const interleaved = await sendOp({
    writeId: mintWriteId(),
    op: { op: "patch", record_id: recordId, patch: { done: true } },
    epoch: staleEpoch,
    runIdOverride: otherRunId,
  });

  // TWO producer-side counters, not one, and they are independent: the fence
  // records the epoch decision, `writeOps` records the outcome the route
  // returned. A route that admitted through the fence and then failed to apply
  // moves one and not the other, which no single tally can express.
  const tallyFor = async (id) => {
    const stats = await control(`${CONTROL_BASE}/stats?run=${encodeURIComponent(id)}`);
    return { fence: stats.fence ?? null, writeOps: stats.writeOps ?? null };
  };

  /**
   * THE CONSUMER-SIDE OBSERVATION OF THE APPLY, from a different endpoint over
   * the same store. The door's own `applied` block is the door talking about
   * itself; this is the record being there afterwards. It carries record ids
   * and revisions and no user content, so it is not a read door.
   */
  const observedRecords = async () => {
    try {
      const body = await control(`${CONTROL_BASE}/tasks`);
      return body.records ?? null;
    } catch (error) {
      // `null` means "could not observe", never an empty list — "the store has
      // no such record" and "we could not ask" are different findings and
      // collapsing them into `[]` would report a working apply as broken.
      return { unobservable: error.message };
    }
  };

  return {
    schema: WRITE_JOURNEY_SCHEMA_VERSION,
    runId,
    door: { url: doorUrl, opsPath: OPS_PATH, ...classifyDoor(create.response ?? { text: "" }) },
    tree: readsWirePathRegistry(OPS_PATH, platformRepo),
    corpusPath: readVendoredWriteOutcomes(platformRepo).path,
    control: { url: controlUrl, seed },
    epoch: { active: activeEpoch, stale: staleEpoch },
    recordId,
    steps: { create, replay, stale, interleaved },
    // The PRODUCER side, read back from the server that made the decisions.
    producer: {
      thisRun: await tallyFor(runId),
      interleavedRun: await tallyFor(otherRunId),
      // The control probe. Without it, a counter hard-coded to return the same
      // tally for every run id would satisfy every assertion above.
      neverSentRun: await tallyFor(silentRunId),
    },
    // Read LAST, after the refused stale patch: the record must still carry the
    // create's revision, which is what proves the refusal happened before the
    // apply rather than after it.
    store: { records: await observedRecords() },
  };
}

const CORPUS_BODY = (corpus, outcome) => corpus.byOutcome.get(outcome)?.body ?? null;
const CORPUS_STATUS = (corpus, outcome) => corpus.byOutcome.get(outcome)?.status ?? null;

const pass = (detail) => ({ result: "pass", detail });
const fail = (detail) => ({ result: "fail", detail });
const pending = (detail) => ({ result: "pending", detail });

/**
 * The assertion registry. A row, not an `if` — same reason
 * `run-report.mjs` and `check-wire-conformance.mjs` use tables: a table can be
 * read and audited, and scattered conditionals cannot.
 *
 * `classify` is the shipped client classifier (`classifyWriteOpsResponse`),
 * injected so the verdict tests can run without the built dist. The dead-letter
 * assertion is only meaningful because it is the PRODUCTION classifier reading
 * the REAL refusal bytes — a re-typed copy of the taxonomy would agree with
 * itself no matter what the server sent.
 */
export const JOURNEY_ASSERTIONS = [
  {
    name: "door_agreement",
    claim: "the door this journey drove and the door the repository claims exists are the same door",
    measuredBy: "wire: the capability read off the live door's own create response",
    corroboratedBy: "tree: whether /v1/tasks/ops has a WIRE_PATH_REGISTRY row in platform",
    evaluate: (j) => {
      const { capability, why } = j.door;
      if (capability === "unknown") return fail(`the door's create response is unreadable — ${why}`);
      if (capability === "absent") {
        return fail(
          `no write door at ${j.door.url}: it ${why}.`
          + ` ${j.tree.path} says registered=${j.tree.registered}.`
          + " The retired fence harness is gone (R5), so there is no second door to fall back to —"
          + " this journey has measured nothing about the write path.",
        );
      }
      if (j.tree.registered && capability !== "applies") {
        return fail(
          `${j.tree.path} registers ${j.door.opsPath}, but the live door at ${j.door.url} ${why}.`
          + " The journey is measuring the stage-(a) harness while the real route exists:"
          + " repoint it (STACK stage b) rather than reading this as a pass.",
        );
      }
      if (!j.tree.registered && capability === "applies") {
        return fail(
          `the door at ${j.door.url} applies writes for ${j.door.opsPath}, which no WIRE_PATH_REGISTRY`
          + " row claims. A door serving a wire path off the registry is rule 16/17's defect class.",
        );
      }
      return pass(`${capability} — ${why}; registry says registered=${j.tree.registered}`);
    },
  },
  {
    name: "control_seeded",
    claim: "the dev account's control state was observed and activated, so the fence has something to admit against",
    measuredBy: "control plane: each observe/activate response's own accepted/activated flag",
    corroboratedBy: "wire: the create below was admitted rather than denied control_state_absent",
    evaluate: (j) => {
      // Zero steps is a FAILURE, not a vacuous pass. `[].every(...)` is true,
      // and an assertion that reports "nothing was refused" for a seeding that
      // never ran is the same shape as an assertion that opts out when it
      // cannot measure — it converts "we did not do it" into "we checked".
      if (j.control.seed.steps.length === 0) {
        return fail("no control seeding was performed at all — the fence has nothing to admit against, so any admission below came from somewhere else");
      }
      const refused = j.control.seed.steps.filter(
        (s) => s.response?.accepted === false || s.response?.activated === false,
      );
      if (refused.length > 0) {
        return fail(`control seeding refused: ${refused.map((s) => `${s.name}=${JSON.stringify(s.response)}`).join("; ")}`);
      }
      return pass(`seeded ${j.control.seed.steps.length} control step(s) for ${j.control.seed.accountId} at epoch ${j.epoch.active} (HARNESS — R3)`);
    },
  },
  {
    name: "create_admitted",
    claim: "a create op authored at the active epoch reached the fence and was admitted",
    measuredBy: "server: the fence's own admitted count for this run id",
    corroboratedBy: "wire: the number of 2xx responses this driver actually received on the same run id",
    evaluate: (j) => {
      const observed = j.steps.create.response;
      if (observed === null) return fail(`the shipped adapter refused to build the create envelope: ${JSON.stringify(j.steps.create.envelopeBuild)}`);
      const { fence, writeOps } = j.producer.thisRun;
      if (fence === null) {
        return fail(
          `the server reports NO fence decision at all for run ${j.runId} (tally is null, not zero)`
          + ` — the run id join is broken, so nothing this journey observed is attributable`,
        );
      }
      if (observed.status !== 200 && observed.status !== 202) {
        return fail(`the create was refused: ${observed.status} ${observed.text}`);
      }
      // EQUALITY, not a threshold. `admitted > 0` is satisfied by a counter that
      // increments on request entry, which is the dispatch-side number STATE.md
      // forbids from a verdict; only the two sides agreeing on HOW MANY can tell
      // a decision counter from an arrival counter.
      const driverAdmissions = [j.steps.create.response, j.steps.replay.response]
        .filter((r) => r !== null && (r.status === 200 || r.status === 202)).length;
      if (fence.admitted !== driverAdmissions) {
        return fail(
          `the driver received ${driverAdmissions} admitted response(s) on run ${j.runId} but the server`
          + ` counted ${fence.admitted} fence admission(s) — the two arbiters disagree`,
        );
      }
      // The fence admitting and the ROUTE accepting are different events, and a
      // door that passed the fence and then failed to apply moves only the
      // first. Where the route keeps its own outcome counter, both must agree.
      if (writeOps !== null) {
        const accepted = writeOps.outcomes.accepted + writeOps.outcomes.accepted_idempotent;
        if (accepted !== driverAdmissions) {
          return fail(
            `the fence admitted ${fence.admitted} and the driver saw ${driverAdmissions} 2xx, but the route's own`
            + ` outcome counter recorded ${accepted} accepted — admitted through the fence is not the same event as applied`,
          );
        }
      }
      return pass(`server counted fence admitted=${fence.admitted}${writeOps === null ? "" : `, route accepted=${writeOps.outcomes.accepted}+${writeOps.outcomes.accepted_idempotent} idempotent`} for run ${j.runId}; driver received exactly ${driverAdmissions} (create ${observed.status}, replay ${j.steps.replay.response?.status})`);
    },
  },
  {
    name: "server_applied_observation",
    claim: "the create the door said it applied is actually in the store afterwards, at the revision the door named",
    measuredBy: "wire: the door's own `applied` block (record_id + revision)",
    corroboratedBy: "store: GET /v1/qa/control/tasks — a DIFFERENT endpoint over the same store, read after the run",
    evaluate: (j) => {
      if (j.door.capability !== "applies") {
        return pending(
          `the door at ${j.door.url} ${j.door.why}. Applying is the write route's job and it has not landed`
          + " (no WIRE_PATH_REGISTRY row for /v1/tasks/ops); a placeholder apply in this harness would be a"
          + " second implementation of the thing that matters most. STACK stage (b) lands this.",
        );
      }
      const applied = JSON.parse(j.steps.create.response.text).applied ?? null;
      if (applied === null || typeof applied.record_id !== "string") {
        return fail(`the door returned an applied block with no record_id: ${j.steps.create.response.text}`);
      }
      if (applied.record_id !== j.recordId) {
        return fail(`the door applied to ${applied.record_id}, but the op named ${j.recordId}`);
      }
      // THE SECOND MEASUREMENT. Reading only the door's own response is one
      // side of one question: a route that answers `{applied:…}` from the
      // request it was handed, having written nothing, satisfies it perfectly.
      const records = j.store?.records ?? null;
      if (records === null || !Array.isArray(records)) {
        return fail(`the store could not be observed (${JSON.stringify(records)}) — the door's claim to have applied has no second measurement`);
      }
      const found = records.find((r) => r.record_id === applied.record_id) ?? null;
      if (found === null) {
        return fail(
          `the door reported applying ${applied.record_id} and the store does not contain it`
          + ` (it holds ${records.length} record(s): ${records.map((r) => r.record_id).join(", ") || "none"})`,
        );
      }
      if (found.revision !== applied.revision) {
        return fail(
          `the door reported revision ${String(applied.revision).slice(0, 12)}… and the store holds`
          + ` ${String(found.revision).slice(0, 12)}… — read AFTER the stale patch was refused, so either the`
          + " refusal applied anyway or the door's answer was never the record's state",
        );
      }
      return pass(`door applied ${applied.record_id}@${String(applied.revision).slice(0, 12)}…; the store independently reports the same revision after the refused patch`);
    },
  },
  {
    name: "idempotent_replay",
    claim: "replaying the byte-identical envelope under the same journaled write_id is a SUCCESS, not a conflict",
    measuredBy: "wire: the replay response's `idempotent` flag and status",
    corroboratedBy: "server: the route's own outcome counter for this run (accepted_idempotent), plus the vendored corpus row (B1)",
    evaluate: (j, { corpus }) => {
      if (j.door.capability !== "applies") {
        return pending(
          `the door at ${j.door.url} has no write_id registry — ${j.door.why}.`
          + " B1's idempotent replay is OPS's registry landing; STACK stage (b) rebinds this step to it.",
        );
      }
      const first = j.steps.create.response;
      const second = j.steps.replay.response;
      if (j.steps.create.request.body !== j.steps.replay.request.body) {
        return fail("the replay did not send byte-identical bytes — this step proves nothing about the registry");
      }
      const expectedStatus = CORPUS_STATUS(corpus, "accepted_idempotent");
      if (second.status !== expectedStatus) {
        return fail(`replay answered ${second.status}; the vendored corpus ratifies ${expectedStatus} for accepted_idempotent`);
      }
      const body = JSON.parse(second.text);
      if (body.idempotent !== true) {
        return fail(`replay answered idempotent=${JSON.stringify(body.idempotent)} — a replayed write_id that reports a fresh apply means the registry did not recognise it, and the op applied twice`);
      }
      if (JSON.parse(first.text).idempotent !== false) {
        return fail(`the FIRST send already reported idempotent=true — the registry is answering from a row this journey did not create`);
      }
      const writeOps = j.producer.thisRun.writeOps;
      if (writeOps !== null) {
        // The response saying `idempotent:true` and the SERVER having recorded
        // an idempotent outcome are two different claims. A route that sets the
        // flag from the request while recording a fresh apply moves only one.
        if (writeOps.outcomes.accepted_idempotent !== 1 || writeOps.outcomes.accepted !== 1) {
          return fail(
            `the driver saw one fresh apply and one idempotent replay, but the route recorded`
            + ` accepted=${writeOps.outcomes.accepted} accepted_idempotent=${writeOps.outcomes.accepted_idempotent}`
            + ` — the flag on the wire and the outcome the server recorded disagree`,
          );
        }
      }
      return pass(`first send idempotent=false, replay idempotent=true, same write_id ${j.steps.create.request.writeId.slice(0, 12)}…; server recorded accepted=1 accepted_idempotent=1`);
    },
  },
  {
    name: "stale_epoch_refused",
    claim: "an op authored at a superseded epoch is refused as stale_epoch specifically — not merely refused",
    measuredBy: "server: fence tally refused.stale_epoch for this run id",
    corroboratedBy: "wire: the 409 bytes received, PAIRED with the admitted create from the same process and route",
    evaluate: (j, { corpus }) => {
      const observed = j.steps.stale.response;
      if (observed === null) return fail(`the shipped adapter refused to build the stale envelope: ${JSON.stringify(j.steps.stale.envelopeBuild)}`);
      const admitted = j.steps.create.response;
      // THE PAIR. "Not 2xx" is satisfied by a 404, a crash, a typo'd path and a
      // server refusing everything. An admission from the same process, same
      // route and same body grammar, differing only in `account_epoch`, is not.
      if (admitted.status !== 200 && admitted.status !== 202) {
        return fail(`the paired admission did not happen (create -> ${admitted.status}), so this refusal is indistinguishable from the door being broken`);
      }
      const expectedStatus = CORPUS_STATUS(corpus, "stale_epoch");
      if (observed.status !== expectedStatus) {
        return fail(`stale op answered ${observed.status}; the vendored corpus ratifies ${expectedStatus}`);
      }
      const { fence, writeOps } = j.producer.thisRun;
      if (fence === null) return fail(`no fence decision recorded for run ${j.runId} — the join is broken`);
      if (fence.refused.stale_epoch !== 1) {
        return fail(`the driver received one stale_epoch refusal but the fence counted ${fence.refused.stale_epoch} for this run — the two arbiters disagree`);
      }
      if (writeOps !== null && writeOps.outcomes.stale_epoch !== 1) {
        return fail(`the fence refused one stale op but the route recorded ${writeOps.outcomes.stale_epoch} stale_epoch outcome(s) — the refusal did not reach the wire as the class the fence decided`);
      }
      return pass(`server counted stale_epoch=1 on both the fence and the route's outcome counter for run ${j.runId}; driver received ${observed.status}, paired with a ${admitted.status} admission differing only in account_epoch`);
    },
  },
  {
    name: "refusal_bytes_are_corpus_exact",
    claim: "the stale-epoch refusal is byte-identical to the vendored contract's ratified body, and leaks nothing",
    measuredBy: "wire: the exact response text",
    corroboratedBy: "corpus: platform's vendored write-ops-outcomes.json stale_epoch row",
    evaluate: (j, { corpus }) => {
      const observed = j.steps.stale.response;
      const expected = CORPUS_BODY(corpus, "stale_epoch");
      if (expected === null) return fail("the vendored corpus has no stale_epoch row — there is no arbiter for these bytes");
      if (observed.text !== expected) {
        return fail(`refusal bytes differ from the vendored corpus.\n    wire:   ${observed.text}\n    corpus: ${expected}`);
      }
      // ADR-012 §4: the refusal must not make account state probeable. W1: the
      // active epoch is never returned on a refusal surface.
      for (const secret of [String(j.epoch.active), j.control.seed.accountId, "request_epoch_behind"]) {
        if (observed.text.includes(secret)) return fail(`the refusal body leaks ${JSON.stringify(secret)}`);
      }
      return pass(`byte-identical to the vendored stale_epoch row, and leaks neither the active epoch nor the account id`);
    },
  },
  {
    name: "dead_letter_disposition",
    claim: "the refused op is preserved server-side as a straggler AND the shipped client would dead-letter it as stale_epoch — never as conflict",
    measuredBy: "server: fence tally preservedEnvelopes for this run id",
    corroboratedBy: "client: the shipped classifyWriteOpsResponse run over the REAL refusal bytes",
    evaluate: (j, { classify }) => {
      const { fence, writeOps } = j.producer.thisRun;
      if (fence === null) return fail(`no fence decision recorded for run ${j.runId} — the join is broken`);
      if (writeOps !== null && writeOps.preservedEnvelopes !== fence.preservedEnvelopes) {
        return fail(`the fence preserved ${fence.preservedEnvelopes} envelope(s) and the route recorded ${writeOps.preservedEnvelopes} — the straggler table and the fence disagree about the same refusal`);
      }
      if (fence.preservedEnvelopes !== 1) {
        return fail(
          `the server preserved ${fence.preservedEnvelopes} envelope(s) for this run's single stale refusal.`
          + " `preserve_envelope` is what makes the user's edit recoverable; a straggler that is refused"
          + " and not preserved is a silently lost edit.",
        );
      }
      const classified = classify(
        { status: j.steps.stale.response.status, text: j.steps.stale.response.text },
        "l3-write-journey",
      );
      if (classified === null) return fail("the shipped client read the refusal as a success");
      if (classified.kind !== "permanent" || classified.reason !== "stale_epoch") {
        return fail(
          `the shipped client classified the refusal as ${JSON.stringify(classified)}.`
          + " B2 rules out `conflict` by name: telling a person their saved edit conflicted, when the"
          + " server refused an op authored in a superseded generation, is a false report about their content.",
        );
      }
      return pass(`server preserved ${fence.preservedEnvelopes} envelope (fence and route agree); shipped client classified the same bytes as permanent/stale_epoch`);
    },
  },
  {
    name: "join_is_by_run_id",
    claim: "the producer-side counter is joined to THIS run and is not a total that would agree with any answer",
    measuredBy: "server: fence tally for a run id that sent nothing — must be null, not an all-zero tally",
    corroboratedBy: "server: the interleaved run's own tally, which must hold its traffic and not this run's",
    evaluate: (j) => {
      if (j.producer.neverSentRun.fence !== null || j.producer.neverSentRun.writeOps !== null) {
        return fail(
          `a run id that sent nothing has tally ${JSON.stringify(j.producer.neverSentRun)}.`
          + " `null` is what distinguishes 'the fence refused N writes for this run' from"
          + " 'this counter reports N for everything'.",
        );
      }
      const other = j.producer.interleavedRun.fence;
      if (other === null) return fail("the interleaved run sent an op and has no tally — the join dropped it");
      if (other.refused.stale_epoch !== 1) {
        return fail(`the interleaved run sent one stale op and the server counted ${other.refused.stale_epoch}`);
      }
      const mine = j.producer.thisRun.fence;
      if (mine.refused.stale_epoch !== 1) {
        return fail(`this run's tally absorbed the interleaved run's traffic (stale_epoch=${mine.refused.stale_epoch}, expected 1)`);
      }
      return pass("unsent run id -> null; interleaved traffic stayed in its own run's tally");
    },
  },
];

/**
 * Judge the facts. Pure: no I/O, no clock, no network.
 *
 * `pending` is a first-class result and is never a pass. A journey with any
 * pending step returns `partial`, which callers must not treat as green — see
 * `run-report.mjs`, where the journey's pending steps are reported and the
 * failing ones are what gate.
 */
export function judgeJourney(journey, { corpus, classify }) {
  const assertions = JOURNEY_ASSERTIONS.map((a) => {
    let outcome;
    try {
      outcome = a.evaluate(journey, { corpus, classify });
    } catch (error) {
      // A verdict that throws is a verdict that did not happen. Reporting it as
      // a failure rather than letting it escape is what keeps one malformed
      // response from erasing the other eight assertions' results.
      outcome = fail(`the assertion could not be evaluated: ${error.message}`);
    }
    return {
      name: a.name,
      claim: a.claim,
      measuredBy: a.measuredBy,
      corroboratedBy: a.corroboratedBy,
      singleMeasurement: a.corroboratedBy === null,
      result: outcome.result,
      detail: outcome.detail,
    };
  });
  const failed = assertions.filter((a) => a.result === "fail");
  const pendingSteps = assertions.filter((a) => a.result === "pending");
  return {
    schema: WRITE_JOURNEY_SCHEMA_VERSION,
    runId: journey.runId,
    door: journey.door,
    stage: journey.door.capability === "applies" ? "b" : "a",
    assertions,
    pending: pendingSteps.map((a) => a.name),
    result: failed.length > 0 ? "fail" : (pendingSteps.length > 0 ? "partial" : "pass"),
  };
}

export function formatJourney(verdict) {
  const out = [`  write journey  run=${verdict.runId}  stage=${verdict.stage}  door=${verdict.door.url}`];
  for (const a of verdict.assertions) {
    const mark = { pass: "PASS", fail: "FAIL", pending: "PEND" }[a.result];
    out.push(`  [${mark}] ${a.name}`);
    out.push(`         claim:  ${a.claim}`);
    out.push(`         by:     ${a.measuredBy}`);
    out.push(`         vs:     ${a.corroboratedBy ?? "(nothing — SINGLE MEASUREMENT, treat as weaker evidence)"}`);
    out.push(`         ${a.result === "pass" ? "saw" : "why"}:    ${a.detail}`);
  }
  out.push(`  journey result: ${verdict.result.toUpperCase()}`);
  if (!verdict.gating) {
    out.push(`  NOT GATING L3 — ${verdict.gatingNote}`);
  }
  return out.join("\n");
}

/**
 * ── WHY THE STAGE-(a) JOURNEY DOES NOT REDDEN L3, AND HOW THAT RETIRES ──────
 *
 * Charter R11: stage (a) is "excluded from the green gate until the doors
 * exist". The reason is `overnight-runs.md` §4 — one lane's harness must not
 * idle six lanes on a shared trunk at 3am — and it is NOT "this evidence is
 * weak". The stage-(a) assertions are real, they are red-proofed, and this
 * lane gates on them: `dev-stack.sh --write-journey` exits nonzero on a journey
 * failure, and so does this file's own CLI.
 *
 * What makes the exclusion safe rather than rot: it is derived, not declared.
 * The moment `/v1/tasks/ops` gets its WIRE_PATH_REGISTRY row, `gating` flips to
 * true on its own and the journey gates L3 with no edit to this file, no flag,
 * and nobody having to remember. Until then every run prints the condition.
 */
export function gatingOf(journey) {
  return {
    gating: journey.tree.registered === true,
    gatingNote: journey.tree.registered
      ? null
      : `stage (a): ${journey.door.opsPath} has no WIRE_PATH_REGISTRY row in ${journey.tree.path},`
        + " so this journey drives the fence harness rather than the product's write door."
        + " It gates automatically the moment that row lands (charter R11).",
  };
}

if (process.argv[1] && process.argv[1].endsWith("write-journey.mjs")) {
  const argv = process.argv.slice(2);
  const flag = (name, fallback) => (argv.indexOf(name) === -1 ? fallback : argv[argv.indexOf(name) + 1]);

  /**
   * `--print-door-plan` — which door should the launcher point this journey at?
   *
   * dev-stack.sh asks THIS module rather than grepping the registry itself.
   * Two implementations of one fact is the defect class this whole program is
   * about; the launcher must not be able to disagree with the verdict about
   * which stage the night is in.
   */
  if (argv.includes("--print-door-plan")) {
    const tree = readsWirePathRegistry(OPS_PATH, flag("--platform-repo", REPO_PATHS.platform));
    process.stdout.write(`${JSON.stringify({ ...tree, opsPath: OPS_PATH, stage: tree.registered ? "b" : "a" })}\n`);
    process.exit(0);
  }

  /** Render a verdict file a previous run already wrote. Judges nothing. */
  if (argv.includes("--format")) {
    const verdict = JSON.parse(readFileSync(flag("--format"), "utf8"));
    process.stdout.write(`${formatJourney(verdict)}\n`);
    process.exit(0);
  }

  // The shipped client adapter, imported from the BUILT dist by path — the exact
  // module the surfaces call, not a re-implementation. Dynamic and confined to
  // the CLI path so the verdict tests can import this module in L1, where no
  // dist is guaranteed to exist.
  const adapters = await import(
    new URL("../../core/packages/adapters-platform/dist/index.js", import.meta.url).href
  );

  const platformRepo = flag("--platform-repo", REPO_PATHS.platform);
  const activeEpoch = Number(flag("--epoch", "7"));
  const journey = await runWriteJourney({
    doorUrl: flag("--door"),
    controlUrl: flag("--control", flag("--door")),
    token: flag("--token"),
    accountId: flag("--account"),
    runId: flag("--run", `journey-${Date.now()}`),
    activeEpoch,
    buildEnvelope: adapters.buildWriteOpEnvelope,
    platformRepo,
    // Red-proof levers. See runWriteJourney: both can only subtract evidence.
    skipSeed: argv.includes("--red-proof-skip-seed"),
    staleEpoch: Number(flag("--stale-epoch", String(activeEpoch - 1))),
  });
  const verdict = {
    ...judgeJourney(journey, {
      corpus: readVendoredWriteOutcomes(platformRepo),
      classify: adapters.classifyWriteOpsResponse,
    }),
    ...gatingOf(journey),
    facts: journey,
  };

  /**
   * ── STAGE (c): the client OUTBOX draining through the same door ───────────
   *
   * Runs whenever the door applies — i.e. whenever there is something to drain
   * into. It is NOT conditional on anything a caller passes, and it is not
   * skipped when it fails to load: a stage that quietly opts out is the
   * "converts we-do-not-know into we-checked" shape, so a failure to import the
   * client modules is reported as a failing assertion with the reason.
   */
  if (journey.door.capability === "applies") {
    const outboxModule = await import(new URL("./write-journey-outbox.mjs", import.meta.url).href);
    let outbox = null;
    try {
      const sync = await import(new URL("../../core/packages/sync/dist/index.js", import.meta.url).href);
      const fakes = await import(new URL("../../core/packages/testkit/dist/fakes.js", import.meta.url).href);
      const facts = await outboxModule.runOutboxDrain({
        doorUrl: flag("--door"),
        token: flag("--token"),
        accountId: flag("--account"),
        runId: verdict.runId,
        activeEpoch,
        deps: {
          MemoryStore: fakes.MemoryStore,
          ManualEnv: fakes.ManualEnv,
          Outbox: sync.Outbox,
          platformTasksTransport: adapters.platformTasksTransport,
          createPlatformWriteStamps: adapters.createPlatformWriteStamps,
          createDevAccountEpochProvider: adapters.createDevAccountEpochProvider,
        },
      });
      // Producer-side, read back AFTER the drain, for the drain's OWN run ids.
      const statsFor = async (id) => {
        const r = await fetch(`${flag("--control", flag("--door"))}${CONTROL_BASE}/stats?run=${encodeURIComponent(id)}`);
        const body = await r.json();
        return { fence: body.fence ?? null, writeOps: body.writeOps ?? null };
      };
      const producer = { drain: await statsFor(facts.drainRunId), stale: await statsFor(facts.staleRunId) };
      outbox = { ...outboxModule.judgeOutbox(facts, { producer }), producer, facts };
    } catch (error) {
      outbox = {
        result: "fail",
        assertions: [{
          name: "outbox_stage_ran", claim: "stage (c) executed at all",
          measuredBy: "the driver", corroboratedBy: null, singleMeasurement: true,
          result: "fail",
          detail: `stage (c) could not run: ${error.message}. A stage that cannot run is not a stage that passed.`,
        }],
      };
    }
    verdict.outbox = outbox;
    verdict.assertions = [...verdict.assertions, ...outbox.assertions];
    verdict.stage = outbox.result === "pass" ? "c" : verdict.stage;
    if (outbox.result === "fail") verdict.result = "fail";
  }
  const json = `${JSON.stringify(verdict, null, 2)}\n`;
  const out = flag("--out");
  if (out) (await import("node:fs")).writeFileSync(out, json);
  process.stdout.write(argv.includes("--json") ? json : `${formatJourney(verdict)}\n`);
  process.exit(verdict.result === "fail" ? 1 : 0);
}
