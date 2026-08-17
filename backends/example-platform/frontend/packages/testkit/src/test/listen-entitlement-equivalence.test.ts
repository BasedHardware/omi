/**
 * BOTH WIRE SHAPES PRODUCE THE SAME INTERNAL STATE.
 *
 * This is the test the coordinator's ruling exists for
 * (decisions/COORD-entitlement-frame-collision.md). `freemium_threshold_reached`
 * is what a server emits today; `entitlement` is reserved for the rewritten
 * wire and emitted by nobody. FE-SURFACES built its entitlement UI against the
 * reserved one — so against a real server that UI never fired, and neither
 * side's suite could catch it, because each end was individually correct.
 *
 * THE FRAMES BELOW ARE READ OUT OF THE SHARED CORPUS, NOT WRITTEN HERE.
 * That is the whole point and it is not a stylistic preference. A test that
 * hand-authors the other component's payload is testing its author's memory of
 * the wire, which is exactly the thing that was already wrong. The corpus
 * (`packages/wire-listen/fixtures/corpus.json`) is the shape of record, it is
 * what the protocol conformance suite drives, and `check-wire-conformance.mjs`
 * fails the build if a declared frame is missing from it or if this file stops
 * importing it.
 *
 * Hermetic: fixtures + ManualEnv, no network, no clock.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { FallbackRecord, FallbackSink } from "@omi-core/contracts";
import { ManualEnv } from "../fakes.js";
import {
  createListenCaptureStreamPort,
  type ListenEntitlementSnapshot,
  type SchemaDocument,
} from "@omi-core/wire-listen";

const HERE = dirname(fileURLToPath(import.meta.url));
const CORE_ROOT = join(HERE, "../../../..");
const schema = JSON.parse(
  readFileSync(join(CORE_ROOT, "contracts/wire/listen/listen-protocol.schema.json"), "utf8"),
) as SchemaDocument;

/** The shape-of-record corpus, read from source. Never a local copy. */
const CORPUS = JSON.parse(
  readFileSync(join(CORE_ROOT, "packages/wire-listen/fixtures/corpus.json"), "utf8"),
) as {
  scenarios: readonly {
    name: string;
    // Not every frame is a JSON object: heartbeats are raw text and transcript
    // batches are arrays. Narrowing happens in corpusFrame, not here.
    frames: readonly { json?: unknown; text?: string; expect?: string }[];
  }[];
};

/** Pull the first frame of a given `type` out of the corpus, or fail loudly. */
function corpusFrame(eventType: string): Record<string, unknown> {
  for (const scenario of CORPUS.scenarios) {
    for (const frame of scenario.frames) {
      const json = frame.json;
      if (typeof json !== "object" || json === null || Array.isArray(json)) continue;
      const record = json as Record<string, unknown>;
      if (record["type"] === eventType) return record;
    }
  }
  throw new Error(
    `no ${eventType} frame in the shared corpus — either the corpus lost coverage or the ` +
      `frame was renamed; check-wire-conformance.mjs should have caught this first`,
  );
}

class CollectingSink implements FallbackSink {
  readonly records: FallbackRecord[] = [];
  record(r: FallbackRecord): void {
    this.records.push(r);
  }
}

function openPort(generation: "legacy" | "platform") {
  const sink = new CollectingSink();
  const { port, ingest } = createListenCaptureStreamPort({
    schema,
    env: new ManualEnv(),
    sink,
    generation,
  });
  return { port, ingest, sink };
}

/** Drive one corpus frame through the port and return the normalised state. */
function stateFrom(
  generation: "legacy" | "platform",
  frame: Record<string, unknown>,
): { state: ListenEntitlementSnapshot | null; sink: CollectingSink } {
  const { port, ingest, sink } = openPort(generation);
  ingest.acceptTextFrame(JSON.stringify(frame));
  return { state: port.getEntitlementState(), sink };
}

test("the shared corpus still carries BOTH entitlement wire shapes", () => {
  // If this fails, every equivalence assertion below is vacuous. Asserting the
  // premise separately is what stops a corpus regression from reading as a pass.
  const entitlement = corpusFrame("entitlement");
  const freemium = corpusFrame("freemium_threshold_reached");
  assert.equal(entitlement["type"], "entitlement");
  assert.equal(freemium["type"], "freemium_threshold_reached");
  assert.ok("remaining_seconds" in freemium, "the legacy frame carries a countdown");
  assert.ok("state" in entitlement, "the reserved frame carries a state union");
});

test("BOTH wire shapes normalise to the same internal state for the exhausted case", () => {
  // red-proof: in listen_capture_stream.ts, delete the
  // `freemium_threshold_reached` branch of acceptTextFrame. The legacy frame
  // then produces `null` — a user at their limit whose UI never fires, which is
  // precisely the production bug this ruling was written to fix.
  // APPLIED 2026-08-08: observed
  //   AssertionError: the legacy wire must produce a state at all ... null !== object
  //
  // The two wires carry DIFFERENT information, so identical objects would be a
  // lie. What must agree is the pair of normalised decision fields — the only
  // two both wires can always answer, and therefore the only two a surface may
  // branch on without checking `source`.
  const exhaustedFreemium = { type: "freemium_threshold_reached", remaining_seconds: 0, action: "none" };
  const exhaustedEntitlement = {
    ...corpusFrame("entitlement"),
    state: "upgrade_required",
  };

  const legacy = stateFrom("legacy", exhaustedFreemium).state;
  const platform = stateFrom("platform", exhaustedEntitlement).state;

  assert.ok(legacy, "the legacy wire must produce a state at all");
  assert.ok(platform, "the platform wire must produce a state at all");

  assert.equal(legacy.status, "upgrade_required");
  assert.equal(platform.status, "upgrade_required");
  assert.equal(
    legacy.status,
    platform.status,
    "the two wires disagree about severity — a surface would render two different screens",
  );
  assert.equal(
    legacy.captureContinuing,
    platform.captureContinuing,
    "the two wires disagree about whether audio survives",
  );
  assert.equal(legacy.captureContinuing, false);
});

test("the paused-but-capturing case agrees across both wires", () => {
  // The other end of the range: credit is not exhausted, and capture continues.
  // red-proof: in listenEntitlementSnapshotFromFreemium, change
  // `captureContinuing: !exhausted` to `false`. The two wires then disagree and
  // the legacy surface silently stops showing a live transcript.
  // APPLIED 2026-08-08: observed  false !== true
  const approaching = { type: "freemium_threshold_reached", remaining_seconds: 180, action: "setup_on_device_stt" };
  const paused = { ...corpusFrame("entitlement"), state: "transcription_paused_capture_continuing" };

  const legacy = stateFrom("legacy", approaching).state;
  const platform = stateFrom("platform", paused).state;
  assert.ok(legacy && platform);
  assert.equal(legacy.captureContinuing, true);
  assert.equal(platform.captureContinuing, true);
  assert.equal(legacy.captureContinuing, platform.captureContinuing);
});

test("fields a wire does not carry are null, never a plausible default", () => {
  // red-proof: in listenEntitlementSnapshotFromFreemium, replace
  // `limit: { kind: "unknown" }` with `{ kind: "metered", amount: 3600, unit: "seconds" }`.
  // A surface would then show a user a ceiling the server never stated — the
  // same fabrication class as a synthesized memory carrying `locked: false`.
  // APPLIED 2026-08-08: observed  'metered' !== 'unknown'
  const legacy = stateFrom("legacy", corpusFrame("freemium_threshold_reached")).state;
  assert.ok(legacy);
  assert.equal(legacy.usage, null, "the legacy wire says nothing about consumption");
  assert.equal(legacy.limit.kind, "unknown", "and nothing about a ceiling — unknown, not unmetered");
  assert.equal(legacy.reason, null);
  assert.equal(legacy.upgradeTarget, null, "and does not say where to upgrade");
  assert.ok(legacy.remaining, "what it DOES carry is a countdown, and that is kept");

  const platform = stateFrom("platform", corpusFrame("entitlement")).state;
  assert.ok(platform);
  assert.equal(platform.remaining, null, "the reserved wire carries no countdown");
  assert.ok(platform.usage, "but it does carry usage");
  assert.notEqual(platform.limit.kind, "unknown", "and a real ceiling");
});

test("a frame from the other generation is ACCEPTED and REPORTED, never silently taken", () => {
  // red-proof: delete the `reportGenerationMismatch` call from the entitlement
  // branch. The state still arrives, so every other assertion in this file
  // still passes — only this one catches it. That is the point: silence is the
  // failure mode, and silence is invisible to a suite that only checks state.
  // APPLIED 2026-08-08: observed  AssertionError: a cross-generation frame must be reported ... 0 !== 1
  const crossed = stateFrom("legacy", corpusFrame("entitlement"));
  assert.ok(crossed.state, "the frame is still accepted — the user's limit is real either way");
  assert.equal(crossed.state.source, "entitlement");

  const mismatches = crossed.sink.records.filter(
    (r) => r.path === "listen.capture.entitlement-generation-mismatch",
  );
  assert.equal(mismatches.length, 1, "a cross-generation frame must be reported");
  assert.match(mismatches[0]!.detail ?? "", /legacy/);
  assert.match(mismatches[0]!.detail ?? "", /entitlement/);

  // And the matching case is NOT reported — a mismatch signal that fires always
  // is a mismatch signal nobody reads.
  const aligned = stateFrom("platform", corpusFrame("entitlement"));
  assert.equal(
    aligned.sink.records.filter((r) => r.path === "listen.capture.entitlement-generation-mismatch").length,
    0,
  );
});

test("each generation's own frame needs no mismatch report", () => {
  const legacy = stateFrom("legacy", corpusFrame("freemium_threshold_reached"));
  assert.ok(legacy.state);
  assert.equal(legacy.state.source, "freemium_threshold_reached");
  assert.equal(
    legacy.sink.records.filter((r) => r.path === "listen.capture.entitlement-generation-mismatch").length,
    0,
    "the legacy generation expects the freemium frame",
  );
});
