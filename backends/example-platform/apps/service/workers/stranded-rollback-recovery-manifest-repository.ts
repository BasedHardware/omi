import type { VerifiedStrandedRollbackRecoveryManifest } from "../../../core/control/stranded-rollback-recovery";

export interface StrandedRollbackRecoveryManifestKey {
  readonly version: "stranded-rollback-recovery-manifest-key-v1";
  readonly account_id: string;
  readonly control_revision: number;
  readonly account_epoch: number;
  readonly database_generation_digest: string;
  readonly manifest_digest: string;
}

export interface StoredStrandedRollbackRecoveryManifest {
  readonly version: "stored-stranded-rollback-recovery-manifest-v1";
  readonly account_id: string;
  readonly control_revision: number;
  readonly account_epoch: number;
  readonly database_generation_digest: string;
  readonly cutover_frontier_digest: string;
  readonly rollback_frontier_digest: string;
  readonly cutover_at_epoch_seconds: number;
  readonly rolled_back_at_epoch_seconds: number;
  readonly recovery_deadline_epoch_seconds: number;
  readonly surface_count: number;
  readonly total_record_count: number;
  readonly manifest_digest: string;
  readonly persistence_receipt_digest: string;
}

export type StrandedRollbackRecoveryManifestLoad =
  | Readonly<{ readonly kind: "missing" }>
  | Readonly<{
      readonly kind: "found";
      readonly manifest: StoredStrandedRollbackRecoveryManifest;
    }>;

export interface StrandedRollbackRecoveryManifestRepository {
  record(
    manifest: VerifiedStrandedRollbackRecoveryManifest,
  ): Promise<Readonly<{
    readonly kind: "stored" | "replayed";
    readonly manifest: StoredStrandedRollbackRecoveryManifest;
  }>>;
  load(key: StrandedRollbackRecoveryManifestKey): Promise<StrandedRollbackRecoveryManifestLoad>;
}
