import { createHmac } from "node:crypto";
import { isProxy } from "node:util/types";

import { parseAttributionBeliefRevision } from "../../../core/consolidate/attribution-belief";
import { attributionCalibrationRequestDigest } from
  "../../../core/consolidate/attribution-calibration";
import { sha256CanonicalRedacted } from "../../../core/ledger";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  materializeListenAttributionBeliefInputs,
  parseListenAttributionBeliefInput,
  type ListenAttributionBeliefInput,
} from "../listen/attribution-belief-input";
import {
  listenAttributionBeliefInputRef,
  listenAttributionBeliefInputStageRequestDigest,
  materializeListenAttributionBeliefInputSet,
  type StoredListenAttributionBeliefInput,
} from "../listen/attribution-belief-input-source";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import {
  assertVerifiedMemoryEvaluationResult,
  type MemoryEvaluationResult,
} from "../stores/memory-shadow-result-repository";
import {
  ATTRIBUTION_BELIEF_SHADOW_RESULT_VERSION,
} from "./attribution-belief-shadow-producer";
import {
  parseMemoryEvaluationCohort,
  type MemoryEvaluationCohortManifest,
} from "./memory-evaluation-statistics";
import {
  formationWorkInputSnapshotDigest,
} from "./formation-work-input-repository";
import {
  parseFormationInputSnapshot,
  type FormationInputSnapshot,
} from "./formation-work-producer";

const SHEET_VERSION = "listen-attribution-blind-sheet-v1" as const;
const KEY_VERSION = "listen-attribution-blind-key-v1" as const;
const LABELS_VERSION = "listen-attribution-blind-labels-v1" as const;
const PROTOCOL_VERSION = "listen-source-owner-truth-v1" as const;
const CAPABILITY = "memories.experiments.shadow";
const MAX_UNITS = 10_000;
const MAX_RESULTS = 200_000;
const DIGEST = /^[a-f0-9]{64}$/;
const ROW_REF = /^labr1_[a-f0-9]{64}$/;
const SHEET_REF = /^labs1_[a-f0-9]{64}$/;
const RESULT_REF = /^msr1_[a-f0-9]{64}$/;
const INPUT_REF = /^labinput1_[a-f0-9]{64}$/;
const OBSERVATION_REF = /^obsref1_[a-f0-9]{64}$/;
const GRADER_REF = /^meg1_[a-f0-9]{64}$/;

export type ListenAttributionTruthLabel = "owner" | "non_owner" | "unclear";

export interface ListenAttributionBlindContext {
  readonly input_ref: string;
  readonly stored_input: Readonly<StoredListenAttributionBeliefInput>;
  readonly snapshot: Readonly<FormationInputSnapshot>;
}

export interface ListenAttributionBlindSheetSegment {
  readonly ordinal: number;
  readonly text: string;
  readonly target: boolean;
}

export interface ListenAttributionBlindSheetRow {
  readonly ordinal: number;
  readonly row_ref: string;
  readonly segments: readonly Readonly<ListenAttributionBlindSheetSegment>[];
}

export interface ListenAttributionBlindSheet {
  readonly version: typeof SHEET_VERSION;
  readonly grading_protocol_version: typeof PROTOCOL_VERSION;
  readonly sheet_ref: string;
  readonly cohort_digest: string;
  readonly row_count: number;
  readonly rows: readonly Readonly<ListenAttributionBlindSheetRow>[];
  readonly hidden_key_digest: string;
  readonly blind_sheet_digest: string;
}

export interface ListenAttributionBlindKeyMapping {
  readonly row_ref: string;
  readonly input_ref: string;
  readonly observation_ref: string;
  readonly observation_content_digest: string;
  readonly result_refs: readonly string[];
}

export interface ListenAttributionBlindKey {
  readonly version: typeof KEY_VERSION;
  readonly cohort_digest: string;
  readonly result_count: number;
  readonly mappings: readonly Readonly<ListenAttributionBlindKeyMapping>[];
  readonly hidden_key_digest: string;
}

export interface ListenAttributionBlindArtifacts {
  readonly sheet: Readonly<ListenAttributionBlindSheet>;
  readonly hidden_key: Readonly<ListenAttributionBlindKey>;
}

export interface ListenAttributionBlindHumanGrade {
  readonly row_ref: string;
  readonly label: ListenAttributionTruthLabel;
}

export interface ListenAttributionBlindLabels {
  readonly version: typeof LABELS_VERSION;
  readonly grading_protocol_version: typeof PROTOCOL_VERSION;
  readonly grader_session_ref: string;
  readonly cohort_digest: string;
  readonly blind_sheet_digest: string;
  readonly hidden_key_digest: string;
  readonly labels: readonly Readonly<{
    row_ref: string;
    input_ref: string;
    observation_ref: string;
    result_refs: readonly string[];
    label: ListenAttributionTruthLabel;
  }>[];
  readonly labels_digest: string;
}

const fail = (code: string): never => {
  throw new TypeError(`Listen attribution blind calibration ${code}`);
};
const compare = (left: string, right: string): number => left < right ? -1 : left > right ? 1 : 0;

const exactRecord = (value: unknown, keys: readonly string[], code: string): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const actual = Reflect.ownKeys(descriptors);
  const expected = [...keys].sort();
  if (actual.some((key) => typeof key !== "string") || actual.length !== expected.length
    || (actual as string[]).sort().some((key, index) => key !== expected[index])) fail(code);
  const output: Record<string, unknown> = {};
  for (const key of expected) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail(code);
    output[key] = descriptor.value;
  }
  return output;
};

const exactArray = (
  value: unknown,
  minimum: number,
  maximum: number,
  code: string,
): readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype
    || value.length < minimum || value.length > maximum) fail(code);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  if (Reflect.ownKeys(descriptors).length !== value.length + 1) fail(code);
  const output: unknown[] = [];
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = descriptors[String(index)];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail(code);
    output.push(descriptor.value);
  }
  return output;
};

const ref = (value: unknown, pattern: RegExp, code: string): string => {
  if (typeof value !== "string" || !pattern.test(value)) fail(code);
  return value;
};

const integer = (value: unknown, maximum: number, code: string): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 0 || (value as number) > maximum) fail(code);
  return value as number;
};

const text = (value: unknown, maximum: number, code: string): string => {
  if (typeof value !== "string" || value.length === 0 || value.length > maximum
    || /[\p{Cc}\p{Cs}]/u.test(value)) fail(code);
  return value;
};

const hmac = (secret: Uint8Array, value: unknown): string => createHmac("sha256", secret)
  .update(JSON.stringify(value)).digest("hex");

const unique = (values: readonly string[], code: string): void => {
  if (new Set(values).size !== values.length) fail(code);
};

const storedInput = (value: unknown): Readonly<StoredListenAttributionBeliefInput> => {
  const row = exactRecord(value, [
    "version", "owner_account_id", "account_epoch", "formation_work_id",
    "source_snapshot_digest", "set_digest", "input_count", "input_ordinal",
    "input_ref", "input_digest", "stage_request_digest", "input",
  ], "invalid_context");
  if (row["version"] !== "stored-listen-attribution-belief-input-v1") fail("invalid_context");
  const input = parseListenAttributionBeliefInput(row["input"]);
  const parsed = Object.freeze({
    version: row["version"],
    owner_account_id: row["owner_account_id"],
    account_epoch: row["account_epoch"],
    formation_work_id: row["formation_work_id"],
    source_snapshot_digest: row["source_snapshot_digest"],
    set_digest: row["set_digest"],
    input_count: row["input_count"],
    input_ordinal: row["input_ordinal"],
    input_ref: row["input_ref"],
    input_digest: row["input_digest"],
    stage_request_digest: row["stage_request_digest"],
    input,
  }) as Readonly<StoredListenAttributionBeliefInput>;
  if (typeof parsed.owner_account_id !== "string" || !Number.isSafeInteger(parsed.account_epoch)
    || parsed.account_epoch < 0 || typeof parsed.formation_work_id !== "string"
    || !DIGEST.test(parsed.source_snapshot_digest) || !DIGEST.test(parsed.set_digest)
    || !DIGEST.test(parsed.input_digest) || !DIGEST.test(parsed.stage_request_digest)
    || !Number.isSafeInteger(parsed.input_count) || parsed.input_count < 1 || parsed.input_count > 2
    || !Number.isSafeInteger(parsed.input_ordinal) || parsed.input_ordinal < 0
    || parsed.input_ordinal >= parsed.input_count || !INPUT_REF.test(parsed.input_ref)
    || parsed.input.owner_account_id !== parsed.owner_account_id
    || parsed.input_digest !== sha256CanonicalContent(parsed.input)) fail("invalid_context");
  return parsed;
};

const normalizedBelief = (
  result: Readonly<MemoryEvaluationResult>,
  input: Readonly<ListenAttributionBeliefInput>,
) => {
  if (result.result_contract_version !== ATTRIBUTION_BELIEF_SHADOW_RESULT_VERSION) {
    fail("wrong_result_contract");
  }
  const row = exactRecord(result.normalized_result, [
    "version", "belief", "calibration_receipt",
  ], "invalid_result");
  if (row["version"] !== ATTRIBUTION_BELIEF_SHADOW_RESULT_VERSION) fail("invalid_result");
  const belief = parseAttributionBeliefRevision(row["belief"]);
  const receipt = exactRecord(row["calibration_receipt"], [
    "version", "request_digest", "response_digest", "result_digest",
    "calibration_contract_digest", "belief_revision_id",
  ], "invalid_result");
  const expectedRequestDigest = attributionCalibrationRequestDigest({
    owner_account_id: input.owner_account_id,
    belief_kind: input.belief_kind,
    about_ref: input.about_ref,
    observation_ref: input.observation_ref,
    observation_content_digest: input.observation_content_digest,
    graph_frontier: input.graph_frontier,
    hypothesis_candidates: input.hypothesis_candidates,
    evidence_factors: input.evidence_factors,
    attribution_contract_digest: input.attribution_contract_digest,
    aggregation_contract_digest: input.aggregation_contract_digest,
    calibration_contract_digest: result.execution_contract_digest,
    created_at_event_time: input.created_at_event_time,
    previous_revision: null,
  });
  const expectedResponseDigest = sha256CanonicalRedacted({
    probabilities: belief.hypotheses.map((hypothesis) => ({
      hypothesis_id: hypothesis.hypothesis_id,
      probability_micros: hypothesis.probability_micros,
    })),
  });
  if (receipt["version"] !== "attribution-calibration-receipt-v1"
    || receipt["request_digest"] !== expectedRequestDigest
    || receipt["response_digest"] !== result.response_digest
    || receipt["response_digest"] !== expectedResponseDigest
    || receipt["result_digest"] !== sha256CanonicalRedacted(belief)
    || receipt["calibration_contract_digest"] !== result.execution_contract_digest
    || receipt["belief_revision_id"] !== belief.belief_revision_id
    || typeof receipt["request_digest"] !== "string" || !DIGEST.test(receipt["request_digest"])) {
    fail("invalid_result");
  }
  return belief;
};

const evaluationInputCoordinate = (
  ownerAccountId: string,
  accountEpoch: number,
  inputRef: string,
  input: Readonly<ListenAttributionBeliefInput>,
): Readonly<{ input_digest: string; cohort_input_ref: string }> => {
  const sourceRefDigest = sha256CanonicalContent({
    contract_version: "memory-evaluation-source-ref-v1",
    owner_account_id: ownerAccountId,
    account_epoch: accountEpoch,
    source_kind: "formation_input_snapshot",
    source_ref: inputRef,
  });
  const inputDigest = sha256CanonicalContent({
    contract_version: "copied-memory-evaluation-input-v2",
    owner_account_id: ownerAccountId,
    account_epoch: accountEpoch,
    source_kind: "formation_input_snapshot",
    source_ref_digest: sourceRefDigest,
    input_frontier: input.graph_frontier,
    payload: input,
  });
  return Object.freeze({
    input_digest: inputDigest,
    cohort_input_ref: `mei1_${sha256CanonicalContent({
      contract_version: "memory-evaluation-export-input-ref-v1",
      owner_account_id: ownerAccountId,
      account_epoch: accountEpoch,
      input_frontier_digest: sha256CanonicalContent({
        contract_version: "memory-evaluation-frontier-ref-v1",
        input_frontier: input.graph_frontier,
      }),
      input_digest: inputDigest,
    })}`,
  });
};

const verifyBelief = (
  context: Readonly<AuthorizedLedgerWriteContext>,
  cohort: Readonly<MemoryEvaluationCohortManifest>,
  input: Readonly<ListenAttributionBeliefInput>,
  result: Readonly<MemoryEvaluationResult>,
  role: "baseline" | "candidate",
  repeatOrdinal: number,
  unit: Readonly<MemoryEvaluationCohortManifest["units"][number]>,
  inputRef: string,
): void => {
  if (result.owner_account_id !== context.account_id || result.account_epoch !== context.account_epoch
    || result.evaluation_run_id !== cohort.evaluation_run_ref
    || result.evaluation_mode !== cohort.evaluation_mode || result.evaluation_role !== role
    || result.repeat_ordinal !== repeatOrdinal || result.input_frontier !== input.graph_frontier) {
    fail("result_coordinate_mismatch");
  }
  const expectedAssignmentRef = `mea1_${sha256CanonicalContent({
    contract_version: "memory-evaluation-export-assignment-ref-v1",
    owner_account_id: result.owner_account_id,
    account_epoch: result.account_epoch,
    assignment_bundle_id: result.assignment_bundle_id,
  })}`;
  const expectedInput = evaluationInputCoordinate(
    result.owner_account_id, result.account_epoch, inputRef, input,
  );
  if (expectedAssignmentRef !== unit.assignment_bundle_ref
    || expectedInput.cohort_input_ref !== unit.input_ref
    || result.input_digest !== expectedInput.input_digest) {
    fail("result_coordinate_mismatch");
  }
  const belief = normalizedBelief(result, input);
  if (belief.owner_account_id !== input.owner_account_id || belief.belief_kind !== input.belief_kind
    || belief.about_ref !== input.about_ref || belief.observation_ref !== input.observation_ref
    || belief.observation_content_digest !== input.observation_content_digest
    || belief.graph_frontier !== input.graph_frontier
    || belief.attribution_contract_digest !== input.attribution_contract_digest
    || belief.aggregation_contract_digest !== input.aggregation_contract_digest
    || belief.calibration_contract_digest !== result.execution_contract_digest
    || sha256CanonicalContent(belief.evidence_factors) !== sha256CanonicalContent(input.evidence_factors)) {
    fail("result_input_mismatch");
  }
  const expectedCandidates = input.hypothesis_candidates
    .map((candidate) => `${candidate.kind}:${candidate.target_ref ?? ""}`).sort();
  const actualCandidates = belief.hypotheses
    .map((candidate) => `${candidate.kind}:${candidate.target_ref ?? ""}`).sort();
  if (expectedCandidates.length !== actualCandidates.length
    || expectedCandidates.some((candidate, index) => candidate !== actualCandidates[index])) {
    fail("result_input_mismatch");
  }
};

const contextFor = (
  context: Readonly<AuthorizedLedgerWriteContext>,
  value: unknown,
): Readonly<{
  input_ref: string;
  cohort_input_ref: string;
  stored_input: Readonly<StoredListenAttributionBeliefInput>;
  snapshot: Readonly<FormationInputSnapshot>;
  segments: readonly Readonly<ListenAttributionBlindSheetSegment>[];
}> => {
  const row = exactRecord(value, ["input_ref", "stored_input", "snapshot"], "invalid_context");
  const inputRef = ref(row["input_ref"], INPUT_REF, "invalid_context");
  const stored = storedInput(row["stored_input"]);
  const snapshot = parseFormationInputSnapshot(row["snapshot"]);
  if (stored.input_ref !== inputRef || stored.owner_account_id !== context.account_id
    || stored.account_epoch !== context.account_epoch || stored.formation_work_id !== snapshot.work_id
    || snapshot.owner_account_id !== context.account_id
    || stored.source_snapshot_digest !== formationWorkInputSnapshotDigest(snapshot)
    || inputRef !== listenAttributionBeliefInputRef({
      owner_account_id: stored.owner_account_id,
      account_epoch: stored.account_epoch,
      formation_work_id: stored.formation_work_id,
      about_ref: stored.input.about_ref,
    })) fail("context_coordinate_mismatch");
  const rematerialized = materializeListenAttributionBeliefInputs(snapshot);
  const exactInput = rematerialized.find((item) => item.about_ref === stored.input.about_ref);
  const rematerializedSet = materializeListenAttributionBeliefInputSet(context, {
    formation_work_id: snapshot.work_id,
    source_snapshot_digest: formationWorkInputSnapshotDigest(snapshot),
    snapshot,
  });
  const expectedEntry = rematerializedSet.inputs[stored.input_ordinal];
  if (!exactInput || sha256CanonicalContent(exactInput) !== stored.input_digest
    || rematerializedSet.set_digest !== stored.set_digest
    || rematerializedSet.inputs.length !== stored.input_count
    || !expectedEntry
    || expectedEntry.input_ref !== stored.input_ref
    || sha256CanonicalContent(expectedEntry.input) !== stored.input_digest
    || stored.stage_request_digest !== listenAttributionBeliefInputStageRequestDigest(rematerializedSet)) {
    fail("context_input_mismatch");
  }
  const targetEvidence = new Set(stored.input.evidence_factors.map((factor) => factor.evidence_ref));
  const eventByRevision = new Map(snapshot.events.map((event) => [event.event_revision_id, event]));
  const targetEventRevisions = new Set<string>();
  for (const evidence of snapshot.evidence) {
    const refValue = `atevidence1_${sha256CanonicalContent({
      contract_version: "listen-attribution-evidence-v1",
      observation_ref: stored.input.observation_ref,
      evidence_id: evidence.evidence_id,
      event_revision_id: evidence.event_revision_id,
    })}`;
    if (targetEvidence.has(refValue)) targetEventRevisions.add(evidence.event_revision_id);
  }
  if (targetEventRevisions.size === 0) fail("context_target_mismatch");
  const segments = snapshot.target_evidence_ids.map((evidenceId, ordinal) => {
    const evidence = snapshot.evidence.find((item) => item.evidence_id === evidenceId);
    if (!evidence) fail("context_target_mismatch");
    const event = eventByRevision.get(evidence.event_revision_id);
    if (!event) fail("context_target_mismatch");
    const payload = exactRecord(event.payload, [
      "text", "source_identity_ref", "speaker_rendering", "source_local_mention_ref",
      "observed_is_user", "segment_start_seconds", "segment_end_seconds",
      "capture_completeness", "finalization_digest", "conversation_id", "terminal_status", "source",
    ], "invalid_context_event");
    return Object.freeze({
      ordinal,
      text: text(payload["text"], 65_536, "invalid_context_event"),
      target: targetEventRevisions.has(event.event_revision_id),
    });
  });
  if (!segments.some((segment) => segment.target)) fail("context_target_mismatch");
  return Object.freeze({
    input_ref: inputRef,
    cohort_input_ref: evaluationInputCoordinate(
      stored.owner_account_id, stored.account_epoch, inputRef, stored.input,
    ).cohort_input_ref,
    stored_input: stored,
    snapshot,
    segments: Object.freeze(segments),
  });
};

export const buildListenAttributionBlindArtifacts = (
  contextValue: AuthorizedLedgerWriteContext,
  cohortValue: MemoryEvaluationCohortManifest,
  resultValues: readonly MemoryEvaluationResult[],
  contextValues: readonly ListenAttributionBlindContext[],
  secretValue: Uint8Array,
): Readonly<ListenAttributionBlindArtifacts> => {
  const context = assertAuthorizedLedgerWriteContext(contextValue);
  if (context.capability !== CAPABILITY) fail("capability_denied");
  if (!(secretValue instanceof Uint8Array) || isProxy(secretValue)
    || secretValue.byteLength < 32 || secretValue.byteLength > 128) fail("invalid_randomization_key");
  const secret = Uint8Array.from(secretValue);
  const cohort = parseMemoryEvaluationCohort(cohortValue);
  const expectedRefs = cohort.units.flatMap((unit) => unit.pairs.flatMap((pair) => [
    pair.baseline_result_ref, pair.candidate_result_ref,
  ]));
  const results = exactArray(resultValues, expectedRefs.length, expectedRefs.length, "invalid_results")
    .map(assertVerifiedMemoryEvaluationResult);
  unique(results.map((result) => result.evaluation_result_id), "duplicate_result");
  const byRef = new Map(results.map((result) => [result.evaluation_result_id, result]));
  if (expectedRefs.some((resultRef) => !byRef.has(resultRef))
    || results.some((result) => !expectedRefs.includes(result.evaluation_result_id))) fail("incomplete_results");
  const contexts = exactArray(contextValues, cohort.unit_count, cohort.unit_count, "invalid_contexts")
    .map((value) => contextFor(context, value));
  unique(contexts.map((item) => item.cohort_input_ref), "duplicate_context");
  const contextsByRef = new Map(contexts.map((item) => [item.cohort_input_ref, item]));

  const rows: Array<ListenAttributionBlindSheetRow & { order: string }> = [];
  const mappings: ListenAttributionBlindKeyMapping[] = [];
  for (const unit of cohort.units) {
    const item = contextsByRef.get(unit.input_ref);
    if (!item) fail("incomplete_contexts");
    const resultRefs: string[] = [];
    for (const pair of unit.pairs) {
      for (const role of ["baseline", "candidate"] as const) {
        const resultRef = role === "baseline" ? pair.baseline_result_ref : pair.candidate_result_ref;
        const result = byRef.get(resultRef)!;
        verifyBelief(
          context, cohort, item.stored_input.input, result, role,
          pair.repeat_ordinal, unit, item.input_ref,
        );
        resultRefs.push(resultRef);
      }
    }
    resultRefs.sort(compare);
    const rowRef = `labr1_${hmac(secret, {
      contract_version: "listen-attribution-blind-row-ref-v1",
      cohort_digest: cohort.cohort_digest,
      input_ref: item.input_ref,
      observation_ref: item.stored_input.input.observation_ref,
    })}`;
    rows.push({
      ordinal: 0,
      row_ref: rowRef,
      segments: item.segments,
      order: hmac(secret, {
        contract_version: "listen-attribution-blind-row-order-v1",
        sheet_cohort_digest: cohort.cohort_digest,
        row_ref: rowRef,
      }),
    });
    mappings.push(Object.freeze({
      row_ref: rowRef,
      input_ref: item.input_ref,
      observation_ref: item.stored_input.input.observation_ref,
      observation_content_digest: item.stored_input.input.observation_content_digest,
      result_refs: Object.freeze(resultRefs),
    }));
  }
  const orderedRows = Object.freeze(rows.sort((left, right) => compare(left.order, right.order))
    .map((row, ordinal) => Object.freeze({
      ordinal, row_ref: row.row_ref, segments: row.segments,
    })));
  mappings.sort((left, right) => compare(left.row_ref, right.row_ref));
  const hiddenCore = Object.freeze({
    version: KEY_VERSION,
    cohort_digest: cohort.cohort_digest,
    result_count: expectedRefs.length,
    mappings: Object.freeze(mappings),
  });
  const hiddenKey = parseListenAttributionBlindKey(Object.freeze({
    ...hiddenCore,
    hidden_key_digest: sha256CanonicalContent(hiddenCore),
  }));
  const sheetCore = Object.freeze({
    version: SHEET_VERSION,
    grading_protocol_version: PROTOCOL_VERSION,
    sheet_ref: `labs1_${hmac(secret, {
      contract_version: "listen-attribution-blind-sheet-ref-v1",
      cohort_digest: cohort.cohort_digest,
    })}`,
    cohort_digest: cohort.cohort_digest,
    row_count: orderedRows.length,
    rows: orderedRows,
    hidden_key_digest: hiddenKey.hidden_key_digest,
  });
  const sheet = parseListenAttributionBlindSheet(Object.freeze({
    ...sheetCore,
    blind_sheet_digest: sha256CanonicalContent(sheetCore),
  }));
  return Object.freeze({ sheet, hidden_key: hiddenKey });
};

export const parseListenAttributionBlindSheet = (value: unknown): Readonly<ListenAttributionBlindSheet> => {
  const root = exactRecord(value, [
    "version", "grading_protocol_version", "sheet_ref", "cohort_digest", "row_count",
    "rows", "hidden_key_digest", "blind_sheet_digest",
  ], "invalid_sheet");
  if (root["version"] !== SHEET_VERSION || root["grading_protocol_version"] !== PROTOCOL_VERSION) {
    fail("invalid_sheet");
  }
  const rows = Object.freeze(exactArray(root["rows"], 1, MAX_UNITS, "invalid_sheet")
    .map((entry, index) => {
      const row = exactRecord(entry, ["ordinal", "row_ref", "segments"], "invalid_sheet_row");
      if (integer(row["ordinal"], MAX_UNITS - 1, "invalid_sheet_row") !== index) fail("invalid_sheet_row");
      const segments = Object.freeze(exactArray(row["segments"], 1, 4_096, "invalid_sheet_row")
        .map((segmentValue, segmentIndex) => {
          const segment = exactRecord(segmentValue, ["ordinal", "text", "target"], "invalid_sheet_segment");
          if (integer(segment["ordinal"], 4_095, "invalid_sheet_segment") !== segmentIndex
            || typeof segment["target"] !== "boolean") fail("invalid_sheet_segment");
          return Object.freeze({
            ordinal: segmentIndex,
            text: text(segment["text"], 65_536, "invalid_sheet_segment"),
            target: segment["target"],
          });
        }));
      if (!segments.some((segment) => segment.target)) fail("invalid_sheet_row");
      return Object.freeze({ ordinal: index, row_ref: ref(row["row_ref"], ROW_REF, "invalid_sheet_row"), segments });
    }));
  unique(rows.map((row) => row.row_ref), "invalid_sheet");
  const core = Object.freeze({
    version: SHEET_VERSION,
    grading_protocol_version: PROTOCOL_VERSION,
    sheet_ref: ref(root["sheet_ref"], SHEET_REF, "invalid_sheet"),
    cohort_digest: ref(root["cohort_digest"], DIGEST, "invalid_sheet"),
    row_count: integer(root["row_count"], MAX_UNITS, "invalid_sheet"),
    rows,
    hidden_key_digest: ref(root["hidden_key_digest"], DIGEST, "invalid_sheet"),
  });
  if (core.row_count !== rows.length) fail("invalid_sheet_counts");
  const sheetDigest = ref(root["blind_sheet_digest"], DIGEST, "invalid_sheet");
  if (sheetDigest !== sha256CanonicalContent(core)) fail("invalid_sheet_digest");
  return Object.freeze({ ...core, blind_sheet_digest: sheetDigest });
};

export const parseListenAttributionBlindKey = (value: unknown): Readonly<ListenAttributionBlindKey> => {
  const root = exactRecord(value, [
    "version", "cohort_digest", "result_count", "mappings", "hidden_key_digest",
  ], "invalid_hidden_key");
  if (root["version"] !== KEY_VERSION) fail("invalid_hidden_key");
  const mappings = Object.freeze(exactArray(root["mappings"], 1, MAX_UNITS, "invalid_hidden_key")
    .map((entry) => {
      const row = exactRecord(entry, [
        "row_ref", "input_ref", "observation_ref", "observation_content_digest", "result_refs",
      ], "invalid_hidden_mapping");
      const resultRefs = Object.freeze(exactArray(row["result_refs"], 2, MAX_RESULTS, "invalid_hidden_mapping")
        .map((resultRef) => ref(resultRef, RESULT_REF, "invalid_hidden_mapping")));
      unique(resultRefs, "invalid_hidden_mapping");
      if (resultRefs.some((resultRef, index) => index > 0 && compare(resultRefs[index - 1]!, resultRef) >= 0)) {
        fail("invalid_hidden_mapping");
      }
      return Object.freeze({
        row_ref: ref(row["row_ref"], ROW_REF, "invalid_hidden_mapping"),
        input_ref: ref(row["input_ref"], INPUT_REF, "invalid_hidden_mapping"),
        observation_ref: ref(row["observation_ref"], OBSERVATION_REF, "invalid_hidden_mapping"),
        observation_content_digest: ref(row["observation_content_digest"], DIGEST, "invalid_hidden_mapping"),
        result_refs: resultRefs,
      });
    }));
  unique(mappings.map((mapping) => mapping.row_ref), "invalid_hidden_key");
  unique(mappings.map((mapping) => mapping.input_ref), "invalid_hidden_key");
  const allResults = mappings.flatMap((mapping) => mapping.result_refs);
  unique(allResults, "invalid_hidden_key");
  const core = Object.freeze({
    version: KEY_VERSION,
    cohort_digest: ref(root["cohort_digest"], DIGEST, "invalid_hidden_key"),
    result_count: integer(root["result_count"], MAX_RESULTS, "invalid_hidden_key"),
    mappings,
  });
  if (core.result_count !== allResults.length) fail("invalid_hidden_key_counts");
  const hiddenDigest = ref(root["hidden_key_digest"], DIGEST, "invalid_hidden_key");
  if (hiddenDigest !== sha256CanonicalContent(core)) fail("invalid_hidden_key_digest");
  return Object.freeze({ ...core, hidden_key_digest: hiddenDigest });
};

export const expandListenAttributionBlindLabels = (
  sheetValue: ListenAttributionBlindSheet,
  hiddenKeyValue: ListenAttributionBlindKey,
  graderSessionRefValue: string,
  gradeValues: readonly ListenAttributionBlindHumanGrade[],
): Readonly<ListenAttributionBlindLabels> => {
  const sheet = parseListenAttributionBlindSheet(sheetValue);
  const hidden = parseListenAttributionBlindKey(hiddenKeyValue);
  if (sheet.cohort_digest !== hidden.cohort_digest || sheet.hidden_key_digest !== hidden.hidden_key_digest
    || sheet.row_count !== hidden.mappings.length) fail("sheet_key_mismatch");
  const publicRefs = sheet.rows.map((row) => row.row_ref).sort(compare);
  const hiddenRefs = hidden.mappings.map((row) => row.row_ref).sort(compare);
  if (publicRefs.some((rowRef, index) => rowRef !== hiddenRefs[index])) fail("sheet_key_mismatch");
  const grades = exactArray(gradeValues, publicRefs.length, publicRefs.length, "invalid_human_grades")
    .map((entry) => {
      const row = exactRecord(entry, ["row_ref", "label"], "invalid_human_grade");
      if (row["label"] !== "owner" && row["label"] !== "non_owner" && row["label"] !== "unclear") {
        fail("invalid_human_grade");
      }
      return Object.freeze({
        row_ref: ref(row["row_ref"], ROW_REF, "invalid_human_grade"),
        label: row["label"] as ListenAttributionTruthLabel,
      });
    });
  unique(grades.map((grade) => grade.row_ref), "invalid_human_grades");
  const byRef = new Map(grades.map((grade) => [grade.row_ref, grade.label]));
  if (publicRefs.some((rowRef) => !byRef.has(rowRef))) fail("incomplete_human_grades");
  const labels = Object.freeze(hidden.mappings.map((mapping) => Object.freeze({
    row_ref: mapping.row_ref,
    input_ref: mapping.input_ref,
    observation_ref: mapping.observation_ref,
    result_refs: mapping.result_refs,
    label: byRef.get(mapping.row_ref)!,
  })));
  const core = Object.freeze({
    version: LABELS_VERSION,
    grading_protocol_version: PROTOCOL_VERSION,
    grader_session_ref: ref(graderSessionRefValue, GRADER_REF, "invalid_grader_session"),
    cohort_digest: sheet.cohort_digest,
    blind_sheet_digest: sheet.blind_sheet_digest,
    hidden_key_digest: hidden.hidden_key_digest,
    labels,
  });
  return Object.freeze({ ...core, labels_digest: sha256CanonicalContent(core) });
};

export const LISTEN_ATTRIBUTION_BLIND_SHEET_VERSION = SHEET_VERSION;
export const LISTEN_ATTRIBUTION_BLIND_KEY_VERSION = KEY_VERSION;
export const LISTEN_ATTRIBUTION_BLIND_LABELS_VERSION = LABELS_VERSION;
