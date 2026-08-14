/**
 * The PLATFORM generation's task READ model — surface-facing declarations.
 *
 * Unlike `SynthesizedMemoryItem`, which is a genuinely different record class
 * from the legacy `Memory` it sits beside, `PlatformTaskItem` is deliberately
 * FIELD-IDENTICAL to `Task` in `./tasks.ts` — every one of the thirteen, same
 * names, same types. That is the whole ruling: `DAVID-tasks-read-epoch-and-ci`
 * D2 ratifies full parity precisely so the surface renders identically off
 * either generation, which is what turns `openTasks()` into a one-line factory
 * change with a one-line rollback. A narrower read model here would make the
 * flip visible to users and convert a mechanical change into a product event.
 *
 * SO WHY A SEPARATE TYPE AT ALL, if the fields match? Because `id` does not.
 *
 * `Task["id"]` is a `RecordId` — a slug or legacy UUID that went through
 * `parseRecordId`, and the alias `adapters-legacy/src/tasks.ts` maintains
 * between a local slug and a server id. `PlatformTaskItem["id"]` is the
 * ratified reader-scoped OPAQUE ref, which is not a `RecordId`, does not parse
 * as one, and is not stable across readers. D2 says so outright: that alias
 * does not cross this wire. Declaring one type for both would let an opaque
 * handle be passed to something expecting an addressable domain id, and the
 * compiler would not object — which is the shape of the defect that had a QA
 * door serving raw storage row ids as public item ids.
 *
 * These declarations drop the ratified package's brands for the same reason
 * `synthesized-memories.ts` does: brands are a PARSING discipline owned by
 * `packages/adapters-platform`, and a surface should not need the ratified
 * package on its dependency path to render a string.
 */

/** One task as the platform generation serves it. Read-only by construction. */
export interface PlatformTaskItem {
  /**
   * Reader-scoped opaque handle. NOT a `RecordId` and NOT parseable with
   * `parseRecordId`. Treat it as a key, never as an address, and never join it
   * against a legacy server id.
   */
  readonly id: string;
  readonly description: string;
  readonly completed: boolean;
  readonly completedAt: number | null;
  readonly dueAt: number | null;
  readonly owner: string | null;
  /** Where the task came from; `assistant` writes carry provenance. */
  readonly source: string;
  readonly provenance: readonly string[];
  readonly sortOrder: number;
  readonly indentLevel: number;
  readonly createdAt: number;
  readonly updatedAt: number;
  /** Server revision of the last write we saw; reconcile compares these. */
  readonly revision: string | null;
}

/**
 * How much of the account's task set the loaded window actually covers.
 *
 * Same discipline as `SynthesizedRecallState`, and for the same reason: the
 * absence of a coverage envelope is NOT evidence of coverage. `kind: "unknown"`
 * is what an unparseable body, a non-200, or a pre-contract origin produces,
 * and there is deliberately no way to spell "we saw nothing, therefore there is
 * nothing" — that sentence is how a client deletes local rows a degraded
 * projection failed to return.
 *
 * `complete` is the SERVER'S declaration, carried verbatim. A client never
 * derives it from item counts or a short page.
 */
export type PlatformTaskCoverageState =
  | { readonly kind: "unknown" }
  | {
      readonly kind: "known";
      /**
       * The ratified status, already reduced by the contract's own precedence
       * rule `degraded > incomplete > partial > complete`.
       */
      readonly status: PlatformTaskCoverageStatus;
      /** Every applicable limitation, not only the winning family. */
      readonly reasons: readonly PlatformTaskCoverageReason[];
      /** `status === "complete"`, restated so a caller cannot misread it. */
      readonly complete: boolean;
      /** The server searched and found nothing — zero tasks IS the answer. */
      readonly queryGap: boolean;
      readonly hasMore: boolean;
    };

export type PlatformTaskCoverageStatus = "complete" | "incomplete" | "degraded" | "partial";

/**
 * The ratified `LimitationReason` union for tasks, restated as a closed union
 * so a surface's exhaustive switch breaks at compile time when the contract
 * adds a reason — the moment a human must decide how to explain it, rather
 * than a moment to fall through to a generic message.
 *
 * `pending_writes` is the tasks analogue of the memories wire's
 * `accepted_work_pending`: an op the write path applied that this projection
 * has not caught up with. It is a different word because it is a different
 * fact, and the two wires' envelopes are separately versioned for exactly that
 * reason.
 */
export type PlatformTaskCoverageReason =
  | "pending_writes"
  | "projection_stale"
  | "projection_unavailable"
  | "projection_bypassed"
  | "source_bound"
  | "time_bound"
  | "policy_bound";

/** The state a store reports before its first read has resolved. */
export const UNKNOWN_PLATFORM_TASK_COVERAGE: PlatformTaskCoverageState = { kind: "unknown" };
