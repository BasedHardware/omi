/**
 * THE REFERENCE HTTP BINDING FOR A FENCE REFUSAL.
 *
 * ── READ THIS BEFORE USING IT (WRITE lane, this means you) ───────────────────
 *
 * **This file is not a contract.** The write contract is landing in a different
 * lane under `COORD-contract-evolution-policy.md`, and the ratified surface today
 * is route shape only — ruling B4, `POST /v1/{domain}/ops` — plus ruling B2's
 * client-side dead-letter reason `stale_epoch`. Status codes and refusal bodies
 * for the write path are NOT ratified.
 *
 * What this file exists to prevent is the specific failure rule 16 was written
 * for: two modules independently binding one concept and disagreeing below the
 * layer anyone looks at. The fence's five outcomes need exactly one HTTP
 * spelling. So the fence lane provides one, the write lane binds it into the
 * ratified contract, and neither invents a second.
 *
 * The status/body choices restate the skeleton in `SPIKE-write-path-contract.md`
 * §5 — the same document fable read when signing B2 and B4 — rather than
 * introducing a third proposal:
 *
 *   authentication      401  {error:"unauthorized",  refusal_outcome:"authentication"}
 *   authorization       403  {error:"forbidden",     refusal_outcome:"authorization"}
 *   entitlement         403  {error:"forbidden",     refusal_outcome:"entitlement"}
 *   stale_epoch         409  {error:"stale_epoch",   refusal_outcome:"stale_epoch"}
 *   control_unavailable 503  {error:"maintenance",   refusal_outcome:"control_unavailable"}
 *                            + retry-after
 *
 * `refusal_outcome` is ADR-010 §3's "shared status class [that] carries the
 * outcome so the client is not inferring intent from the code alone". It is
 * load-bearing here: authorization and entitlement share status 403 and differ
 * only in that field, which is exactly the distinction ADR-010 amended ADR-004 §4
 * to make possible.
 *
 * ── THE ESCALATION THIS CARRIES ──────────────────────────────────────────────
 *
 * `control_unavailable` is a FIFTH value on a refusal wire, and ADR-010 §3 names
 * four. Adding a value to a shared wire enum is above a lane's bar, so it is
 * filed in `data/run-2026-08-08c/blocked/` for fable rather than ruled here. The
 * fence works either way — the alternative binding is a bare 503 with no
 * `refusal_outcome` field, which is a one-line change in this file and no change
 * anywhere else. That is the blast radius.
 *
 * ── DISCIPLINE INHERITED FROM THE READ PATH ──────────────────────────────────
 *
 * Bodies are FIXED CONSTANTS. Nothing is interpolated — not the reason, not the
 * epoch, not the account. `routes/memories.ts` collapses nine denial reasons into
 * one byte-identical 403 because "telling a caller WHICH check failed is an
 * oracle over grant state", and the same holds here: the fence's internal reasons
 * describe control and grant state and never leave the process.
 *
 * The active epoch is NOT returned to the client either, tempting as it is for a
 * "refresh and retry" instruction. An unauthenticated-to-this-account caller
 * could otherwise probe an account's migration progress, and ADR-012 §4 requires
 * that "account existence must not be probeable through response differences".
 * The client refreshes control state through the bootstrap/control path that
 * ADR-007 §2 keeps reachable while product writes are fenced.
 */

import type { WriteFenceOutcome } from "../../../core/control/write-fence";
import type { WriteEnforcementDecision } from "./write-enforcement-decision";

const JSON_HEADERS = Object.freeze({
  "cache-control": "no-store",
  "content-type": "application/json",
});

/** Seconds. A fixed constant, so the value cannot vary with account state. */
export const CONTROL_UNAVAILABLE_RETRY_AFTER_SECONDS = 60;

interface WireRefusal {
  readonly status: number;
  readonly body: string;
  readonly headers: Readonly<Record<string, string>>;
}

const refusal = (status: number, error: string, outcome: WriteFenceOutcome, headers: Readonly<Record<string, string>> = {}): WireRefusal =>
  Object.freeze({
    status,
    body: JSON.stringify({ error, refusal_outcome: outcome }),
    headers: Object.freeze({ ...JSON_HEADERS, ...headers }),
  });

export const WRITE_FENCE_REFUSALS: Readonly<Record<WriteFenceOutcome, WireRefusal>> = Object.freeze({
  authentication: refusal(401, "unauthorized", "authentication"),
  authorization: refusal(403, "forbidden", "authorization"),
  entitlement: refusal(403, "forbidden", "entitlement"),
  stale_epoch: refusal(409, "stale_epoch", "stale_epoch"),
  control_unavailable: refusal(503, "maintenance", "control_unavailable", {
    "retry-after": String(CONTROL_UNAVAILABLE_RETRY_AFTER_SECONDS),
  }),
});

/**
 * Maps a refusal to its response. Admitted decisions are a caller error: the
 * write path owns the success shape, and returning some placeholder 200 from here
 * would put two modules in charge of what an applied write looks like.
 */
export const writeFenceRefusalResponse = (decision: WriteEnforcementDecision): Response => {
  if (decision.admitted) {
    throw new TypeError("write fence: admitted decisions have no refusal response");
  }
  const wire = WRITE_FENCE_REFUSALS[decision.outcome];
  return new Response(wire.body, { status: wire.status, headers: { ...wire.headers } });
};
