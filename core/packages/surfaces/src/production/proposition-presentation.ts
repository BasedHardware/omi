import type { MessageKey } from "@omi-core/i18n";
import type { SynthesizedMemoryItem, SynthesizedRecallReason, SynthesizedRecallState } from "@omi-core/contracts";

/** Compile-time proof that a narrow key union really exists in the catalog. */
type CatalogKey<T extends MessageKey> = T;

/**
 * Narrow key unions rather than bare `MessageKey`. `t()` demands an interpolation
 * argument whenever the key type is wide enough to include a placeholder message, so
 * narrowing here is what lets the component call `t(locale, key)` with a computed key and
 * still be checked against the catalog.
 */
export type CompletenessTitleKey = CatalogKey<
  | "memoriesPlatform.completeness.complete"
  | "memoriesPlatform.completeness.incomplete"
  | "memoriesPlatform.completeness.degraded"
  | "memoriesPlatform.completeness.partial"
>;

export type ReasonKey = CatalogKey<
  | "memoriesPlatform.reason.acceptedWorkPending"
  | "memoriesPlatform.reason.projectionStale"
  | "memoriesPlatform.reason.projectionUnavailable"
  | "memoriesPlatform.reason.projectionBypassed"
  | "memoriesPlatform.reason.sourceBound"
  | "memoriesPlatform.reason.timeBound"
  | "memoriesPlatform.reason.policyBound"
>;

export type LineageLabelKey = CatalogKey<
  | "memoriesPlatform.synthesisVersion"
  | "memoriesPlatform.inputDigest"
  | "memoriesPlatform.outputDigest"
>;

/**
 * Every rendering decision for the platform-generation Memories surface.
 *
 * Pure and free of value imports, so `node --test` executes it directly (Node 22 strips
 * types; the `import type` lines above erase). The component renders what these functions
 * return and makes no honesty judgement of its own — which is what lets the invariants be
 * tested against real inputs instead of against the component's source text.
 */

/** `unstated` is FE-CORE's `kind:"unknown"`: the server told us nothing, so we claim nothing. */
export type CompletenessNoticeKind = "unstated" | "complete" | "incomplete" | "degraded" | "partial";

export type CompletenessNotice = {
  readonly kind: CompletenessNoticeKind;
  readonly titleKey: CompletenessTitleKey | null;
  readonly reasonKeys: readonly ReasonKey[];
  readonly tone: "neutral" | "caution" | "warning";
};

const DEGRADED_REASONS: readonly SynthesizedRecallReason[] = [
  "projection_stale",
  "projection_unavailable",
  "projection_bypassed",
];
const PARTIAL_REASONS: readonly SynthesizedRecallReason[] = ["source_bound", "time_bound", "policy_bound"];

/**
 * Wire vocabulary to catalog copy. Explicit rather than computed: the ratified reasons are
 * snake_case and canonical message keys must be camelCase, so a template-built key would
 * be both unchecked and wrong.
 *
 * Typed as a TOTAL record over `SynthesizedRecallReason`. That is the drift guard: if the
 * ratified contract gains an eighth limitation reason, this file stops compiling until
 * someone writes copy for it. There is deliberately no "unrecognised reason" runtime path
 * — `parseSynthesizedPageJson` rejects a whole page whose reasons are not in the ratified
 * vocabulary, so such a page reaches this surface as `kind: "unknown"`, never as a known
 * state with a mystery reason. A count of unrecognised reasons would be unreachable code
 * describing a state the contract cannot produce.
 */
const REASON_KEYS: Readonly<Record<SynthesizedRecallReason, ReasonKey>> = {
  "accepted_work_pending": "memoriesPlatform.reason.acceptedWorkPending",
  "projection_stale": "memoriesPlatform.reason.projectionStale",
  "projection_unavailable": "memoriesPlatform.reason.projectionUnavailable",
  "projection_bypassed": "memoriesPlatform.reason.projectionBypassed",
  "source_bound": "memoriesPlatform.reason.sourceBound",
  "time_bound": "memoriesPlatform.reason.timeBound",
  "policy_bound": "memoriesPlatform.reason.policyBound",
};

/**
 * The precedence the ratified contract uses (`deriveCompletenessStatus` in
 * `contracts/ratified/src/projections/synthesized.ts`): degraded outranks incomplete
 * outranks partial.
 */
function deriveStatusFromReasons(reasons: readonly SynthesizedRecallReason[]): CompletenessNoticeKind {
  if (reasons.some((reason) => DEGRADED_REASONS.includes(reason))) return "degraded";
  if (reasons.includes("accepted_work_pending")) return "incomplete";
  if (reasons.some((reason) => PARTIAL_REASONS.includes(reason))) return "partial";
  return "complete";
}

function toneFor(kind: CompletenessNoticeKind): CompletenessNotice["tone"] {
  if (kind === "degraded") return "warning";
  if (kind === "complete" || kind === "unstated") return "neutral";
  return "caution";
}

/**
 * Absent metadata yields no claim, and a state carrying limitation reasons never renders
 * as complete even when its own `status` says so. Snapshot honesty (core hard rule 12)
 * makes completeness the exceptional claim, so the only direction this moves a status is
 * *down*.
 */
export function completenessNotice(recall: SynthesizedRecallState): CompletenessNotice {
  if (recall.kind === "unknown") {
    return { kind: "unstated", titleKey: null, reasonKeys: [], tone: "neutral" };
  }
  const reasons = recall.reasons ?? [];
  const kind = reasons.length > 0 ? deriveStatusFromReasons(reasons) : recall.status;
  return {
    kind,
    titleKey: `memoriesPlatform.completeness.${kind === "unstated" ? "partial" : kind}` as CompletenessTitleKey,
    reasonKeys: reasons.map((reason) => REASON_KEYS[reason]),
    tone: toneFor(kind),
  };
}

/**
 * Three distinct answers, and the surface must not collapse any pair of them:
 *  - `rows`             — there is something to show;
 *  - `query-gap`        — we searched and there is nothing (`queryGap`, a declared answer);
 *  - `recall-unknown`   — we do not know yet (`kind:"unknown"`), which is not an answer;
 *  - `empty-projection` — a known page that is simply empty without declaring a gap.
 */
export type EmptyPresentation = "rows" | "query-gap" | "recall-unknown" | "empty-projection";

export function emptyPresentation(
  itemCount: number,
  recall: SynthesizedRecallState,
): EmptyPresentation {
  if (itemCount > 0) return "rows";
  if (recall.kind === "unknown") return "recall-unknown";
  return recall.queryGap ? "query-gap" : "empty-projection";
}

export type PaginationAffordance = {
  readonly canLoadMore: boolean;
  /** Only true when the server actually declared this window terminates. */
  readonly terminal: boolean;
};

/**
 * With no recall envelope the surface offers no continuation AND makes no end-of-list
 * claim — "you have reached the end" is a completeness claim and needs server evidence.
 */
export function paginationAffordance(recall: SynthesizedRecallState): PaginationAffordance {
  if (recall.kind === "unknown") return { canLoadMore: false, terminal: false };
  return { canLoadMore: recall.hasMore, terminal: !recall.hasMore };
}

export type LineageRow = { readonly labelKey: LineageLabelKey; readonly value: string };

/** Empty when the server supplied no lineage. Digests are never synthesized client-side. */
export function lineageRows(item: SynthesizedMemoryItem): readonly LineageRow[] {
  const provenance = item.provenance;
  if (!provenance) return [];
  return [
    { labelKey: "memoriesPlatform.synthesisVersion", value: provenance.synthesisVersion },
    { labelKey: "memoriesPlatform.inputDigest", value: provenance.inputDigest },
    { labelKey: "memoriesPlatform.outputDigest", value: provenance.outputDigest },
  ];
}

export type CitationSummary = {
  /** False when the field was absent — which is not the same as "zero citations". */
  readonly stated: boolean;
  readonly count: number;
};

/**
 * Citation refs are opaque server handles with no meaning to a reader, so the surface
 * reports how many were cited rather than printing the refs themselves.
 */
export function citationSummary(item: SynthesizedMemoryItem): CitationSummary {
  const citations = item.citations;
  if (!citations) return { stated: false, count: 0 };
  return { stated: true, count: citations.length };
}

/**
 * Filters the rows already loaded into this client. It is not a backend search and the
 * surface's label must not claim to be one (glass-parity provisional ruling 4).
 */
export function filterLoadedPropositions(
  items: readonly SynthesizedMemoryItem[],
  query: string,
  locale: string,
): readonly SynthesizedMemoryItem[] {
  const needle = query.trim().toLocaleLowerCase(locale);
  if (!needle) return items;
  return items.filter((item) => item.text.toLocaleLowerCase(locale).includes(needle));
}
