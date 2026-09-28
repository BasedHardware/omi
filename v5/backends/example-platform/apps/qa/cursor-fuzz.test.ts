// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMX-001)
import { describe, expect, test } from "bun:test";
import fc from "fast-check";

import type { ApplicationReadSnapshotAttestation } from "../../core/retrieve/application-read";
import {
  InvalidMcpCursorError,
  isInvalidMcpCursorError,
  type McpCursorSigningKeyset,
} from "../mcp/cursor";
import { createQaCursorAdapter } from "./cursor-bindings";

/** Fixed so every property is hermetic: no clock, no ambient time. */
const FIXED_READ_TIMESTAMP_EPOCH_SECONDS = 1_800_000_000;

/**
 * Explicit seed on every `fc.assert` so a failure is reproducible and CI cannot
 * flake on generator luck. Tune `numRuns` to keep the file under ~10s.
 */
const FC_ASSERT: { seed: number; numRuns: number } = Object.freeze({
  seed: 20260808,
  numRuns: 200,
});

const FIXED_COVERAGE = {
  declared_frontier: "frontier-v1:declared",
  accepted: { state: "no_eligible", searched_frontier: null },
  stm: { state: "no_eligible", searched_frontier: null },
  projection_freshness: "fresh",
  intentional_bounds: [],
} as ApplicationReadSnapshotAttestation["coverage"];

/** Digest fields a single-field mutation can reach (coverage is tested elsewhere). */
const MUTABLE_DIGEST_FIELDS = [
  "owner_identity_digest",
  "application_identity_digest",
  "credential_identity_digest",
  "authorization_state_digest",
  "grant_state_digest",
  "account_head_digest",
  "authorized_graph_digest",
  "coherent_projection_commit_digest",
  "visibility_digest",
  "filter_digest",
  "query_digest",
  "source_digest",
  "read_mode_digest",
  "synthesized_projection_generation_digest",
  "projected_content_digest",
  "durable_generation_digest",
  "overlay_generation_digest",
  "declared_generation_digest",
  "accepted_generation_digest",
  "stm_generation_digest",
] as const;

type MutableDigestField = (typeof MUTABLE_DIGEST_FIELDS)[number];

const sha256DigestArb = fc.hexaString({ minLength: 64, maxLength: 64 });

const visibleKeyArb = sha256DigestArb.map((hex) => `vk1_${hex}`);

const attestationArb: fc.Arbitrary<ApplicationReadSnapshotAttestation> = fc.record({
  owner_identity_digest: sha256DigestArb,
  application_identity_digest: sha256DigestArb,
  credential_identity_digest: sha256DigestArb,
  authorization_state_digest: sha256DigestArb,
  grant_state_digest: sha256DigestArb,
  account_head_digest: sha256DigestArb,
  authorized_graph_digest: sha256DigestArb,
  coherent_projection_commit_digest: sha256DigestArb,
  visibility_digest: sha256DigestArb,
  filter_digest: sha256DigestArb,
  query_digest: sha256DigestArb,
  source_digest: sha256DigestArb,
  read_mode_digest: sha256DigestArb,
  read_timestamp_epoch_seconds: fc.constant(FIXED_READ_TIMESTAMP_EPOCH_SECONDS),
  synthesized_projection_generation_digest: sha256DigestArb,
  projected_content_digest: sha256DigestArb,
  durable_generation_digest: sha256DigestArb,
  overlay_generation_digest: sha256DigestArb,
  declared_generation_digest: sha256DigestArb,
  accepted_generation_digest: sha256DigestArb,
  stm_generation_digest: sha256DigestArb,
  coverage: fc.constant(FIXED_COVERAGE),
});

const signingSecretArb = fc.uint8Array({ minLength: 32, maxLength: 32 });

const keysetFromSecret = (secret: Uint8Array): McpCursorSigningKeyset => Object.freeze({
  active_key_id: "qa-fuzz-1",
  keys: Object.freeze([Object.freeze({
    key_id: "qa-fuzz-1",
    secret,
  })]),
});

const printableAsciiCharArb = fc.integer({ min: 0x20, max: 0x7e }).map((code) =>
  String.fromCharCode(code)
);

/** Printable ASCII (space through ~), length 0..4096 — the encoded cursor bound. */
const printableAsciiStringArb = fc.stringOf(printableAsciiCharArb, {
  minLength: 0,
  maxLength: 4096,
});

const junkStringArb = fc.oneof(fc.string(), printableAsciiStringArb);

type CursorMutationKind = "substitute" | "delete" | "insert";

const mutateCursor = (
  cursor: string,
  kind: CursorMutationKind,
  indexSeed: number,
  char: string,
): string => {
  if (kind === "insert") {
    const index = cursor.length === 0 ? 0 : indexSeed % (cursor.length + 1);
    return `${cursor.slice(0, index)}${char}${cursor.slice(index)}`;
  }
  if (cursor.length === 0) return cursor;
  const index = indexSeed % cursor.length;
  if (kind === "delete") {
    return `${cursor.slice(0, index)}${cursor.slice(index + 1)}`;
  }
  // substitute — may be a no-op when `char` equals the existing character
  return `${cursor.slice(0, index)}${char}${cursor.slice(index + 1)}`;
};

const secretsEqual = (left: Uint8Array, right: Uint8Array): boolean => {
  if (left.byteLength !== right.byteLength) return false;
  for (let i = 0; i < left.byteLength; i += 1) {
    if (left[i] !== right[i]) return false;
  }
  return true;
};

describe("QA cursor property fuzz", () => {
  test("round-trip: verify(issue(k, a), a) === k for arbitrary valid inputs", () => {
    fc.assert(
      fc.property(attestationArb, visibleKeyArb, signingSecretArb, (attestation, key, secret) => {
        const adapter = createQaCursorAdapter({ signing_keyset: keysetFromSecret(secret) });
        const cursor = adapter.issueCursor(key, attestation);
        return adapter.verifyCursor(cursor, attestation) === key;
      }),
      FC_ASSERT,
    );
  });

  test("total tamper rejection: single-char mutate never yields another key or a foreign error", () => {
    // red-proof: if verifyCursor returned last_visible_key from a forged payload
    // after a one-char substitute (signature check skipped), this would accept a
    // non-no-op mutation and/or return a different key.
    fc.assert(
      fc.property(
        attestationArb,
        visibleKeyArb,
        signingSecretArb,
        fc.constantFrom<CursorMutationKind>("substitute", "delete", "insert"),
        fc.nat(),
        printableAsciiCharArb,
        (attestation, key, secret, kind, indexSeed, char) => {
          const adapter = createQaCursorAdapter({ signing_keyset: keysetFromSecret(secret) });
          const cursor = adapter.issueCursor(key, attestation);
          const mutated = mutateCursor(cursor, kind, indexSeed, char);
          try {
            const got = adapter.verifyCursor(mutated, attestation);
            // Acceptance is only lawful for a no-op mutation, and only with the
            // original key — never a different key.
            return mutated === cursor && got === key;
          } catch (error) {
            return isInvalidMcpCursorError(error);
          }
        },
      ),
      FC_ASSERT,
    );
  });

  test("uniform rejection shape: junk always fails as InvalidMcpCursorError:invalid cursor", () => {
    // red-proof: if isSyntacticallyRedeemableCursor let a NUL / oversize string
    // through and the decoder then threw TypeError, the observed set would gain
    // a second name:message shape.
    const adapter = createQaCursorAdapter({
      signing_keyset: keysetFromSecret(new Uint8Array(32).fill(7)),
    });
    const attestation: ApplicationReadSnapshotAttestation = {
      owner_identity_digest: "a".repeat(64),
      application_identity_digest: "b".repeat(64),
      credential_identity_digest: "c".repeat(64),
      authorization_state_digest: "d".repeat(64),
      grant_state_digest: "e".repeat(64),
      account_head_digest: "f".repeat(64),
      authorized_graph_digest: "0".repeat(64),
      coherent_projection_commit_digest: "1".repeat(64),
      visibility_digest: "2".repeat(64),
      filter_digest: "3".repeat(64),
      query_digest: "4".repeat(64),
      source_digest: "5".repeat(64),
      read_mode_digest: "6".repeat(64),
      read_timestamp_epoch_seconds: FIXED_READ_TIMESTAMP_EPOCH_SECONDS,
      synthesized_projection_generation_digest: "7".repeat(64),
      projected_content_digest: "8".repeat(64),
      durable_generation_digest: "9".repeat(64),
      overlay_generation_digest: "a".repeat(64),
      declared_generation_digest: "b".repeat(64),
      accepted_generation_digest: "c".repeat(64),
      stm_generation_digest: "d".repeat(64),
      coverage: FIXED_COVERAGE,
    };

    const observed = new Set<string>();
    fc.assert(
      fc.property(junkStringArb, (junk) => {
        try {
          adapter.verifyCursor(junk, attestation);
          observed.add("ACCEPTED");
          return false;
        } catch (error) {
          if (isInvalidMcpCursorError(error) && error instanceof InvalidMcpCursorError) {
            observed.add(`${error.name}:${error.message}`);
            return error.message === "invalid cursor";
          }
          observed.add(
            `LEAK:${error instanceof Error ? error.constructor.name : typeof error}`,
          );
          return false;
        }
      }),
      FC_ASSERT,
    );
    expect([...observed]).toEqual(["InvalidMcpCursorError:invalid cursor"]);
  });

  test("binding sensitivity: changing any one digest field refuses redemption", () => {
    // red-proof: if owner_identity_digest were dropped from qaCursorBindings, a
    // single-field change to it would still verify and this property would fail.
    fc.assert(
      fc.property(
        attestationArb,
        visibleKeyArb,
        signingSecretArb,
        fc.constantFrom<MutableDigestField>(...MUTABLE_DIGEST_FIELDS),
        sha256DigestArb,
        (attestation, key, secret, field, replacement) => {
          fc.pre(replacement !== attestation[field]);
          const adapter = createQaCursorAdapter({ signing_keyset: keysetFromSecret(secret) });
          const cursor = adapter.issueCursor(key, attestation);
          const mutated: ApplicationReadSnapshotAttestation = {
            ...attestation,
            [field]: replacement,
          };
          try {
            adapter.verifyCursor(cursor, mutated);
            return false;
          } catch (error) {
            return isInvalidMcpCursorError(error);
          }
        },
      ),
      FC_ASSERT,
    );
  });

  test("no key confusion: a cursor from keyset A never verifies under keyset B", () => {
    fc.assert(
      fc.property(
        attestationArb,
        visibleKeyArb,
        signingSecretArb,
        signingSecretArb,
        (attestation, key, secretA, secretB) => {
          fc.pre(!secretsEqual(secretA, secretB));
          const issued = createQaCursorAdapter({ signing_keyset: keysetFromSecret(secretA) })
            .issueCursor(key, attestation);
          const other = createQaCursorAdapter({ signing_keyset: keysetFromSecret(secretB) });
          try {
            other.verifyCursor(issued, attestation);
            return false;
          } catch (error) {
            return isInvalidMcpCursorError(error);
          }
        },
      ),
      FC_ASSERT,
    );
  });
});
