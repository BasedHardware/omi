import type { ApplicationReadSnapshotAttestation } from "../../../core/retrieve/application-read";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import { asOpaqueVisibleKeyset, issueMcpCursor, verifyMcpCursor, type McpCursorSigningKeyset } from "../../mcp/cursor";

export function createProductionCursor(keyset: McpCursorSigningKeyset) {
  const captured = { active_key_id: keyset.active_key_id, keys: keyset.keys.map(key => ({ key_id: key.key_id, secret: new Uint8Array(key.secret) })) };
  const bindings = (attestation: ApplicationReadSnapshotAttestation) => {
    const { read_timestamp_epoch_seconds: _, ...snapshot } = attestation;
    const digest = sha256CanonicalContent(snapshot);
    return {
      owner_digest: attestation.owner_identity_digest,
      app_digest: attestation.application_identity_digest,
      credential_key_digest: attestation.credential_identity_digest,
      authorization_generation_digest: attestation.authorization_state_digest,
      grant_generation_digest: attestation.grant_state_digest,
      account_generation_digest: attestation.account_head_digest,
      graph_generation_digest: attestation.authorized_graph_digest,
      projection_generation_digest: digest,
      projection_commit_digest: attestation.coherent_projection_commit_digest,
      visibility_digest: attestation.visibility_digest,
      filter_digest: attestation.filter_digest,
      query_digest: attestation.query_digest,
      cursor_policy_digest: sha256CanonicalContent({ version: "production-cursor-v1", ttl: 900 }),
      source_digest: attestation.source_digest,
      read_mode_digest: attestation.read_mode_digest,
    };
  };
  return Object.freeze({
    verifyCursor: (cursor: string, attestation: ApplicationReadSnapshotAttestation): string => verifyMcpCursor(cursor, {
      bindings: bindings(attestation), now_epoch_seconds: attestation.read_timestamp_epoch_seconds,
    }, captured).last_visible_key,
    issueCursor: (key: string, attestation: ApplicationReadSnapshotAttestation) => issueMcpCursor({
      last_visible_key: asOpaqueVisibleKeyset(key), bindings: bindings(attestation),
      issued_at_epoch_seconds: attestation.read_timestamp_epoch_seconds, ttl_seconds: 900,
    }, captured),
  });
}
