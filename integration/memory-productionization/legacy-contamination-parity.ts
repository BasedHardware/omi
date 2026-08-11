/**
 * QA-only compatibility census for the pre-v3 recall artifacts.
 *
 * This deliberately preserves the old whole-answer definition. It never
 * pretends logs without assertion manifests can satisfy the new assertion-local
 * provenance contract. Inputs are explicit copied files and SQLite is opened
 * read-only; the report contains counts and hashes, never answer/store content.
 */
import { Database } from "bun:sqlite";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

import { sha256CanonicalContent } from "../../core/retrieve/content-digest";

const SECOND_PERSON = /\b(you|your|you're|yours)\b/i;
const DIGEST = /^[a-f0-9]{64}$/;

export interface LegacyContaminationParityInput {
  readonly store_path: string;
  readonly baseline_pass_files: readonly [string, string];
  readonly candidate_pass_files: readonly [string, string];
}

export interface LegacyContaminationArmCounts {
  readonly rows: number;
  readonly answers: number;
  readonly second_person_answers: number;
  readonly contaminated_answers: number;
  readonly contaminated_percent_of_second_person: number;
}

export interface LegacyContaminationParityReport {
  readonly version: "legacy-contamination-parity-v1";
  readonly definition: "whole_answer_second_person_with_any_bystander_only_citation";
  readonly input_sha256: Readonly<{
    store: string;
    baseline_pass_1: string;
    baseline_pass_2: string;
    candidate_pass_1: string;
    candidate_pass_2: string;
  }>;
  readonly baseline: Readonly<LegacyContaminationArmCounts>;
  readonly candidate: Readonly<LegacyContaminationArmCounts>;
  readonly paired_population: number;
  readonly baseline_unpaired_rows: number;
  readonly both_contaminated: number;
  readonly baseline_only_contaminated: number;
  readonly candidate_only_contaminated: number;
  readonly neither_contaminated: number;
  readonly net_removed: number;
  readonly exact_mcnemar_two_sided_p: number;
  readonly model_calls: 0;
  readonly writes: 0;
  readonly report_digest: string;
}

interface Coordinate { readonly tiers: ReadonlySet<string> }
interface LogRow {
  readonly pair_key: string;
  readonly answer_text: string | null;
  readonly citations: readonly string[];
}

const fail = (code: string): never => { throw new TypeError(`legacy contamination parity ${code}`); };
const sha256File = (path: string): string => createHash("sha256").update(readFileSync(path)).digest("hex");

const parseJsonObject = (text: string, code: string): Record<string, unknown> => {
  let value: unknown;
  try { value = JSON.parse(text); } catch { return fail(code); }
  if (value === null || typeof value !== "object" || Array.isArray(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  return value as Record<string, unknown>;
};

const coordinatesFor = (path: string): ReadonlyMap<string, Coordinate> => {
  const db = new Database(path, { readonly: true, strict: true });
  try {
    const output = new Map<string, { tiers: Set<string> }>();
    const evidenceRows = db.query("SELECT content_json FROM evidence_revisions").all() as { content_json: string }[];
    for (const row of evidenceRows) {
      const record = parseJsonObject(row.content_json, "invalid_evidence_json");
      if (typeof record["evidence_id"] !== "string" || record["evidence_id"].length === 0) {
        fail("invalid_evidence_json");
      }
      if (output.has(record["evidence_id"])) fail("duplicate_evidence_id");
      output.set(record["evidence_id"], { tiers: new Set() });
    }
    const claimRows = db.query("SELECT content_json FROM claim_revisions WHERE lifecycle = 'canonical'").all() as { content_json: string }[];
    for (const row of claimRows) {
      const record = parseJsonObject(row.content_json, "invalid_claim_json");
      const evidenceRefs = record["evidence_refs"];
      const labels = record["policy_labels"];
      if (!Array.isArray(evidenceRefs) || !evidenceRefs.every((value) => typeof value === "string")
        || !Array.isArray(labels) || !labels.every((value) => typeof value === "string")) {
        fail("invalid_claim_json");
      }
      const tiers = labels.filter((label) => label.startsWith("subject:"));
      for (const evidenceRef of evidenceRefs) {
        const coordinate = output.get(evidenceRef);
        if (!coordinate) fail("claim_evidence_missing");
        for (const tier of tiers) coordinate.tiers.add(tier);
      }
    }
    return new Map([...output].map(([key, value]) => [key, Object.freeze({ tiers: new Set(value.tiers) })]));
  } finally {
    db.close(false);
  }
};

const parsePass = (path: string, pass: 1 | 2): readonly LogRow[] => {
  const bytes = readFileSync(path, "utf8");
  const rows: LogRow[] = [];
  for (const line of bytes.split("\n")) {
    if (!line) continue;
    const record = parseJsonObject(line, "invalid_log_json");
    const query = record["query"];
    const answer = record["answer_text"];
    const citationValue = record["citations"];
    if (typeof query !== "string" || query.length === 0
      || (answer !== null && typeof answer !== "string")
      || !Array.isArray(citationValue)
      || !citationValue.every((value) => typeof value === "string" && value.length > 0)) {
      fail("invalid_log_row");
    }
    const citations = citationValue as string[];
    if (new Set(citations).size !== citations.length) fail("duplicate_citation");
    rows.push(Object.freeze({ pair_key: `${pass}:${query}`, answer_text: answer as string | null, citations: Object.freeze([...citations]) }));
  }
  return Object.freeze(rows);
};

const loadArm = (files: readonly [string, string]): ReadonlyMap<string, LogRow> => {
  const rows = [...parsePass(files[0], 1), ...parsePass(files[1], 2)];
  const output = new Map<string, LogRow>();
  for (const row of rows) {
    if (output.has(row.pair_key)) fail("duplicate_pair_key");
    output.set(row.pair_key, row);
  }
  return output;
};

const contaminated = (row: LogRow, coordinates: ReadonlyMap<string, Coordinate>): boolean => {
  if (!row.answer_text || !SECOND_PERSON.test(row.answer_text)) return false;
  return row.citations.some((citation) => {
    const coordinate = coordinates.get(citation);
    if (!coordinate) fail("citation_not_in_store");
    return coordinate.tiers.has("subject:bystander")
      && !coordinate.tiers.has("subject:owner")
      && !coordinate.tiers.has("subject:owner_context");
  });
};

const armCounts = (
  rows: ReadonlyMap<string, LogRow>,
  coordinates: ReadonlyMap<string, Coordinate>,
): Readonly<LegacyContaminationArmCounts> => {
  const values = [...rows.values()];
  const answers = values.filter((row) => Boolean(row.answer_text));
  const secondPerson = answers.filter((row) => SECOND_PERSON.test(row.answer_text!));
  const contaminatedAnswers = secondPerson.filter((row) => contaminated(row, coordinates));
  return Object.freeze({
    rows: values.length,
    answers: answers.length,
    second_person_answers: secondPerson.length,
    contaminated_answers: contaminatedAnswers.length,
    contaminated_percent_of_second_person: secondPerson.length
      ? Math.round((contaminatedAnswers.length * 10_000) / secondPerson.length) / 100
      : 0,
  });
};

const binomialCoefficient = (n: number, k: number): number => {
  const limit = Math.min(k, n - k);
  let value = 1;
  for (let index = 1; index <= limit; index += 1) value = (value * (n - limit + index)) / index;
  return value;
};

const exactMcNemar = (left: number, right: number): number => {
  const discordant = left + right;
  if (discordant === 0) return 1;
  const tail = Math.min(left, right);
  let probability = 0;
  for (let index = 0; index <= tail; index += 1) {
    probability += binomialCoefficient(discordant, index) * (0.5 ** discordant);
  }
  return Math.min(1, 2 * probability);
};

export const auditLegacyContaminationParity = (
  input: LegacyContaminationParityInput,
): Readonly<LegacyContaminationParityReport> => {
  const coordinates = coordinatesFor(input.store_path);
  const baselineRows = loadArm(input.baseline_pass_files);
  const candidateRows = loadArm(input.candidate_pass_files);
  if ([...candidateRows.keys()].some((key) => !baselineRows.has(key))) fail("candidate_population_not_baseline_subset");

  let both = 0;
  let baselineOnly = 0;
  let candidateOnly = 0;
  let neither = 0;
  for (const [key, candidateRow] of candidateRows) {
    const baselineRow = baselineRows.get(key)!;
    const baselineValue = contaminated(baselineRow, coordinates);
    const candidateValue = contaminated(candidateRow, coordinates);
    if (baselineValue && candidateValue) both += 1;
    else if (baselineValue) baselineOnly += 1;
    else if (candidateValue) candidateOnly += 1;
    else neither += 1;
  }
  const core = Object.freeze({
    version: "legacy-contamination-parity-v1" as const,
    definition: "whole_answer_second_person_with_any_bystander_only_citation" as const,
    input_sha256: Object.freeze({
      store: sha256File(input.store_path),
      baseline_pass_1: sha256File(input.baseline_pass_files[0]),
      baseline_pass_2: sha256File(input.baseline_pass_files[1]),
      candidate_pass_1: sha256File(input.candidate_pass_files[0]),
      candidate_pass_2: sha256File(input.candidate_pass_files[1]),
    }),
    baseline: armCounts(baselineRows, coordinates),
    candidate: armCounts(candidateRows, coordinates),
    paired_population: candidateRows.size,
    baseline_unpaired_rows: baselineRows.size - candidateRows.size,
    both_contaminated: both,
    baseline_only_contaminated: baselineOnly,
    candidate_only_contaminated: candidateOnly,
    neither_contaminated: neither,
    net_removed: baselineOnly - candidateOnly,
    exact_mcnemar_two_sided_p: exactMcNemar(baselineOnly, candidateOnly),
    model_calls: 0 as const,
    writes: 0 as const,
  });
  const report = Object.freeze({ ...core, report_digest: sha256CanonicalContent(core) });
  if (!DIGEST.test(report.report_digest)) fail("invalid_report_digest");
  return report;
};

const flag = (args: readonly string[], name: string): string => {
  const index = args.indexOf(`--${name}`);
  if (index < 0 || index === args.length - 1 || args[index + 1]!.startsWith("--")) fail(`missing_${name}`);
  return args[index + 1]!;
};

export const assertInheritedVoiceParity = (report: LegacyContaminationParityReport): void => {
  const expected = report.baseline.rows === 50
    && report.baseline.answers === 43
    && report.baseline.second_person_answers === 39
    && report.baseline.contaminated_answers === 21
    && report.candidate.rows === 41
    && report.candidate.answers === 37
    && report.candidate.second_person_answers === 37
    && report.candidate.contaminated_answers === 11
    && report.paired_population === 41
    && report.baseline_unpaired_rows === 9
    && report.baseline_only_contaminated === 15
    && report.candidate_only_contaminated === 5
    && Math.abs(report.exact_mcnemar_two_sided_p - 0.04138946533203125) < Number.EPSILON;
  if (!expected) fail("inherited_voice_parity_mismatch");
};

if (import.meta.main) {
  const args = Bun.argv.slice(2);
  const report = auditLegacyContaminationParity({
    store_path: flag(args, "store"),
    baseline_pass_files: [flag(args, "baseline-pass-1"), flag(args, "baseline-pass-2")],
    candidate_pass_files: [flag(args, "candidate-pass-1"), flag(args, "candidate-pass-2")],
  });
  if (args.includes("--expect-inherited-voice-v1")) assertInheritedVoiceParity(report);
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
}
