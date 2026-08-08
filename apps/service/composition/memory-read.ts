// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMX-001)
// domain-pending(DIV-DOMX-006)
import { createHash, createHmac } from "node:crypto";

import {
  computeApplicationSynthesizedProjectionGenerationDigest,
  readApplicationSynthesizedPageWithAttestation,
  type ApplicationReadAttestation,
  type ApplicationReadCoherentCoordinates,
  type ApplicationReadPorts,
  type ApplicationReadSnapshotAttestation,
  type ApplicationRecallGenerationDigests,
  type ApplicationSynthesizedPageRequest,
} from "../../../core/retrieve/application-read";
import {
  inspectApplicationMemoryReadAuthorization,
  readAfterApplicationAuthorization,
  type ApplicationMemoryReadAuthorizationRequest,
} from "../../../core/retrieve/authorization-boundary";
import type {
  AcceptedCoverageState,
  ContentSafeRecallTrace,
  RecallCompletenessInput,
  StmCoverageState,
} from "../../../core/retrieve/recall-integrity";
import { renderStructuralTree, type RenderNode } from "../../../core/retrieve/render";
import { buildDeterministicAnchors } from "../../../core/retrieve/tree";
import type { GraphSnapshot } from "../../../core/retrieve";
import {
  asOpaqueVisibleKeyset,
  issueMcpCursor,
  verifyMcpCursor,
  type McpCursorBindings,
  type McpCursorSigningKeyset,
} from "../../mcp/cursor";
import { createReaderScopedOpaqueCodecs } from "../codecs/opaque-refs";
import { createQaDeterministicSynthesizer } from "./qa-synthesizer";

/**
 * The composition root for the application memory read path.
 *
 * Every layer of this flow already existed and was individually green, but
 * nothing joined them: `readApplicationSynthesizedPage`, the SQLite QA loader,
 * and the signed cursor were each referenced only by their own unit tests. This
 * module is the single place where the authorization boundary, the projection,
 * the deterministic render set, the opaque codecs, and the signed cursor are
 * wired into one real read. There must be exactly one of these.
 *
 * SQLite is QA-only here and is never production authority. No production
 * store, concurrency model, or deployment topology is selected by this file.
 */

/** Version tag for the cursor policy this composition binds into every cursor. */
const CURSOR_POLICY_VERSION = "application-read-cursor-policy-v1";
const RENDER_STRATEGY = "application-read-qa";
const RENDER_MODEL_VERSION = "qa-deterministic-synthesizer-v1";
const RENDER_PROMPT_VERSION = "qa-prompt-v1";
const RENDER_POLICY_VERSION = "qa-policy-v1";
const RENDER_SCHEMA_VERSION = "qa-schema-v1";

/**
 * Which structural view becomes a served memory.
 *
 * `buildDeterministicAnchors` produces temporal, entity, and source views over
 * the same claims, so serving every node would show one proposition several
 * times over. There is also NO view that is one-node-per-proposition: the
 * temporal view is hierarchical (year -> month -> day) and its nodes aggregate
 * every claim beneath them, while entity and source nodes group by entity and
 * by capture session. A "memory" in this model is therefore an aggregation that
 * was synthesized, not a single claim.
 *
 * This composition serves temporal LEAF nodes - the deepest temporal grouping,
 * one per local day. That choice is aligned with a memories timeline and with
 * the local-day grouping the client performs, but it is a QA composition
 * choice, not a ratified product rule. It is reported in
 * blocked/BE-SURFACE-served-node-selection.md. The recall core makes the same
 * disclaimer about its own ordering.
 */
// domain-pending(DIV-DOMCORE-008)
const SERVED_VIEW_KIND = "temporal";

/**
 * Re-roots a value onto standard object prototypes.
 *
 * The SQLite QA loader hardens its output with null-prototype records, but
 * `application-read.ts` rejects any object whose prototype is not
 * `Object.prototype`. Note that `authorization-boundary.ts` ACCEPTS null
 * prototypes, so those two core modules disagree with each other; the mismatch
 * was invisible while nothing connected the driver to the read path. The
 * composition adapts rather than weakening either boundary. Any future durable
 * driver must satisfy the stricter of the two.
 */
const toStandardPrototypeJson = <Value>(value: Value): Value => structuredClone(value);

const sha256Hex = (value: string): string => createHash("sha256").update(value, "utf8").digest("hex");

const compareStrings = (left: string, right: string): number =>
  left < right ? -1 : left > right ? 1 : 0;

const canonicalJson = (value: unknown): string => {
  if (value === null || typeof value === "boolean" || typeof value === "number"
    || typeof value === "string") return JSON.stringify(value) ?? "null";
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (typeof value !== "object") return "null";
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record).sort(compareStrings)
    .map((key) => `${JSON.stringify(key)}:${canonicalJson(record[key])}`).join(",")}}`;
};

/**
 * The QA coherent load this composition consumes. It is structurally the
 * `SqliteQaRecallLoad` produced by `createSqliteQaRecallLoader`, restated here
 * so the composition depends on the shape rather than on the SQLite driver.
 */
// domain-pending(DIV-DOMCORE-006)
export interface CoherentQaLoad {
  readonly owner_account_id: string;
  readonly account_timezone: string;
  readonly durable_snapshot: GraphSnapshot;
  readonly stm_rows: readonly { readonly id: string }[];
  readonly accepted_state: {
    readonly state: AcceptedCoverageState;
    readonly declared_frontier: string | null;
    readonly searched_frontier: string | null;
    readonly candidates: readonly unknown[];
  };
  readonly internal_coverage: {
    readonly durable: {
      readonly graph_generation: string | number;
      readonly ledger_head_digest: string;
    };
    readonly stm: {
      readonly eligible_items: number;
      readonly selected_items: number;
      readonly has_more: boolean;
      readonly bounds_reached: readonly ("item_limit" | "byte_limit")[];
    };
    readonly accepted: { readonly state: AcceptedCoverageState };
  };
  readonly coherent_snapshot_digest: string;
}

export interface MemoryReadCompositionConfig {
  /** Zero-argument coherent loader; called fresh for every internal revalidation. */
  readonly loadCoherent: () => CoherentQaLoad;
  readonly authorizationRequest: ApplicationMemoryReadAuthorizationRequest;
  /** HMAC root for the reader-scoped opaque handles. QA-supplied; never a production secret. */
  readonly codecRootSecret: Uint8Array;
  readonly cursorSigningKeyset: McpCursorSigningKeyset;
  readonly cursorTtlSeconds: number;
  /**
   * The authoritative read timestamp for this snapshot. Passed in, never read
   * from a clock, so the two internal revalidation loads agree and the flow
   * stays hermetic.
   */
  readonly readTimestampEpochSeconds: number;
  readonly traceSink: (trace: ContentSafeRecallTrace) => void | Promise<void>;
}

/**
 * Maps QA coverage onto the recall completeness envelope HONESTLY.
 *
 * The two rules that matter, both of which a plausible implementation gets
 * wrong in the direction of over-claiming:
 *
 * 1. The short-term overlay is NOT searchable through this path. The recall
 *    core refuses a synthesized STM frontier because STM has no produced-render
 *    authority boundary yet. So when eligible STM rows exist, the envelope must
 *    say the overlay was bypassed - reporting `no_eligible` would present
 *    durable-only recall as complete recall, which is exactly the false
 *    `complete: true` that costs user data.
 * 2. Accepted-work coverage may only be reported as `no_eligible` when the load
 *    actually declares there is no eligible accepted work. Anything that would
 *    imply a searched accepted frontier is downgraded to `bypassed`, because
 *    this composition genuinely did not search it.
 */
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
const buildCoverage = (
  load: CoherentQaLoad,
  encodeFrontier: (internalFrontier: string) => string,
): RecallCompletenessInput => {
  // The declared frontier reaches the wire UNFILTERED. Unlike item, citation and
  // trace references it does not pass through the read core's opaque-ref codecs
  // or its forbidden-ref leak check - `mapCompleteness` copies it straight into
  // the page. Emitting the raw ledger-head digest here would therefore publish
  // an unkeyed digest of internal coordinates that is identical for every
  // reader and correlatable across them. Reader-scoping it costs nothing and
  // keeps the frontier stable for the reader that actually uses it.
  const declaredFrontier = encodeFrontier(
    `durable:${load.internal_coverage.durable.ledger_head_digest}`,
  );

  // Accepted synthesis is not performed here. Only a declared no-eligible state
  // survives as no_eligible; every other state becomes an explicit limitation.
  const acceptedState: AcceptedCoverageState =
    load.internal_coverage.accepted.state === "no_eligible" ? "no_eligible" : "bypassed";

  // The overlay is never searched by this path. Silence about a non-empty
  // overlay would be a false completeness claim.
  const stmState: StmCoverageState =
    load.internal_coverage.stm.eligible_items === 0 ? "no_eligible" : "bypassed";

  return Object.freeze({
    declared_frontier: declaredFrontier,
    accepted: Object.freeze({ state: acceptedState, searched_frontier: null }),
    stm: Object.freeze({ state: stmState, searched_frontier: null }),
    projection_freshness: "fresh" as const,
    intentional_bounds: Object.freeze([]),
  });
};

const buildGenerations = (
  load: CoherentQaLoad,
  authorizationDigest: string,
  synthesizedProjectionGenerationDigest: string,
): ApplicationRecallGenerationDigests => Object.freeze({
  authorization_generation_digest: authorizationDigest,
  synthesized_projection_generation_digest: synthesizedProjectionGenerationDigest,
  durable_generation_digest: sha256Hex(canonicalJson({
    kind: "durable-generation",
    graph_generation: load.internal_coverage.durable.graph_generation,
    ledger_head_digest: load.internal_coverage.durable.ledger_head_digest,
  })),
  // No overlay is projected into the served page; its generation still binds
  // the cursor so a cursor cannot survive an overlay change unnoticed.
  overlay_generation_digest: sha256Hex(canonicalJson({
    kind: "overlay-generation",
    eligible_items: load.internal_coverage.stm.eligible_items,
    selected_items: load.internal_coverage.stm.selected_items,
    has_more: load.internal_coverage.stm.has_more,
    bounds_reached: [...load.internal_coverage.stm.bounds_reached].sort(compareStrings),
  })),
  declared_generation_digest: sha256Hex(canonicalJson({
    kind: "declared-generation",
    ledger_head_digest: load.internal_coverage.durable.ledger_head_digest,
  })),
  accepted_generation_digest: sha256Hex(canonicalJson({
    kind: "accepted-generation",
    state: load.internal_coverage.accepted.state,
    declared_frontier: load.accepted_state.declared_frontier,
    searched_frontier: load.accepted_state.searched_frontier,
  })),
  stm_generation_digest: sha256Hex(canonicalJson({
    kind: "stm-generation",
    eligible_items: load.internal_coverage.stm.eligible_items,
    row_ids: load.stm_rows.map((row) => row.id).sort(compareStrings),
  })),
});

const buildReadCoordinates = (
  load: CoherentQaLoad,
  authorization: ApplicationMemoryReadAuthorizationRequest,
  authorizationDigest: string,
  persistedGrantStateDigest: string,
  readTimestampEpochSeconds: number,
): ApplicationReadCoherentCoordinates => Object.freeze({
  owner_identity_digest: sha256Hex(`owner:${load.owner_account_id}`),
  application_identity_digest: sha256Hex(`app:${authorization.credential.app_id ?? ""}`),
  credential_identity_digest: sha256Hex(`credential:${authorization.credential.key_id ?? ""}`),
  // The core cross-checks this against the authorization generation digest.
  authorization_state_digest: authorizationDigest,
  grant_state_digest: persistedGrantStateDigest,
  account_head_digest: sha256Hex(canonicalJson({
    kind: "account-head",
    ledger_head_digest: load.internal_coverage.durable.ledger_head_digest,
  })),
  authorized_graph_digest: sha256Hex(canonicalJson({
    kind: "authorized-graph",
    graph_generation: load.internal_coverage.durable.graph_generation,
  })),
  coherent_projection_commit_digest: sha256Hex(`coherent:${load.coherent_snapshot_digest}`),
  // This read applies the application-default visibility, no filter, and no
  // query. They are still distinct bound coordinates so that introducing any of
  // them later invalidates outstanding cursors rather than silently reusing them.
  visibility_digest: sha256Hex("visibility:application-default-synthesized-v1"),
  filter_digest: sha256Hex("filter:none-v1"),
  query_digest: sha256Hex("query:none-v1"),
  source_digest: sha256Hex("source:durable-only-v1"),
  read_mode_digest: sha256Hex("read-mode:synthesized-latest-projection-v1"),
  read_timestamp_epoch_seconds: readTimestampEpochSeconds,
});

/**
 * Projects a read attestation onto the fifteen signed cursor bindings.
 *
 * The binding set is fixed at fifteen fields, but the attestation carries more
 * state than that - the coverage envelope, the projected content digest, and
 * the durable/overlay/declared/accepted/STM generations. Those residual fields
 * are folded into `cursor_policy_digest`. Without that fold a cursor minted
 * against one coverage state would verify against a different one, which is a
 * replay across snapshots: a page-two request could silently be answered from a
 * snapshot whose completeness no longer matches the page-one the client saw.
 */
// domain-pending(DIV-DOMX-001)
const attestationToCursorBindings = (
  attestation: ApplicationReadSnapshotAttestation,
): McpCursorBindings => Object.freeze({
  owner_digest: attestation.owner_identity_digest,
  app_digest: attestation.application_identity_digest,
  credential_key_digest: attestation.credential_identity_digest,
  authorization_generation_digest: attestation.authorization_state_digest,
  grant_generation_digest: attestation.grant_state_digest,
  account_generation_digest: attestation.account_head_digest,
  graph_generation_digest: attestation.authorized_graph_digest,
  projection_generation_digest: attestation.synthesized_projection_generation_digest,
  projection_commit_digest: attestation.coherent_projection_commit_digest,
  visibility_digest: attestation.visibility_digest,
  filter_digest: attestation.filter_digest,
  query_digest: attestation.query_digest,
  cursor_policy_digest: sha256Hex(canonicalJson({
    policy: CURSOR_POLICY_VERSION,
    projected_content_digest: attestation.projected_content_digest,
    durable_generation_digest: attestation.durable_generation_digest,
    overlay_generation_digest: attestation.overlay_generation_digest,
    declared_generation_digest: attestation.declared_generation_digest,
    accepted_generation_digest: attestation.accepted_generation_digest,
    stm_generation_digest: attestation.stm_generation_digest,
    coverage: attestation.coverage,
  })),
  source_digest: attestation.source_digest,
  read_mode_digest: attestation.read_mode_digest,
});

/** Selects the produced renders this composition is willing to serve as memories. */
const selectServedRenders = (
  renders: readonly RenderNode[],
  nodeViewKinds: ReadonlyMap<string, { readonly view_kind: string; readonly isLeaf: boolean }>,
): readonly RenderNode[] => renders
  .filter((render) => {
    const node = nodeViewKinds.get(render.node_id);
    if (!node || node.view_kind !== SERVED_VIEW_KIND || !node.isLeaf) return false;
    // Only grounded, current renders may be served. An empty, failed, or stale
    // render is not a memory - and presenting one as absence would be a lie.
    return render.status === "ready" && render.render_hash !== null && !render.stale;
  })
  .slice()
  .sort((left, right) => compareStrings(left.node_id, right.node_id));

export interface PreparedMemoryRead {
  readonly ports: ApplicationReadPorts;
  /** How many produced renders this snapshot is willing to serve, before paging. */
  readonly servableRenderCount: number;
}

export interface MemoryPageResult {
  readonly canonical_json: string;
  readonly attestation: ApplicationReadAttestation;
}

/**
 * Builds the read ports for one snapshot.
 *
 * Renders must be produced BEFORE the read begins, because `loadDurableRenders`
 * is synchronous while rendering is asynchronous. The pre-rendered set is
 * therefore memoized and returned on every call. This is safe, and is checked:
 * the read core recomputes the produced-render-set generation receipt on each
 * internal load and refuses the page if it disagrees, so a snapshot that
 * changed underneath the pre-render fails closed rather than serving stale
 * content.
 */
export const prepareMemoryRead = async (
  config: MemoryReadCompositionConfig,
): Promise<PreparedMemoryRead> => {
  const authorization = config.authorizationRequest;
  // Runs the same gate the read will run, so a denial surfaces before any
  // render work happens rather than after.
  const evidence = inspectApplicationMemoryReadAuthorization(authorization);

  const codecs = createReaderScopedOpaqueCodecs({
    root_secret: config.codecRootSecret,
    reader_projection_digest: evidence.principal_digest,
  });

  /**
   * Reader-scoped, domain-separated frontier handle. Same construction as the
   * opaque-ref codecs (per-reader subkey, distinct label) but with the
   * `frontier-v1:` grammar the ratified parser expects.
   */
  const frontierSubkey = createHmac("sha256", Buffer.from(config.codecRootSecret))
    .update("omi.service.opaque-frontier.v1", "ascii")
    .update("\0", "ascii")
    .update(evidence.principal_digest, "ascii")
    .digest();
  const encodeFrontier = (internalFrontier: string): string =>
    `frontier-v1:${createHmac("sha256", frontierSubkey).update(internalFrontier, "utf8").digest("hex")}`;

  const preRenderLoad = config.loadCoherent();
  const preRenderProjection = readAfterApplicationAuthorization(authorization, () => ({
    snapshot: toStandardPrototypeJson(preRenderLoad.durable_snapshot),
    options: { account_timezone: preRenderLoad.account_timezone },
  }));

  const tree = buildDeterministicAnchors(preRenderProjection);
  const nodeViewKinds = new Map(tree.nodes.map((node) => [node.node_id, {
    view_kind: node.view_kind as string,
    isLeaf: node.child_node_ids.length === 0,
  }]));
  const allRenders = await renderStructuralTree(
    tree,
    preRenderProjection,
    createQaDeterministicSynthesizer(),
    {
      strategy: RENDER_STRATEGY,
      model_version: RENDER_MODEL_VERSION,
      prompt_version: RENDER_PROMPT_VERSION,
      policy_version: RENDER_POLICY_VERSION,
      schema_version: RENDER_SCHEMA_VERSION,
    },
  );
  const servedRenders = selectServedRenders(allRenders, nodeViewKinds);
  const synthesizedProjectionGenerationDigest =
    computeApplicationSynthesizedProjectionGenerationDigest(preRenderProjection, servedRenders);

  const ports: ApplicationReadPorts = {
    resolveAttempt: () => ({
      authorization_request: authorization,
      load_coherent: () => {
        const load = config.loadCoherent();
        return {
          projection_load: {
            snapshot: toStandardPrototypeJson(load.durable_snapshot),
            options: { account_timezone: load.account_timezone },
          },
          coverage: buildCoverage(load, encodeFrontier),
          generations: buildGenerations(
            load,
            evidence.authorization_digest,
            synthesizedProjectionGenerationDigest,
          ),
          read_coordinates: buildReadCoordinates(
            load,
            authorization,
            evidence.authorization_digest,
            evidence.persisted_grant_state_digest,
            config.readTimestampEpochSeconds,
          ),
        };
      },
    }),
    // The read core rebinds every returned render against the freshly projected
    // input and recomputes the generation receipt, so returning the memoized
    // set cannot smuggle in renders from a different projection.
    loadDurableRenders: () => [...servedRenders],
    encodeVisibleKey: codecs.encodeVisibleKey,
    encodeItemRef: codecs.encodeItemRef,
    encodeCitationRef: codecs.encodeCitationRef,
    encodeTraceRef: codecs.encodeTraceRef,
    verifyCursor: (cursor, attestation) => verifyMcpCursor(
      cursor,
      {
        bindings: attestationToCursorBindings(attestation),
        // The signed page read timestamp, never an ambient decode time.
        now_epoch_seconds: attestation.read_timestamp_epoch_seconds,
      },
      config.cursorSigningKeyset,
    ).last_visible_key,
    issueCursor: (lastVisibleKey, attestation) => issueMcpCursor(
      {
        last_visible_key: asOpaqueVisibleKeyset(lastVisibleKey),
        bindings: attestationToCursorBindings(attestation),
        issued_at_epoch_seconds: attestation.read_timestamp_epoch_seconds,
        ttl_seconds: config.cursorTtlSeconds,
      },
      config.cursorSigningKeyset,
    ),
    traceSink: config.traceSink,
  };

  return Object.freeze({ ports, servableRenderCount: servedRenders.length });
};

/** Reads one page of canonical ratified JSON through the prepared ports. */
export const readMemoryPage = async (
  request: ApplicationSynthesizedPageRequest,
  prepared: PreparedMemoryRead,
): Promise<MemoryPageResult> =>
  readApplicationSynthesizedPageWithAttestation(request, prepared.ports);
