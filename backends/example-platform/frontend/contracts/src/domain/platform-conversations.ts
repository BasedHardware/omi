/**
 * The PLATFORM generation's conversation READ model — surface-facing
 * declarations.
 *
 * Field-identical to `Conversation` in `./conversations.ts` except `id` is an
 * unbranded storage id (the service already serves it) rather than a
 * `RecordId`. Coverage is a separate claim, carried from the server's
 * completeness envelope, never derived from item counts.
 */

export interface PlatformConversationItem {
  readonly id: string;
  readonly title: string;
  readonly overview: string;
  readonly createdAt: number;
  readonly updatedAt: number;
  readonly startedAt: number | null;
  readonly finishedAt: number | null;
  readonly source: string;
  readonly status: string;
  readonly discarded: boolean;
  readonly starred: boolean;
  readonly visibility: "public" | "private" | "shared";
  readonly isLocked: boolean;
  /** Opaque. `null` = unfiled. A non-null value may dangle. */
  readonly folderId: string | null;
  readonly revision: string | null;
}

export type PlatformConversationCoverageState =
  | { readonly kind: "unknown" }
  | {
      readonly kind: "known";
      readonly status: PlatformConversationCoverageStatus;
      readonly reasons: readonly PlatformConversationCoverageReason[];
      readonly complete: boolean;
      readonly queryGap: boolean;
      readonly hasMore: boolean;
    };

export type PlatformConversationCoverageStatus =
  | "complete"
  | "incomplete"
  | "degraded"
  | "partial";

export type PlatformConversationCoverageReason =
  | "pending_writes"
  | "projection_stale"
  | "projection_unavailable"
  | "projection_bypassed"
  | "source_bound"
  | "time_bound"
  | "policy_bound";

export const UNKNOWN_PLATFORM_CONVERSATION_COVERAGE: PlatformConversationCoverageState = {
  kind: "unknown",
};
