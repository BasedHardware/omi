import { createHmac } from "node:crypto";
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
import {
  externalMemoryEvaluationLabelsDigest,
  MEMORY_EVALUATION_GRADING_PROTOCOL,
  MEMORY_EVALUATION_LABEL_VERSION,
  parseMemoryEvaluationCohort,
  type ExternalMemoryEvaluationLabels,
  type MemoryEvaluationCohortManifest,
  type MemoryEvaluationGrade,
} from "./memory-evaluation-statistics";
import {
  parseMemoryReadEvaluationResult,
  type MemoryReadEvaluationResult,
} from "./memory-read-evaluation-result";

const SHEET_VERSION = "memory-blind-sheet-v1" as const;
const KEY_VERSION = "memory-blind-key-v1" as const;
const CAPABILITY = "memories.experiments.shadow";
const MAX_RESULTS = 200_000;
const MAX_ROWS = 10_000;
const MAX_ANSWERS = MAX_RESULTS;
const DIGEST = /^[a-f0-9]{64}$/;
const RESULT_REF = /^msr1_[a-f0-9]{64}$/;
const SHEET_REF = /^mbs1_[a-f0-9]{64}$/;
const ROW_REF = /^mbr1_[a-f0-9]{64}$/;
const ANSWER_REF = /^mba1_[a-f0-9]{64}$/;
const GRADER_REF = /^meg1_[a-f0-9]{64}$/;

export interface MemoryBlindSheetAnswer {
  readonly ordinal: number;
  readonly answer_ref: string;
  readonly answer_text: string;
}

export interface MemoryBlindSheetRow {
  readonly ordinal: number;
  readonly row_ref: string;
  readonly query_text: string;
  readonly answers: readonly Readonly<MemoryBlindSheetAnswer>[];
}

export interface MemoryBlindEvaluationSheet {
  readonly version: typeof SHEET_VERSION;
  readonly grading_protocol_version: typeof MEMORY_EVALUATION_GRADING_PROTOCOL;
  readonly sheet_ref: string;
  readonly cohort_digest: string;
  readonly input_count: number;
  readonly result_count: number;
  readonly rendered_row_count: number;
  readonly human_answer_count: number;
  readonly machine_empty_count: number;
  readonly deduplicated_result_count: number;
  readonly rows: readonly Readonly<MemoryBlindSheetRow>[];
  readonly hidden_key_digest: string;
  readonly blind_sheet_digest: string;
}

export interface MemoryBlindKeyMapping {
  readonly answer_ref: string;
  readonly result_refs: readonly string[];
}

export interface MemoryBlindEvaluationKey {
  readonly version: typeof KEY_VERSION;
  readonly cohort_digest: string;
  readonly result_count: number;
  readonly mappings: readonly Readonly<MemoryBlindKeyMapping>[];
  readonly machine_empty_labels: readonly Readonly<{ result_ref: string; grade: "empty" }>[];
  readonly hidden_key_digest: string;
}

export interface MemoryBlindEvaluationArtifacts {
  readonly sheet: Readonly<MemoryBlindEvaluationSheet>;
  readonly hidden_key: Readonly<MemoryBlindEvaluationKey>;
}

export interface MemoryBlindHumanGrade {
  readonly answer_ref: string;
  readonly grade: Exclude<MemoryEvaluationGrade, "empty">;
}

const fail = (code: string): never => { throw new TypeError(`memory blind evaluation ${code}`); };
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

const integer = (value: unknown, maximum: number, code: string): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 0 || (value as number) > maximum) fail(code);
  return value as number;
};

const text = (value: unknown, maximum: number, code: string): string => {
  if (typeof value !== "string" || value.length === 0 || value !== value.trim()
    || [...value].length > maximum || /[\p{Cc}\p{Cs}]/u.test(value)) fail(code);
  return value;
};

const hmac = (secret: Uint8Array, value: unknown): string => createHmac("sha256", secret)
  .update(JSON.stringify(value)).digest("hex");

const unique = (values: readonly string[], code: string): void => {
  if (new Set(values).size !== values.length) fail(code);
};

const readResult = (result: Readonly<MemoryEvaluationResult>): Readonly<MemoryReadEvaluationResult> => {
  if (result.result_contract_version !== "memory-read-evaluation-result-v1") fail("wrong_result_contract");
  return parseMemoryReadEvaluationResult(result.normalized_result);
};

const verifyPlacement = (
  context: Readonly<AuthorizedLedgerWriteContext>,
  cohort: Readonly<MemoryEvaluationCohortManifest>,
  unit: Readonly<MemoryEvaluationCohortManifest["units"][number]>,
  result: Readonly<MemoryEvaluationResult>,
  role: "baseline" | "candidate",
  repeatOrdinal: number,
): Readonly<MemoryReadEvaluationResult> => {
  if (result.owner_account_id !== context.account_id || result.account_epoch !== context.account_epoch) fail("authority_mismatch");
  if (result.evaluation_run_id !== cohort.evaluation_run_ref || result.evaluation_mode !== cohort.evaluation_mode
    || result.evaluation_role !== role || result.repeat_ordinal !== repeatOrdinal) fail("result_coordinate_mismatch");
  const expectedAssignmentRef = `mea1_${sha256CanonicalContent({
    contract_version: "memory-evaluation-export-assignment-ref-v1",
    owner_account_id: result.owner_account_id,
    account_epoch: result.account_epoch,
    assignment_bundle_id: result.assignment_bundle_id,
  })}`;
  const frontierRef = sha256CanonicalContent({
    contract_version: "memory-evaluation-frontier-ref-v1",
    input_frontier: result.input_frontier,
  });
  const expectedInputRef = `mei1_${sha256CanonicalContent({
    contract_version: "memory-evaluation-export-input-ref-v1",
    owner_account_id: result.owner_account_id,
    account_epoch: result.account_epoch,
    input_frontier_digest: frontierRef,
    input_digest: result.input_digest,
  })}`;
  if (expectedAssignmentRef !== unit.assignment_bundle_ref || expectedInputRef !== unit.input_ref) {
    fail("result_coordinate_mismatch");
  }
  const read = readResult(result);
  const expectedReadFrontier = sha256CanonicalContent({
    contract_version: "memory-read-evaluation-frontier-v1",
    input_frontier: result.input_frontier,
  });
  if (read.copied_input_digest !== result.input_digest || read.input_frontier_digest !== expectedReadFrontier
    || read.strategy_id !== result.strategy_id || read.execution_contract_digest !== result.execution_contract_digest
    || read.evaluation_role !== role || read.repeat_ordinal !== repeatOrdinal) fail("normalized_result_mismatch");
  return read;
};

export const buildMemoryBlindEvaluationArtifacts = (
  contextValue: AuthorizedLedgerWriteContext,
  cohortValue: MemoryEvaluationCohortManifest,
  resultValues: readonly MemoryEvaluationResult[],
  secretValue: Uint8Array,
): Readonly<MemoryBlindEvaluationArtifacts> => {
  const context = assertAuthorizedLedgerWriteContext(contextValue);
  if (context.capability !== CAPABILITY) fail("capability_denied");
  if (!(secretValue instanceof Uint8Array) || isProxy(secretValue)
    || secretValue.byteLength < 32 || secretValue.byteLength > 128) fail("invalid_randomization_key");
  const secret = Uint8Array.from(secretValue);
  const cohort = parseMemoryEvaluationCohort(cohortValue);
  const expectedRefs = cohort.units.flatMap((unit) => unit.pairs.flatMap((pair) => [
    pair.baseline_result_ref, pair.candidate_result_ref,
  ]));
  const rawResults = exactArray(resultValues, expectedRefs.length, expectedRefs.length, "invalid_results");
  const results = rawResults.map(assertVerifiedMemoryEvaluationResult);
  unique(results.map((result) => result.evaluation_result_id), "duplicate_result");
  const byRef = new Map(results.map((result) => [result.evaluation_result_id, result]));
  if (expectedRefs.some((resultRef) => !byRef.has(resultRef)) || results.some(
    (result) => !expectedRefs.includes(result.evaluation_result_id),
  )) fail("incomplete_results");

  const publicRows: MemoryBlindSheetRow[] = [];
  const mappings: MemoryBlindKeyMapping[] = [];
  const machineEmptyRefs: string[] = [];
  let deduplicatedResultCount = 0;

  for (const unit of cohort.units) {
    let query: string | null = null;
    const answerResults = new Map<string, string[]>();
    for (const pair of unit.pairs) {
      for (const role of ["baseline", "candidate"] as const) {
        const resultRef = role === "baseline" ? pair.baseline_result_ref : pair.candidate_result_ref;
        const result = byRef.get(resultRef)!;
        const read = verifyPlacement(context, cohort, unit, result, role, pair.repeat_ordinal);
        if (query === null) query = read.query_text;
        else if (query !== read.query_text) fail("query_mismatch");
        if (read.answer_text === null) machineEmptyRefs.push(resultRef);
        else {
          const refs = answerResults.get(read.answer_text) ?? [];
          refs.push(resultRef);
          answerResults.set(read.answer_text, refs);
        }
      }
    }
    if (answerResults.size === 0) continue;
    const rowRef = `mbr1_${hmac(secret, {
      contract_version: "memory-blind-row-ref-v1",
      cohort_digest: cohort.cohort_digest,
      input_ref: unit.input_ref,
    })}`;
    const answerRows = [...answerResults.entries()].map(([answerText, resultRefs]) => {
      const answerRef = `mba1_${hmac(secret, {
        contract_version: "memory-blind-answer-ref-v1",
        row_ref: rowRef,
        answer_digest: sha256CanonicalContent({ answer_text: answerText }),
      })}`;
      const order = hmac(secret, {
        contract_version: "memory-blind-answer-order-v1",
        row_ref: rowRef,
        answer_ref: answerRef,
      });
      const sortedRefs = Object.freeze([...resultRefs].sort(compare));
      deduplicatedResultCount += sortedRefs.length - 1;
      mappings.push(Object.freeze({ answer_ref: answerRef, result_refs: sortedRefs }));
      return { answer_ref: answerRef, answer_text: answerText, order };
    }).sort((left, right) => compare(left.order, right.order) || compare(left.answer_ref, right.answer_ref));
    publicRows.push(Object.freeze({
      ordinal: publicRows.length,
      row_ref: rowRef,
      query_text: query!,
      answers: Object.freeze(answerRows.map((answer, ordinal) => Object.freeze({
        ordinal,
        answer_ref: answer.answer_ref,
        answer_text: answer.answer_text,
      }))),
    }));
  }

  mappings.sort((left, right) => compare(left.answer_ref, right.answer_ref));
  machineEmptyRefs.sort(compare);
  const hiddenCore = Object.freeze({
    version: KEY_VERSION,
    cohort_digest: cohort.cohort_digest,
    result_count: expectedRefs.length,
    mappings: Object.freeze(mappings),
    machine_empty_labels: Object.freeze(machineEmptyRefs.map((resultRef) => Object.freeze({
      result_ref: resultRef,
      grade: "empty" as const,
    }))),
  });
  const hiddenKey = parseMemoryBlindEvaluationKey(Object.freeze({
    ...hiddenCore,
    hidden_key_digest: sha256CanonicalContent(hiddenCore),
  }));
  const sheetCore = Object.freeze({
    version: SHEET_VERSION,
    grading_protocol_version: MEMORY_EVALUATION_GRADING_PROTOCOL,
    sheet_ref: `mbs1_${hmac(secret, {
      contract_version: "memory-blind-sheet-ref-v1",
      cohort_digest: cohort.cohort_digest,
    })}`,
    cohort_digest: cohort.cohort_digest,
    input_count: cohort.unit_count,
    result_count: expectedRefs.length,
    rendered_row_count: publicRows.length,
    human_answer_count: mappings.length,
    machine_empty_count: machineEmptyRefs.length,
    deduplicated_result_count: deduplicatedResultCount,
    rows: Object.freeze(publicRows),
    hidden_key_digest: hiddenKey.hidden_key_digest,
  });
  const sheet = parseMemoryBlindEvaluationSheet(Object.freeze({
    ...sheetCore,
    blind_sheet_digest: sha256CanonicalContent(sheetCore),
  }));
  return Object.freeze({ sheet, hidden_key: hiddenKey });
};

export const parseMemoryBlindEvaluationSheet = (value: unknown): Readonly<MemoryBlindEvaluationSheet> => {
  const root = exactRecord(value, [
    "version", "grading_protocol_version", "sheet_ref", "cohort_digest", "input_count",
    "result_count", "rendered_row_count", "human_answer_count", "machine_empty_count",
    "deduplicated_result_count", "rows", "hidden_key_digest", "blind_sheet_digest",
  ], "invalid_sheet");
  if (root["version"] !== SHEET_VERSION || root["grading_protocol_version"] !== MEMORY_EVALUATION_GRADING_PROTOCOL) {
    fail("invalid_sheet");
  }
  const rows = Object.freeze(exactArray(root["rows"], 0, MAX_ROWS, "invalid_sheet").map((value, index) => {
    const row = exactRecord(value, ["ordinal", "row_ref", "query_text", "answers"], "invalid_sheet_row");
    if (integer(row["ordinal"], MAX_ROWS - 1, "invalid_sheet_row") !== index) fail("invalid_sheet_row");
    const answers = Object.freeze(exactArray(row["answers"], 1, MAX_ANSWERS, "invalid_sheet_row")
      .map((value, answerIndex) => {
        const answer = exactRecord(value, ["ordinal", "answer_ref", "answer_text"], "invalid_sheet_answer");
        if (integer(answer["ordinal"], MAX_ANSWERS - 1, "invalid_sheet_answer") !== answerIndex) {
          fail("invalid_sheet_answer");
        }
        return Object.freeze({
          ordinal: answerIndex,
          answer_ref: ref(answer["answer_ref"], ANSWER_REF, "invalid_sheet_answer"),
          answer_text: text(answer["answer_text"], 65_536, "invalid_sheet_answer"),
        });
      }));
    unique(answers.map((answer) => answer.answer_ref), "invalid_sheet_row");
    return Object.freeze({
      ordinal: index,
      row_ref: ref(row["row_ref"], ROW_REF, "invalid_sheet_row"),
      query_text: text(row["query_text"], 4_096, "invalid_sheet_row"),
      answers,
    });
  }));
  unique(rows.map((row) => row.row_ref), "invalid_sheet");
  unique(rows.flatMap((row) => row.answers.map((answer) => answer.answer_ref)), "invalid_sheet");
  const humanCount = rows.reduce((sum, row) => sum + row.answers.length, 0);
  const core = Object.freeze({
    version: SHEET_VERSION,
    grading_protocol_version: MEMORY_EVALUATION_GRADING_PROTOCOL,
    sheet_ref: ref(root["sheet_ref"], SHEET_REF, "invalid_sheet"),
    cohort_digest: ref(root["cohort_digest"], DIGEST, "invalid_sheet"),
    input_count: integer(root["input_count"], MAX_ROWS, "invalid_sheet"),
    result_count: integer(root["result_count"], MAX_RESULTS, "invalid_sheet"),
    rendered_row_count: integer(root["rendered_row_count"], MAX_ROWS, "invalid_sheet"),
    human_answer_count: integer(root["human_answer_count"], MAX_ANSWERS, "invalid_sheet"),
    machine_empty_count: integer(root["machine_empty_count"], MAX_RESULTS, "invalid_sheet"),
    deduplicated_result_count: integer(root["deduplicated_result_count"], MAX_RESULTS, "invalid_sheet"),
    rows,
    hidden_key_digest: ref(root["hidden_key_digest"], DIGEST, "invalid_sheet"),
  });
  if (core.rendered_row_count !== rows.length || core.human_answer_count !== humanCount
    || core.rendered_row_count > core.input_count
    || core.machine_empty_count + core.human_answer_count + core.deduplicated_result_count !== core.result_count) {
    fail("invalid_sheet_counts");
  }
  const sheetDigest = ref(root["blind_sheet_digest"], DIGEST, "invalid_sheet");
  if (sheetDigest !== sha256CanonicalContent(core)) fail("invalid_sheet_digest");
  return Object.freeze({ ...core, blind_sheet_digest: sheetDigest });
};

export const parseMemoryBlindEvaluationKey = (value: unknown): Readonly<MemoryBlindEvaluationKey> => {
  const root = exactRecord(value, [
    "version", "cohort_digest", "result_count", "mappings", "machine_empty_labels", "hidden_key_digest",
  ], "invalid_hidden_key");
  if (root["version"] !== KEY_VERSION) fail("invalid_hidden_key");
  const mappings = Object.freeze(exactArray(root["mappings"], 0, MAX_ANSWERS, "invalid_hidden_key")
    .map((value) => {
      const mapping = exactRecord(value, ["answer_ref", "result_refs"], "invalid_hidden_mapping");
      const refs = Object.freeze(exactArray(mapping["result_refs"], 1, MAX_RESULTS, "invalid_hidden_mapping")
        .map((resultRef) => ref(resultRef, RESULT_REF, "invalid_hidden_mapping")));
      unique(refs, "invalid_hidden_mapping");
      if (refs.some((resultRef, index) => index > 0 && compare(refs[index - 1]!, resultRef) >= 0)) {
        fail("invalid_hidden_mapping");
      }
      return Object.freeze({
        answer_ref: ref(mapping["answer_ref"], ANSWER_REF, "invalid_hidden_mapping"),
        result_refs: refs,
      });
    }));
  const machine = Object.freeze(exactArray(root["machine_empty_labels"], 0, MAX_RESULTS, "invalid_hidden_key")
    .map((value) => {
      const label = exactRecord(value, ["result_ref", "grade"], "invalid_machine_label");
      if (label["grade"] !== "empty") fail("invalid_machine_label");
      return Object.freeze({ result_ref: ref(label["result_ref"], RESULT_REF, "invalid_machine_label"), grade: "empty" as const });
    }));
  unique(mappings.map((mapping) => mapping.answer_ref), "invalid_hidden_key");
  const allRefs = [...mappings.flatMap((mapping) => mapping.result_refs), ...machine.map((label) => label.result_ref)];
  unique(allRefs, "invalid_hidden_key");
  const core = Object.freeze({
    version: KEY_VERSION,
    cohort_digest: ref(root["cohort_digest"], DIGEST, "invalid_hidden_key"),
    result_count: integer(root["result_count"], MAX_RESULTS, "invalid_hidden_key"),
    mappings,
    machine_empty_labels: machine,
  });
  if (core.result_count !== allRefs.length) fail("invalid_hidden_key_counts");
  const hiddenDigest = ref(root["hidden_key_digest"], DIGEST, "invalid_hidden_key");
  if (hiddenDigest !== sha256CanonicalContent(core)) fail("invalid_hidden_key_digest");
  return Object.freeze({ ...core, hidden_key_digest: hiddenDigest });
};

export const expandMemoryBlindEvaluationGrades = (
  sheetValue: MemoryBlindEvaluationSheet,
  hiddenKeyValue: MemoryBlindEvaluationKey,
  graderSessionRefValue: string,
  gradeValues: readonly MemoryBlindHumanGrade[],
): Readonly<ExternalMemoryEvaluationLabels> => {
  const sheet = parseMemoryBlindEvaluationSheet(sheetValue);
  const hiddenKey = parseMemoryBlindEvaluationKey(hiddenKeyValue);
  if (sheet.cohort_digest !== hiddenKey.cohort_digest || sheet.hidden_key_digest !== hiddenKey.hidden_key_digest
    || sheet.result_count !== hiddenKey.result_count) fail("sheet_key_mismatch");
  const publicAnswerRefs = sheet.rows.flatMap((row) => row.answers.map((answer) => answer.answer_ref)).sort(compare);
  const hiddenAnswerRefs = hiddenKey.mappings.map((mapping) => mapping.answer_ref).sort(compare);
  if (publicAnswerRefs.length !== hiddenAnswerRefs.length
    || publicAnswerRefs.some((answerRef, index) => answerRef !== hiddenAnswerRefs[index])) fail("sheet_key_mismatch");
  const hiddenDeduplicated = hiddenKey.mappings.reduce(
    (total, mapping) => total + mapping.result_refs.length - 1,
    0,
  );
  if (hiddenKey.mappings.length !== sheet.human_answer_count
    || hiddenKey.machine_empty_labels.length !== sheet.machine_empty_count
    || hiddenDeduplicated !== sheet.deduplicated_result_count) fail("sheet_key_mismatch");
  const grades = exactArray(gradeValues, hiddenAnswerRefs.length, hiddenAnswerRefs.length, "invalid_human_grades")
    .map((value) => {
      const row = exactRecord(value, ["answer_ref", "grade"], "invalid_human_grade");
      if (!(row["grade"] === "correct" || row["grade"] === "partly"
        || row["grade"] === "wrong" || row["grade"] === "unsure")) fail("invalid_human_grade");
      return Object.freeze({
        answer_ref: ref(row["answer_ref"], ANSWER_REF, "invalid_human_grade"),
        grade: row["grade"] as Exclude<MemoryEvaluationGrade, "empty">,
      });
    });
  unique(grades.map((grade) => grade.answer_ref), "invalid_human_grades");
  const gradeByAnswer = new Map(grades.map((grade) => [grade.answer_ref, grade.grade]));
  if (hiddenAnswerRefs.some((answerRef) => !gradeByAnswer.has(answerRef))) fail("incomplete_human_grades");
  const resultGrades = [
    ...hiddenKey.mappings.flatMap((mapping) => mapping.result_refs.map((resultRef) => Object.freeze({
      result_ref: resultRef,
      grade: gradeByAnswer.get(mapping.answer_ref)!,
    }))),
    ...hiddenKey.machine_empty_labels,
  ].sort((left, right) => compare(left.result_ref, right.result_ref));
  const core = Object.freeze({
    version: MEMORY_EVALUATION_LABEL_VERSION,
    cohort_digest: sheet.cohort_digest,
    grading_protocol_version: MEMORY_EVALUATION_GRADING_PROTOCOL,
    grader_session_ref: ref(graderSessionRefValue, GRADER_REF, "invalid_grader_session"),
    blind_sheet_digest: sheet.blind_sheet_digest,
    hidden_key_digest: hiddenKey.hidden_key_digest,
    grades: Object.freeze(resultGrades),
  });
  return Object.freeze({ ...core, labels_digest: externalMemoryEvaluationLabelsDigest(core) });
};

export const MEMORY_BLIND_EVALUATION_SHEET_VERSION = SHEET_VERSION;
export const MEMORY_BLIND_EVALUATION_KEY_VERSION = KEY_VERSION;
