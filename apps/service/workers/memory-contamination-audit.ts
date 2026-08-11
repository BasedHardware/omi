import { isProxy } from "node:util/types";

import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import {
  assertVerifiedMemoryEvaluationResult,
  type MemoryEvaluationResult,
} from "../stores/memory-shadow-result-repository";
import type { MemoryReadGroundingRepository } from "../stores/memory-read-grounding-repository";
import {
  parseMemoryEvaluationCohort,
  type MemoryEvaluationCohortManifest,
} from "./memory-evaluation-statistics";
import {
  parseMemoryReadEvaluationResult,
  type MemoryReadEvaluationResult,
} from "./memory-read-evaluation-result";

const SOURCE_PORT: unique symbol = Symbol("memory-read-provenance-source");
const CAPABILITY = "memories.experiments.shadow";
const MANIFEST_VERSION = "memory-read-provenance-manifest-v1" as const;
const FINDING_VERSION = "memory-contamination-finding-v1" as const;
const REPORT_VERSION = "memory-contamination-report-v1" as const;
const RESULT_REF = /^msr1_[a-f0-9]{64}$/;
const TRACE_REF = /^tr1_[a-f0-9]{64}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const SUBJECT_CLASS = /^[a-z][a-z0-9_-]{0,63}$/;
const SECOND_PERSON = /\b(you|your|you're|yours)\b/i;
const MAX_REFERENCES = 10_000;
const MAX_CLASSES = 32;
const manifests = new WeakSet<object>();
const findings = new WeakSet<object>();

export interface MemoryReadProvenanceRow {
  readonly trace_ref: string;
  readonly contributing_subject_classes: readonly string[];
}

export interface MemoryReadProvenanceManifest {
  readonly version: typeof MANIFEST_VERSION;
  readonly evaluation_result_ref: string;
  readonly normalized_result_digest: string;
  readonly grounded_reference_count: number;
  readonly rows: readonly Readonly<MemoryReadProvenanceRow>[];
  readonly manifest_digest: string;
}

export type MemoryReadProvenanceSourceOutcome =
  | Readonly<{ kind: "found"; manifest: Readonly<MemoryReadProvenanceManifest> }>
  | Readonly<{ kind: "not_found" | "source_unavailable" | "serialization_retryable" }>
  | Readonly<{
      kind: "stale_context";
      reason: "expired_context" | "stale_epoch" | "destination_inactive" | "lifecycle_inactive";
    }>
  | Readonly<{
      kind: "authorization_denied";
      reason: "credential_inactive" | "grant_inactive" | "capability_denied";
    }>;

export interface MemoryReadProvenanceSource {
  readonly [SOURCE_PORT]: true;
  load(
    context: AuthorizedLedgerWriteContext,
    result: MemoryEvaluationResult,
  ): Promise<MemoryReadProvenanceSourceOutcome>;
}

export type MemoryReadProvenanceSourceImplementation = (
  context: AuthorizedLedgerWriteContext,
  result: Readonly<MemoryEvaluationResult>,
  readResult: Readonly<MemoryReadEvaluationResult>,
) => Promise<unknown>;

export interface MemoryContaminationFinding {
  readonly version: typeof FINDING_VERSION;
  readonly evaluation_result_ref: string;
  readonly normalized_result_digest: string;
  readonly answered: boolean;
  readonly assertion_count: number;
  readonly second_person_assertion_count: number;
  readonly conflicting_grounded_reference_count: number;
  readonly contaminated_assertion_count: number;
  readonly contaminated: boolean;
  readonly finding_digest: string;
}

export interface MemoryContaminationCounts {
  readonly answers: number;
  readonly second_person_answers: number;
  readonly contaminated_answers: number;
  readonly contaminated_percent_of_second_person: number;
}

export interface MemoryContaminationReport {
  readonly version: typeof REPORT_VERSION;
  readonly cohort_digest: string;
  readonly input_count: number;
  readonly repeat_count: number;
  readonly result_count: number;
  readonly primary_repeat_ordinal: 0;
  readonly baseline_all_repeats: Readonly<MemoryContaminationCounts>;
  readonly candidate_all_repeats: Readonly<MemoryContaminationCounts>;
  readonly both_contaminated: number;
  readonly baseline_only_contaminated: number;
  readonly candidate_only_contaminated: number;
  readonly neither_contaminated: number;
  readonly net_removed: number;
  readonly mcnemar_exact_two_sided: Readonly<{
    numerator: string;
    denominator_power_of_two: number;
    approximate: number;
  }>;
  readonly baseline_self_noise: Readonly<{ comparisons: number; contamination_flips: number; flip_rate: number }>;
  readonly candidate_self_noise: Readonly<{ comparisons: number; contamination_flips: number; flip_rate: number }>;
  readonly report_digest: string;
}

const fail = (code: string): never => { throw new TypeError(`memory contamination audit ${code}`); };
const compare = (left: string, right: string): number => left < right ? -1 : left > right ? 1 : 0;

const exactRecord = (value: unknown, keys: readonly string[], code: string): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const ownKeys = Reflect.ownKeys(value as object);
  if (ownKeys.length !== keys.length || ownKeys.some((key) => typeof key !== "string" || !keys.includes(key))) fail(code);
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value as Record<string, unknown>;
};

const exactArray = (value: unknown, minimum: number, maximum: number, code: string): readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype
    || value.length < minimum || value.length > maximum) fail(code);
  const keys = Reflect.ownKeys(value);
  if (keys.length !== value.length + 1 || keys.some((key) => typeof key !== "string"
    || (key !== "length" && (!/^(0|[1-9]\d*)$/.test(key) || Number(key) >= value.length)))) fail(code);
  const output: unknown[] = [];
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = Object.getOwnPropertyDescriptor(value, String(index));
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
    output.push(descriptor.value);
  }
  return output;
};

const ref = (value: unknown, pattern: RegExp, code: string): string => {
  if (typeof value !== "string" || !pattern.test(value)) fail(code);
  return value;
};

const unique = (values: readonly string[], code: string): void => {
  if (new Set(values).size !== values.length) fail(code);
};

const commonOutcome = (value: unknown): Exclude<MemoryReadProvenanceSourceOutcome, { kind: "found" }> | null => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)) fail("invalid_source_outcome");
  const descriptor = Object.getOwnPropertyDescriptor(value, "kind");
  const kind = descriptor && "value" in descriptor && descriptor.enumerable ? descriptor.value : fail("invalid_source_outcome");
  if (kind === "not_found" || kind === "serialization_retryable") {
    exactRecord(value, ["kind"], "invalid_source_outcome");
    return Object.freeze({ kind });
  }
  if (kind === "stale_context" || kind === "authorization_denied") {
    const input = exactRecord(value, ["kind", "reason"], "invalid_source_outcome");
    const allowed = kind === "stale_context"
      ? ["expired_context", "stale_epoch", "destination_inactive", "lifecycle_inactive"]
      : ["credential_inactive", "grant_inactive", "capability_denied"];
    if (typeof input["reason"] !== "string" || !allowed.includes(input["reason"])) fail("invalid_source_outcome");
    return Object.freeze({ kind, reason: input["reason"] }) as Exclude<MemoryReadProvenanceSourceOutcome, { kind: "found" }>;
  }
  return null;
};

const normalizeManifest = (
  result: Readonly<MemoryEvaluationResult>,
  read: Readonly<MemoryReadEvaluationResult>,
  value: unknown,
): Readonly<MemoryReadProvenanceManifest> => {
  const input = exactRecord(value, [
    "kind", "evaluation_result_ref", "normalized_result_digest", "rows",
  ], "invalid_source_outcome");
  if (input["kind"] !== "found"
    || input["evaluation_result_ref"] !== result.evaluation_result_id
    || input["normalized_result_digest"] !== result.normalized_result_digest) fail("source_coordinate_mismatch");
  const rows = Object.freeze(exactArray(input["rows"], 0, MAX_REFERENCES, "invalid_provenance_rows")
    .map((value) => {
      const row = exactRecord(value, ["trace_ref", "contributing_subject_classes"], "invalid_provenance_row");
      const classes = Object.freeze(exactArray(
        row["contributing_subject_classes"],
        1,
        MAX_CLASSES,
        "invalid_provenance_row",
      ).map((subjectClass) => {
        if (typeof subjectClass !== "string" || !SUBJECT_CLASS.test(subjectClass)) fail("invalid_provenance_row");
        return subjectClass;
      }));
      unique(classes, "invalid_provenance_row");
      if (classes.some((subjectClass, index) => index > 0 && compare(classes[index - 1]!, subjectClass) >= 0)) {
        fail("invalid_provenance_row");
      }
      return Object.freeze({
        trace_ref: ref(row["trace_ref"], TRACE_REF, "invalid_provenance_row"),
        contributing_subject_classes: classes,
      });
    }));
  const expectedRefs = [...read.recall_trace.stages.grounded].sort(compare);
  const actualRefs = rows.map((row) => row.trace_ref);
  unique(actualRefs, "duplicate_provenance_reference");
  if (actualRefs.length !== expectedRefs.length
    || actualRefs.some((traceRef, index) => traceRef !== expectedRefs[index])) fail("incomplete_provenance");
  const core = Object.freeze({
    version: MANIFEST_VERSION,
    evaluation_result_ref: result.evaluation_result_id,
    normalized_result_digest: result.normalized_result_digest,
    grounded_reference_count: rows.length,
    rows,
  });
  const manifest = Object.freeze({ ...core, manifest_digest: sha256CanonicalContent(core) });
  manifests.add(manifest);
  return manifest;
};

export const defineMemoryReadProvenanceSource = (
  implementation: MemoryReadProvenanceSourceImplementation,
): MemoryReadProvenanceSource => Object.freeze({
  [SOURCE_PORT]: true as const,
  async load(contextValue, resultValue) {
    const context = assertAuthorizedLedgerWriteContext(contextValue);
    if (context.capability !== CAPABILITY) fail("capability_denied");
    const result = assertVerifiedMemoryEvaluationResult(resultValue);
    if (result.owner_account_id !== context.account_id || result.account_epoch !== context.account_epoch) {
      fail("authority_mismatch");
    }
    const read = parseMemoryReadEvaluationResult(result.normalized_result);
    let raw: unknown;
    try {
      raw = await implementation(context, result, read);
    } catch {
      return Object.freeze({ kind: "source_unavailable" as const });
    }
    const common = commonOutcome(raw);
    if (common) return common;
    return Object.freeze({ kind: "found" as const, manifest: normalizeManifest(result, read, raw) });
  },
});

/**
 * Adapts the sealed finalized-grounding store to the audit's narrow read port.
 * The repository performs authority, result-coordinate, and artifact-digest
 * validation before any rows reach this facade.
 */
export const memoryReadProvenanceSourceFromGroundingRepository = (
  repository: MemoryReadGroundingRepository,
): MemoryReadProvenanceSource => defineMemoryReadProvenanceSource(async (context, result) => {
  const loaded = await repository.load(context, result);
  if (loaded.kind === "found") {
    return Object.freeze({
      kind: "found" as const,
      evaluation_result_ref: loaded.artifact.evaluation_result_ref,
      normalized_result_digest: loaded.artifact.normalized_result_digest,
      rows: loaded.artifact.rows,
    });
  }
  if (loaded.kind === "missing") return Object.freeze({ kind: "not_found" as const });
  return loaded;
});

export const auditMemoryReadContamination = (
  resultValue: MemoryEvaluationResult,
  manifestValue: MemoryReadProvenanceManifest,
): Readonly<MemoryContaminationFinding> => {
  const result = assertVerifiedMemoryEvaluationResult(resultValue);
  if (manifestValue === null || typeof manifestValue !== "object" || !manifests.has(manifestValue)) {
    fail("unverified_provenance_manifest");
  }
  const manifest = manifestValue as Readonly<MemoryReadProvenanceManifest>;
  if (manifest.evaluation_result_ref !== result.evaluation_result_id
    || manifest.normalized_result_digest !== result.normalized_result_digest) fail("provenance_result_mismatch");
  const read = parseMemoryReadEvaluationResult(result.normalized_result);
  const classesByRef = new Map(manifest.rows.map((row) => [row.trace_ref, new Set(row.contributing_subject_classes)]));
  const bystanderOnlyRefs = new Set(manifest.rows.filter((row) => {
    const classes = new Set(row.contributing_subject_classes);
    return classes.has("bystander") && !classes.has("owner") && !classes.has("owner_context");
  }).map((row) => row.trace_ref));
  let secondPersonAssertions = 0;
  let contaminatedAssertions = 0;
  for (const assertion of read.assertions) {
    const secondPerson = SECOND_PERSON.test(assertion.text);
    if (secondPerson) secondPersonAssertions += 1;
    if (secondPerson && assertion.citations.some((citation) => bystanderOnlyRefs.has(citation))) {
      contaminatedAssertions += 1;
    }
    for (const citation of assertion.citations) if (!classesByRef.has(citation)) fail("incomplete_provenance");
  }
  const core = Object.freeze({
    version: FINDING_VERSION,
    evaluation_result_ref: result.evaluation_result_id,
    normalized_result_digest: result.normalized_result_digest,
    answered: read.answer_text !== null,
    assertion_count: read.assertions.length,
    second_person_assertion_count: secondPersonAssertions,
    conflicting_grounded_reference_count: bystanderOnlyRefs.size,
    contaminated_assertion_count: contaminatedAssertions,
    contaminated: contaminatedAssertions > 0,
  });
  const finding = Object.freeze({ ...core, finding_digest: sha256CanonicalContent(core) });
  findings.add(finding);
  return finding;
};

const exactMcNemar = (left: number, right: number): Readonly<{
  numerator: string; denominator_power_of_two: number; approximate: number;
}> => {
  const trials = left + right;
  const tail = Math.min(left, right);
  if (trials === 0) return Object.freeze({ numerator: "1", denominator_power_of_two: 0, approximate: 1 });
  let combination = 1n;
  let sum = 1n;
  for (let index = 1; index <= tail; index += 1) {
    combination = (combination * BigInt(trials - index + 1)) / BigInt(index);
    sum += combination;
  }
  let numerator = 2n * sum;
  let denominatorPower = trials;
  const denominator = 1n << BigInt(trials);
  if (numerator >= denominator) return Object.freeze({ numerator: "1", denominator_power_of_two: 0, approximate: 1 });
  while (denominatorPower > 0 && numerator % 2n === 0n) {
    numerator /= 2n;
    denominatorPower -= 1;
  }
  const shift = Math.max(0, sum.toString(2).length - 53);
  const logApproximation = Math.log(2) + Math.log(Number(sum >> BigInt(shift)))
    + shift * Math.log(2) - trials * Math.log(2);
  const finiteNumerator = Number(numerator);
  return Object.freeze({
    numerator: numerator.toString(),
    denominator_power_of_two: denominatorPower,
    approximate: Number.isFinite(finiteNumerator) && denominatorPower <= 1_023
      ? finiteNumerator / (2 ** denominatorPower)
      : Math.exp(logApproximation),
  });
};

const counts = (values: readonly Readonly<MemoryContaminationFinding>[]): Readonly<MemoryContaminationCounts> => {
  const answers = values.filter((finding) => finding.answered).length;
  const secondPerson = values.filter((finding) => finding.second_person_assertion_count > 0).length;
  const contaminated = values.filter((finding) => finding.contaminated).length;
  return Object.freeze({
    answers,
    second_person_answers: secondPerson,
    contaminated_answers: contaminated,
    contaminated_percent_of_second_person: secondPerson ? contaminated * 100 / secondPerson : 0,
  });
};

export const analyzeMemoryContaminationFindings = (
  cohortValue: MemoryEvaluationCohortManifest,
  findingValues: readonly MemoryContaminationFinding[],
): Readonly<MemoryContaminationReport> => {
  const cohort = parseMemoryEvaluationCohort(cohortValue);
  const expectedRefs = cohort.units.flatMap((unit) => unit.pairs.flatMap((pair) => [
    pair.baseline_result_ref, pair.candidate_result_ref,
  ]));
  const rawFindings = exactArray(findingValues, expectedRefs.length, expectedRefs.length, "invalid_findings");
  const normalized = rawFindings.map((value) => {
    if (value === null || typeof value !== "object" || !findings.has(value)) fail("unverified_finding");
    return value as Readonly<MemoryContaminationFinding>;
  });
  unique(normalized.map((finding) => finding.evaluation_result_ref), "duplicate_finding");
  const byRef = new Map(normalized.map((finding) => [finding.evaluation_result_ref, finding]));
  if (expectedRefs.some((resultRef) => !byRef.has(resultRef)) || normalized.some(
    (finding) => !expectedRefs.includes(finding.evaluation_result_ref),
  )) fail("incomplete_findings");
  const baselineAll: MemoryContaminationFinding[] = [];
  const candidateAll: MemoryContaminationFinding[] = [];
  let both = 0;
  let baselineOnly = 0;
  let candidateOnly = 0;
  let neither = 0;
  let baselineComparisons = 0;
  let candidateComparisons = 0;
  let baselineFlips = 0;
  let candidateFlips = 0;
  for (const unit of cohort.units) {
    const primary = unit.pairs[0]!;
    const baselinePrimary = byRef.get(primary.baseline_result_ref)!;
    const candidatePrimary = byRef.get(primary.candidate_result_ref)!;
    if (baselinePrimary.contaminated && candidatePrimary.contaminated) both += 1;
    else if (baselinePrimary.contaminated) baselineOnly += 1;
    else if (candidatePrimary.contaminated) candidateOnly += 1;
    else neither += 1;
    for (const pair of unit.pairs) {
      const baseline = byRef.get(pair.baseline_result_ref)!;
      const candidate = byRef.get(pair.candidate_result_ref)!;
      baselineAll.push(baseline);
      candidateAll.push(candidate);
      if (pair.repeat_ordinal !== 0) {
        baselineComparisons += 1;
        candidateComparisons += 1;
        if (baseline.contaminated !== baselinePrimary.contaminated) baselineFlips += 1;
        if (candidate.contaminated !== candidatePrimary.contaminated) candidateFlips += 1;
      }
    }
  }
  const core = Object.freeze({
    version: REPORT_VERSION,
    cohort_digest: cohort.cohort_digest,
    input_count: cohort.unit_count,
    repeat_count: cohort.repeat_count,
    result_count: expectedRefs.length,
    primary_repeat_ordinal: 0 as const,
    baseline_all_repeats: counts(baselineAll),
    candidate_all_repeats: counts(candidateAll),
    both_contaminated: both,
    baseline_only_contaminated: baselineOnly,
    candidate_only_contaminated: candidateOnly,
    neither_contaminated: neither,
    net_removed: baselineOnly - candidateOnly,
    mcnemar_exact_two_sided: exactMcNemar(baselineOnly, candidateOnly),
    baseline_self_noise: Object.freeze({
      comparisons: baselineComparisons,
      contamination_flips: baselineFlips,
      flip_rate: baselineComparisons ? baselineFlips / baselineComparisons : 0,
    }),
    candidate_self_noise: Object.freeze({
      comparisons: candidateComparisons,
      contamination_flips: candidateFlips,
      flip_rate: candidateComparisons ? candidateFlips / candidateComparisons : 0,
    }),
  });
  return Object.freeze({ ...core, report_digest: sha256CanonicalContent(core) });
};

export const MEMORY_READ_PROVENANCE_MANIFEST_VERSION = MANIFEST_VERSION;
export const MEMORY_CONTAMINATION_FINDING_VERSION = FINDING_VERSION;
export const MEMORY_CONTAMINATION_REPORT_VERSION = REPORT_VERSION;
