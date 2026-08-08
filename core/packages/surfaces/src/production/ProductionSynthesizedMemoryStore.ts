import type { StoreStatus } from "@omi-core/domain";

/**
 * Surface-facing port for the **platform-generation** memory read model.
 *
 * These shapes are FE-CORE's published port, restated here verbatim so this package
 * builds before `ProductionStores.ts` carries them. FE-CORE owns that file; when their
 * additions land, this module collapses into a re-export and the declarations below are
 * deleted. Nothing in the surfaces package may fork this shape — see
 * `status/FE-CORE.md`, section "PUBLISHED SHAPES".
 *
 * **This is a READ model** (board ruling PR-2). There is deliberately no create, patch,
 * delete, visibility control or dead-letter pair: the ratified wire carries no editable
 * memory fields and no internal record ids, and a read model has no outbox. The legacy
 * editable Memories surface still lives unchanged in `MemoriesProduction.tsx`; the two are
 * different generations, not versions of each other.
 */

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)

type ObservableStore = {
  status(): StoreStatus;
  subscribe(listener: () => void): () => void;
  refresh(): Promise<void>;
};

/**
 * One synthesized proposition. `text` is the one and only presentation field — there is
 * no title, category, visibility, timestamp or revision on this wire, and `id` is an
 * opaque server-owned render id, **not** a `RecordId`. Never parse it, never show it.
 */
export type SynthesizedMemoryItem = {
  readonly id: string;
  readonly text: string;
  /** Opaque refs. Absent means the server sent no citation field, not "cited by nothing". */
  readonly citations?: readonly string[];
  /** Absent means no lineage was supplied for this proposition. */
  readonly provenance?: {
    readonly synthesisVersion: string;
    /** sha256 hex. */
    readonly inputDigest: string;
    readonly outputDigest: string;
  };
};

/**
 * Rule-12 honesty as a union, so "we do not know" cannot be spelled as "complete".
 *
 * `unknown` is not a degenerate `known`: it is the state where no honest page exists yet
 * (offline, unparseable, or an origin that sends no envelope). Rendering it with the same
 * empty state as a declared-complete zero-item page is the bug this union exists to make
 * unrepresentable.
 */
export type SynthesizedRecallState =
  | { readonly kind: "unknown" }
  | {
      readonly kind: "known";
      readonly status: "complete" | "incomplete" | "degraded" | "partial";
      /** Ratified LimitationReason values. Typed as string: the server may add one. */
      readonly reasons: readonly string[];
      /** True only when the server DECLARED completeness. */
      readonly complete: boolean;
      /** Zero items, and that IS the answer. */
      readonly queryGap: boolean;
      readonly hasMore: boolean;
    };

/**
 * The store owns keyset continuation: it holds the server's opaque cursor and accumulates
 * pages, so `loadMore()` takes no argument and the surface never handles a cursor. `list()`
 * returns everything loaded so far, in deterministic server order. The client never sorts.
 */
export type ProductionSynthesizedMemoryStore = ObservableStore & {
  list(): Promise<readonly SynthesizedMemoryItem[]>;
  recall(): SynthesizedRecallState;
  hasMore(): boolean;
  loadMore(): Promise<void>;
};
