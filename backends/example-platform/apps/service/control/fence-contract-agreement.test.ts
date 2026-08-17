/**
 * CROSS-MODULE AGREEMENT: the ratified write contract and the account-control
 * fence must have exactly ONE HTTP spelling between them.
 *
 * It lives here rather than in `contract-tests/` because `tsconfig.contracts.json`
 * compiles that directory under a stricter project than the service is written
 * for, and pulling another module into a stricter gate is a way of failing a
 * lane for a rule it never agreed to.
 */

import { describe, expect, test } from "bun:test";

import {
  CONTROL_UNAVAILABLE_RETRY_AFTER_SECONDS,
  WRITE_AVAILABILITY,
  WRITE_REFUSALS,
  readWriteAvailabilitySignal,
  readWriteRefusalOutcome,
} from "@omi-core/ratified-contracts/write/ops";

import { WRITE_FENCE_REFUSALS } from "./fence-http";

const SCHEMA_OF_RECORD = new URL(
  "../../../node_modules/@omi-core/ratified-contracts/fixtures/write-ops-outcomes.json",
  import.meta.url,
);

// ── THE FENCE SEAM: one HTTP spelling, checked, not assumed ─────────────────
//
// `apps/service/control/fence-http.ts` says outright that it is not a contract,
// and that "the fence lane provides one [HTTP spelling], the write lane binds it
// into the ratified contract, and neither invents a second". This describes an
// obligation, and an obligation nobody executes is how rule 16's defect happened
// in the first place: two modules independently constructing one concept and
// disagreeing one layer below where anyone was looking.
//
// So the agreement is a test. If either side edits a status or a byte of a body,
// this fails — in the repository that has both in scope, which is the only place
// that can see it.
describe("ratified write contract and the account-control fence agree on one wire", () => {
  test("the four ADR-010 refusal outcomes are byte-identical on both sides", () => {
    // red-proof: change any status or body byte in WRITE_FENCE_REFUSALS and this
    // goes red. APPLIED AND OBSERVED RED (stale_epoch 409 -> 400).
    for (const outcome of ["authentication", "authorization", "entitlement", "stale_epoch"] as const) {
      const fence = WRITE_FENCE_REFUSALS[outcome];
      const contract = WRITE_REFUSALS[outcome];
      expect<number>(fence.status).toBe(contract.status);
      expect<string>(fence.body).toBe(contract.body);
      // And the contract can read the fence's own bytes back as the right class.
      expect(readWriteRefusalOutcome(fence.status, fence.body)).toBe(outcome);
    }
  });

  test("the fifth value is ratified as an AVAILABILITY signal, not a fifth refusal", async () => {
    // COORD-fable-rulings-wave2 W1, and its binding condition. The contract now
    // carries `control_unavailable` — the escalation is ruled — but it carries it
    // in its own table with its own reader, because ADR-010 §3's four outcomes
    // are statements about the CALLER'S AUTHORITY and this one is not. Keeping
    // "refusals are four distinct outcomes" true of the authorization
    // composition is what makes this an extension of the ADR David accepted
    // rather than a delegate's signature amending it.
    //
    // red-proof: make the refusal reader answer control_unavailable and this
    // goes red. APPLIED AND OBSERVED RED.
    const fence = WRITE_FENCE_REFUSALS.control_unavailable;
    const contract = WRITE_AVAILABILITY.control_unavailable;
    expect<number>(fence.status).toBe(contract.status);
    expect<string>(fence.body).toBe(contract.body);
    expect(readWriteAvailabilitySignal(fence.status, fence.body)).toBe("control_unavailable");
    expect(readWriteRefusalOutcome(fence.status, fence.body)).toBeNull();

    // The conditions the ruling made load-bearing. Weakening any of these is a
    // §8 guard-weakening diff, so they are asserted from both sides.
    expect<number>(contract.retryAfterSeconds).toBe(CONTROL_UNAVAILABLE_RETRY_AFTER_SECONDS);
    expect(fence.headers["retry-after"]).toBe(String(CONTROL_UNAVAILABLE_RETRY_AFTER_SECONDS));
    expect(contract.body).not.toContain("epoch");

    const schema = await Bun.file(SCHEMA_OF_RECORD).json() as { outcomes: { outcome: string; kind: string }[] };
    const row = schema.outcomes.find((entry) => entry.outcome === "control_unavailable");
    expect(row?.kind).toBe("availability");
  });

  test("no fence outcome collapses onto another", () => {
    // ADR-010 §3's "four distinct outcomes, not one", asserted over the bytes.
    // The most damaging collapse is control_unavailable onto stale_epoch: the
    // client dead-letters stale_epoch as non-retryable (ruling B2), so that
    // mapping would turn every migration window into a permanent lost edit.
    const bodies: string[] = Object.values(WRITE_FENCE_REFUSALS).map((refusal) => refusal.body);
    expect(new Set(bodies).size).toBe(bodies.length);
    expect(WRITE_FENCE_REFUSALS.control_unavailable.body).not.toBe(WRITE_FENCE_REFUSALS.stale_epoch.body);
  });
});
