import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import { assertAuthorizedLedgerWriteContext } from "../auth/authorized-context";
import {
  LISTEN_FORMATION_OUTBOX_LEASE_VERSION,
  LISTEN_FORMATION_OUTBOX_PAYLOAD_VERSION,
  type ListenFormationOutboxLease,
  type ListenFormationOutboxPayload,
  type ListenFormationOutboxRepository,
} from "./formation-outbox-consumer";
import type { ListenFormationFinalization } from "./formation-ingestion";

interface StoredOutboxRow {
  state: "pending" | "leased" | "accepted" | "failed";
  leaseFence: number;
  readonly payload: ListenFormationOutboxPayload;
}

export interface InMemoryListenFormationOutbox {
  readonly repository: ListenFormationOutboxRepository;
  enqueue(finalization: ListenFormationFinalization): ListenFormationOutboxPayload;
}

const payloadDigest = (finalization: ListenFormationFinalization): string =>
  sha256CanonicalContent({
    contract_version: "listen-formation-outbox-payload-v1",
    finalization,
  });

export const createInMemoryListenFormationOutbox = (): InMemoryListenFormationOutbox => {
  const rows = new Map<string, StoredOutboxRow>();

  const enqueue = (finalization: ListenFormationFinalization): ListenFormationOutboxPayload => {
    const outboxId = `listen-outbox:${finalization.finalization_id}`;
    const existing = rows.get(outboxId);
    if (existing !== undefined) return existing.payload;
    const digest = payloadDigest(finalization);
    const payload: ListenFormationOutboxPayload = Object.freeze({
      version: LISTEN_FORMATION_OUTBOX_PAYLOAD_VERSION,
      owner_account_id: finalization.owner_account_id,
      outbox_id: outboxId,
      finalization_id: finalization.finalization_id,
      formation_work_id: finalization.formation_work_id,
      finalization_digest: finalization.finalization_digest,
      payload_digest: digest,
      finalization,
    });
    rows.set(outboxId, { state: "pending", leaseFence: 0, payload });
    return payload;
  };

  const repository: ListenFormationOutboxRepository = Object.freeze({
    async claimNext(context) {
      const authorized = assertAuthorizedLedgerWriteContext(context);
      if (authorized.capability !== "memories.work.accept") {
        return { kind: "authorization_denied" as const, reason: "capability_denied" };
      }
      const pending = [...rows.values()]
        .filter((row) => row.state === "pending"
          && row.payload.owner_account_id === authorized.account_id)
        .sort((left, right) => left.payload.outbox_id < right.payload.outbox_id ? -1 : 1);
      const next = pending[0];
      if (next === undefined) return { kind: "none_available" as const };
      next.state = "leased";
      next.leaseFence += 1;
      const lease: ListenFormationOutboxLease = Object.freeze({
        version: LISTEN_FORMATION_OUTBOX_LEASE_VERSION,
        owner_account_id: next.payload.owner_account_id,
        outbox_id: next.payload.outbox_id,
        finalization_id: next.payload.finalization_id,
        formation_work_id: next.payload.formation_work_id,
        finalization_digest: next.payload.finalization_digest,
        payload_digest: next.payload.payload_digest,
        lease_fence: next.leaseFence,
      });
      return { kind: "claimed" as const, lease };
    },
    async load(context, lease) {
      assertAuthorizedLedgerWriteContext(context);
      const row = rows.get(lease.outbox_id);
      if (row === undefined) return { kind: "not_found" as const };
      if (row.state !== "leased" || row.leaseFence !== lease.lease_fence) {
        return { kind: "stale_lease" as const };
      }
      return { kind: "found" as const, payload: row.payload };
    },
    async markAccepted(context, lease) {
      assertAuthorizedLedgerWriteContext(context);
      const row = rows.get(lease.outbox_id);
      if (row === undefined) return { kind: "ineligible_state" as const };
      if (row.state === "accepted") return { kind: "replayed" as const };
      if (row.state !== "leased" || row.leaseFence !== lease.lease_fence) {
        return { kind: "stale_lease" as const };
      }
      row.state = "accepted";
      return { kind: "accepted" as const };
    },
    async recordFailure(context, lease) {
      assertAuthorizedLedgerWriteContext(context);
      const row = rows.get(lease.outbox_id);
      if (row === undefined) return { kind: "ineligible_state" as const };
      if (row.state === "failed") return { kind: "replayed" as const };
      if (row.state !== "leased" || row.leaseFence !== lease.lease_fence) {
        return { kind: "stale_lease" as const };
      }
      row.state = "failed";
      return { kind: "recorded" as const };
    },
  });

  return Object.freeze({ repository, enqueue });
};
