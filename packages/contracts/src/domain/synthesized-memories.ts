/**
 * The PLATFORM generation's memory READ model — surface-facing declarations.
 *
 * This is not a second spelling of `Memory` (`./memories.ts`). It is a
 * different record class, and the difference is the point:
 *
 * - `Memory` is the LEGACY editable record: content, category, visibility,
 *   review verdict, lock state, created/updated timestamps. A surface may
 *   patch it.
 * - `SynthesizedMemoryItem` is the RATIFIED read projection served by the new
 *   backend (`@omi-core/ratified-contracts` 0.1.1): a stable opaque render id,
 *   exactly one synthesized `text` field, and optional non-presentational
 *   lineage. There is nothing to patch, and the ratified conformance corpus
 *   (`contracts/ratified/fixtures/forbidden-public-fields.mjs`) actively
 *   REJECTS a payload carrying `content`, `category`, `visibility`,
 *   `reviewed`, `review`, `locked`, `tags`, `order`, `summary`, `transcript`,
 *   `store`, `owner`, or any generation/commit coordinate.
 *
 * So mapping one onto the other is not an implementation detail we get to
 * choose. Widening `Memory` to cover both would require inventing values for
 * fields the server refuses to send — and a fabricated `locked: false` is the
 * exact locked-memory data-loss class documented in
 * `packages/adapters-legacy/src/memories.ts`. Two record classes, two ports.
 *
 * These declarations deliberately drop the ratified package's opaque brands
 * (`SynthesizedItemId`, `SynthesizedText`, `CitationRef`, `Sha256Digest`).
 * Brands are a PARSING discipline for the wire boundary, which is
 * `packages/adapters-platform`'s job; a surface that has been handed a value
 * past that boundary should not need the ratified package on its dependency
 * path to render a string. The adapter is the only thing that may construct
 * these, and it constructs them only from a page that satisfied the ratified
 * validator.
 */

/** One synthesized memory as a surface renders it. Read-only by construction. */
export interface SynthesizedMemoryItem {
  /**
   * Stable opaque render id. NOT a `RecordId` and NOT parseable with
   * `parseRecordId`: it is server-owned, may carry a namespace or a hash, and
   * has no slug/legacy-UUID grammar. Treat it as a key, never as an address.
   */
  readonly id: string;
  /** The one and only presentation field. Non-empty by contract. */
  readonly text: string;
  /** Opaque references only — never raw evidence, never ownership coordinates. */
  readonly citations?: readonly string[];
  readonly provenance?: SynthesizedMemoryProvenance;
}

/** Closed, store-agnostic synthesis lineage. Non-presentational. */
export interface SynthesizedMemoryProvenance {
  readonly synthesisVersion: string;
  /** Lowercase 64-char SHA-256 hex, validated at the wire boundary. */
  readonly inputDigest: string;
  readonly outputDigest: string;
}

/**
 * How much of the user's memory the loaded window actually covers.
 *
 * HARD RULE 12, encoded in the type system. `kind: "unknown"` exists because
 * the absence of a completeness envelope is NOT evidence of completeness. An
 * origin that predates the ratified contract, a body we could not parse, a
 * transport that never answered — all of these produce `"unknown"`, and there
 * is deliberately no way to spell "we saw nothing, therefore there is
 * nothing". A surface must be unable to render "unknown" and "complete and
 * empty" the same way without writing the branch that says so.
 *
 * The `complete` flag inside `"known"` is the SERVER'S declaration, carried
 * verbatim. A client never derives it from item counts, page fullness, or a
 * short page.
 */
export type SynthesizedRecallState =
  | { readonly kind: "unknown" }
  | {
      readonly kind: "known";
      /**
       * The ratified completeness status, already reduced by the contract's
       * own precedence rule `degraded > incomplete > partial > complete`.
       */
      readonly status: SynthesizedRecallStatus;
      /**
       * Every applicable limitation, not just the winning family. The
       * contract requires lower-precedence reasons to stay serialized rather
       * than be discarded, so a surface can explain a `degraded` page that is
       * also `source_bound`.
       */
      readonly reasons: readonly SynthesizedRecallReason[];
      /** `status === "complete"`, restated so a caller cannot misread it. */
      readonly complete: boolean;
      /**
       * The server searched and found nothing for this query — zero items IS
       * the answer. Distinct from `kind: "unknown"` (we do not know) and from
       * a page that simply has more to fetch.
       */
      readonly queryGap: boolean;
      readonly hasMore: boolean;
    };

export type SynthesizedRecallStatus = "complete" | "incomplete" | "degraded" | "partial";

/**
 * The ratified `LimitationReason` union, restated. Kept as a closed union
 * rather than `string` so a surface's exhaustive switch breaks at compile time
 * when the contract adds a reason — which is the moment a human must decide
 * how to explain it, not a moment to fall through to a generic message.
 */
export type SynthesizedRecallReason =
  | "accepted_work_pending"
  | "projection_stale"
  | "projection_unavailable"
  | "projection_bypassed"
  | "source_bound"
  | "time_bound"
  // domain-pending(DIV-DOMCORE-006)
  | "policy_bound";

/** The state a store reports before its first read has resolved. */
export const UNKNOWN_SYNTHESIZED_RECALL: SynthesizedRecallState = { kind: "unknown" };
