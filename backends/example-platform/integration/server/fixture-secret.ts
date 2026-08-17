import { createHash } from "node:crypto";

/**
 * Deterministic 32-byte QA fixture secrets.
 *
 * Derived from a fixed label with no wall clock, randomness, environment, or
 * network, so a harness restart re-derives the same reader-scoped opaque refs
 * and the same cursor signatures. That determinism is load-bearing: a cursor
 * minted before a restart must still verify after it, or every pagination
 * assertion becomes restart-order dependent.
 *
 * These are NEVER production keys and no production secret may ever be placed
 * here. The harness binds loopback only (board ruling PR-4).
 */
export const fixtureSecret = (label: string): Uint8Array =>
  new Uint8Array(createHash("sha256").update(`omi-integration-fixture:${label}`, "utf8").digest());
