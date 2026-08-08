// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMX-001)
// domain-pending(DIV-DOMX-006)
import { sha256CanonicalContent } from "../../core/retrieve/content-digest";
import type { ApplicationReadSnapshotAttestation } from "../../core/retrieve/application-read";
import {
  InvalidMcpCursorError,
  MAX_MCP_CURSOR_ENCODED_BYTES,
  asOpaqueVisibleKeyset,
  issueMcpCursor,
  verifyMcpCursor,
  type McpCursorBindings,
  type McpCursorSigningKeyset,
} from "../mcp/cursor";

/**
 * QA-only bridge between the application read's snapshot attestation and the
 * protocol cursor's 15 replay bindings.
 *
 * The security property this file exists to hold is **totality**: every field of
 * `ApplicationReadSnapshotAttestation` must influence at least one binding
 * digest. The 15-field binding vocabulary is fixed by the cursor module, and it
 * is narrower than the attestation, so the surplus attestation state is folded
 * into two adapter-owned digests rather than dropped. Dropping any of it would
 * let a cursor minted against one coherent snapshot verify against a different
 * one — which is a replay oracle, not a convenience.
 *
 * `cursor-bindings.test.ts` proves totality field-by-field rather than asserting
 * this comment.
 */

const STABLE_VISIBLE_KEY = /^vk1_[a-f0-9]{64}$/;
const SHA256_HEX = /^[a-f0-9]{64}$/;

/** QA cursor policy. Changing any of it must invalidate every outstanding cursor. */
export interface QaCursorPolicy {
  readonly policy_version: string;
  readonly ttl_seconds: number;
  readonly max_limit: number;
}

export const QA_CURSOR_POLICY: Readonly<QaCursorPolicy> = Object.freeze({
  policy_version: "qa-application-cursor-v1",
  ttl_seconds: 900,
  max_limit: 100,
});

/**
 * Folds the attestation state that has no dedicated binding slot into one
 * digest: the produced-render receipt, the projected content, all five source
 * generation receipts, and the declared coverage.
 *
 * Coverage belongs here because it determines the emitted `window` and
 * `completeness` of a page. A continuation issued under one coverage claim must
 * not be redeemable under another, or the second page would silently describe a
 * different read than the first.
 */
const projectionGenerationDigest = (attestation: ApplicationReadSnapshotAttestation): string =>
  sha256CanonicalContent({
    version: "qa-application-projection-generation-v1",
    synthesized_projection_generation_digest: attestation.synthesized_projection_generation_digest,
    projected_content_digest: attestation.projected_content_digest,
    durable_generation_digest: attestation.durable_generation_digest,
    overlay_generation_digest: attestation.overlay_generation_digest,
    declared_generation_digest: attestation.declared_generation_digest,
    accepted_generation_digest: attestation.accepted_generation_digest,
    stm_generation_digest: attestation.stm_generation_digest,
    coverage: attestation.coverage,
  });

const cursorPolicyDigest = (policy: QaCursorPolicy): string =>
  sha256CanonicalContent({
    version: "qa-application-cursor-policy-v1",
    policy_version: policy.policy_version,
    ttl_seconds: policy.ttl_seconds,
    max_limit: policy.max_limit,
  });

/**
 * Thirteen coordinates map one-to-one onto their binding slot; the remaining two
 * slots carry the folded projection-generation and cursor-policy digests. The
 * read timestamp is not a binding: it is the cursor payload's authenticated
 * `issued_at_epoch_seconds`, which the cursor module signs and range-checks.
 */
export const qaCursorBindings = (
  attestation: ApplicationReadSnapshotAttestation,
  policy: QaCursorPolicy = QA_CURSOR_POLICY,
): Readonly<McpCursorBindings> => Object.freeze({
  owner_digest: attestation.owner_identity_digest,
  app_digest: attestation.application_identity_digest,
  credential_key_digest: attestation.credential_identity_digest,
  authorization_generation_digest: attestation.authorization_state_digest,
  grant_generation_digest: attestation.grant_state_digest,
  account_generation_digest: attestation.account_head_digest,
  graph_generation_digest: attestation.authorized_graph_digest,
  projection_generation_digest: projectionGenerationDigest(attestation),
  projection_commit_digest: attestation.coherent_projection_commit_digest,
  visibility_digest: attestation.visibility_digest,
  filter_digest: attestation.filter_digest,
  query_digest: attestation.query_digest,
  cursor_policy_digest: cursorPolicyDigest(policy),
  source_digest: attestation.source_digest,
  read_mode_digest: attestation.read_mode_digest,
});

export interface QaCursorAdapterOptions {
  readonly signing_keyset: McpCursorSigningKeyset;
  readonly policy?: QaCursorPolicy;
}

export interface QaCursorAdapter {
  /** Returns the continuation's stable visible key, or throws InvalidMcpCursorError. */
  readonly verifyCursor: (cursor: string, attestation: ApplicationReadSnapshotAttestation) => string;
  readonly issueCursor: (lastVisibleKey: string, attestation: ApplicationReadSnapshotAttestation) => string;
}

/**
 * Every client-controlled cursor rejection leaves this adapter as exactly one
 * `InvalidMcpCursorError`, regardless of which check failed.
 *
 * This matters more than it looks. The application read core validates a cursor
 * against the ratified keyset grammar *before* this adapter runs and raises a
 * plain `TypeError` when it fails, which the MCP transport reports as an
 * internal error rather than an invalid cursor. Two different public outcomes
 * for two different client mutations of the same token is an oracle: it tells an
 * attacker which half of their guess was wrong. So the syntactic pre-check is
 * performed here too, in the same error currency as every other failure, and the
 * caller applies it before the core ever sees the bytes.
 */
export const isSyntacticallyRedeemableCursor = (cursor: unknown): cursor is string =>
  typeof cursor === "string"
  && cursor.length > 0
  && Buffer.byteLength(cursor, "utf8") <= MAX_MCP_CURSOR_ENCODED_BYTES
  && /^[\x21-\x7e]{1,4096}$/.test(cursor);

export const createQaCursorAdapter = (options: QaCursorAdapterOptions): QaCursorAdapter => {
  const policy = options.policy ?? QA_CURSOR_POLICY;
  const keyset = options.signing_keyset;
  if (!Number.isSafeInteger(policy.ttl_seconds) || policy.ttl_seconds < 1) {
    throw new TypeError("QA cursor policy requires a positive integer TTL");
  }
  if (!Number.isSafeInteger(policy.max_limit) || policy.max_limit < 1) {
    throw new TypeError("QA cursor policy requires a positive integer max limit");
  }

  const readTimestamp = (attestation: ApplicationReadSnapshotAttestation): number => {
    const seconds = attestation.read_timestamp_epoch_seconds;
    if (!Number.isSafeInteger(seconds) || seconds < 0) {
      // An unusable read timestamp is a composition defect, not client input.
      throw new TypeError("QA cursor adapter requires an authoritative read timestamp");
    }
    return seconds;
  };

  return Object.freeze({
    verifyCursor: (cursor: string, attestation: ApplicationReadSnapshotAttestation): string => {
      if (!isSyntacticallyRedeemableCursor(cursor)) {
        throw new InvalidMcpCursorError();
      }
      const claims = verifyMcpCursor(cursor, {
        bindings: qaCursorBindings(attestation, policy),
        // The cursor's freshness window is measured against the authoritative
        // read timestamp of this snapshot, never an ambient wall clock. A
        // hermetic QA read and a production read therefore agree.
        now_epoch_seconds: readTimestamp(attestation),
      }, keyset);
      if (!STABLE_VISIBLE_KEY.test(claims.last_visible_key)) {
        throw new InvalidMcpCursorError();
      }
      return claims.last_visible_key;
    },

    issueCursor: (lastVisibleKey: string, attestation: ApplicationReadSnapshotAttestation): string => {
      // Issuance is server-authored. A malformed key here is a composition bug
      // and must not be laundered into the client-facing invalid-cursor shape.
      if (!STABLE_VISIBLE_KEY.test(lastVisibleKey)) {
        throw new TypeError("QA cursor adapter requires a vk1 stable visible keyset");
      }
      const bindings = qaCursorBindings(attestation, policy);
      for (const digest of Object.values(bindings)) {
        if (!SHA256_HEX.test(digest)) {
          throw new TypeError("QA cursor bindings must be lowercase SHA-256 digests");
        }
      }
      return issueMcpCursor({
        last_visible_key: asOpaqueVisibleKeyset(lastVisibleKey),
        bindings,
        issued_at_epoch_seconds: readTimestamp(attestation),
        ttl_seconds: policy.ttl_seconds,
      }, keyset);
    },
  });
};
