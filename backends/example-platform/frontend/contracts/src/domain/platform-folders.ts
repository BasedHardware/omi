/**
 * The PLATFORM generation's folder READ model — surface-facing declarations.
 *
 * Field-identical to `Folder` in `./folders.ts` except `id` is an unbranded
 * storage id. Coverage is carried from the server's completeness envelope.
 * There is no maximum-folder cap.
 */

export interface PlatformFolderItem {
  readonly id: string;
  readonly name: string;
  readonly description: string | null;
  readonly color: string;
  readonly icon: string;
  readonly createdAt: number;
  readonly updatedAt: number;
  readonly order: number;
  readonly isDefault: boolean;
  readonly isSystem: boolean;
  readonly revision: string | null;
}

export type PlatformFolderCoverageState =
  | { readonly kind: "unknown" }
  | {
      readonly kind: "known";
      readonly status: PlatformFolderCoverageStatus;
      readonly reasons: readonly PlatformFolderCoverageReason[];
      readonly complete: boolean;
      readonly queryGap: boolean;
      readonly hasMore: boolean;
    };

export type PlatformFolderCoverageStatus =
  | "complete"
  | "incomplete"
  | "degraded"
  | "partial";

export type PlatformFolderCoverageReason =
  | "pending_writes"
  | "projection_stale"
  | "projection_unavailable"
  | "projection_bypassed"
  | "source_bound"
  | "time_bound"
  | "policy_bound";

export const UNKNOWN_PLATFORM_FOLDER_COVERAGE: PlatformFolderCoverageState = {
  kind: "unknown",
};
