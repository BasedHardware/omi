import { Database } from "bun:sqlite";
import { afterEach, describe, expect, test } from "bun:test";
import { mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { auditLegacyContaminationParity } from "./legacy-contamination-parity";

const roots: string[] = [];
afterEach(() => { for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true }); });

const fixture = () => {
  const root = mkdtempSync(join(tmpdir(), "legacy-contamination-parity-"));
  roots.push(root);
  const store = join(root, "copied.sqlite");
  const db = new Database(store);
  db.exec("CREATE TABLE evidence_revisions (content_json TEXT NOT NULL); CREATE TABLE claim_revisions (lifecycle TEXT NOT NULL, content_json TEXT NOT NULL)");
  db.query("INSERT INTO evidence_revisions VALUES (?)").run(JSON.stringify({ evidence_id: "e-owner" }));
  db.query("INSERT INTO evidence_revisions VALUES (?)").run(JSON.stringify({ evidence_id: "e-other" }));
  db.query("INSERT INTO claim_revisions VALUES ('canonical', ?)").run(JSON.stringify({ evidence_refs: ["e-owner"], policy_labels: ["subject:owner"] }));
  db.query("INSERT INTO claim_revisions VALUES ('canonical', ?)").run(JSON.stringify({ evidence_refs: ["e-other"], policy_labels: ["subject:bystander"] }));
  db.close(false);
  const write = (name: string, rows: readonly unknown[]) => {
    const path = join(root, name);
    writeFileSync(path, `${rows.map((row) => JSON.stringify(row)).join("\n")}\n`);
    return path;
  };
  const baseline1 = write("baseline-p1.jsonl", [
    { query: "role", answer_text: "Your role is builder.", citations: ["e-other"] },
    { query: "empty", answer_text: null, citations: [] },
  ]);
  const baseline2 = write("baseline-p2.jsonl", [
    { query: "role", answer_text: "Your role is builder.", citations: ["e-other"] },
  ]);
  const candidate1 = write("candidate-p1.jsonl", [
    { query: "role", answer_text: "Someone said the role is builder.", citations: ["e-other"] },
    { query: "empty", answer_text: null, citations: [] },
  ]);
  const candidate2 = write("candidate-p2.jsonl", [
    { query: "role", answer_text: "Your role is builder.", citations: ["e-owner"] },
  ]);
  return { root, store, baseline1, baseline2, candidate1, candidate2 };
};

describe("legacy answer-wide contamination compatibility census", () => {
  test("is read-only, hashes every input, and pairs only the candidate's declared population", () => {
    const input = fixture();
    const before = [input.store, input.baseline1, input.baseline2, input.candidate1, input.candidate2]
      .map((path) => ({ path, bytes: readFileSync(path), mtime: statSync(path).mtimeMs }));
    const report = auditLegacyContaminationParity({
      store_path: input.store,
      baseline_pass_files: [input.baseline1, input.baseline2],
      candidate_pass_files: [input.candidate1, input.candidate2],
    });
    expect(report).toMatchObject({
      definition: "whole_answer_second_person_with_any_bystander_only_citation",
      baseline: { rows: 3, answers: 2, second_person_answers: 2, contaminated_answers: 2 },
      candidate: { rows: 3, answers: 2, second_person_answers: 1, contaminated_answers: 0 },
      paired_population: 3,
      baseline_unpaired_rows: 0,
      baseline_only_contaminated: 2,
      candidate_only_contaminated: 0,
      model_calls: 0,
      writes: 0,
    });
    for (const digest of Object.values(report.input_sha256)) expect(digest).toMatch(/^[a-f0-9]{64}$/);
    for (const item of before) {
      expect(readFileSync(item.path)).toEqual(item.bytes);
      expect(statSync(item.path).mtimeMs).toBe(item.mtime);
    }
    expect(JSON.stringify(report)).not.toMatch(/builder|e-owner|e-other|subject:/);
  });

  test("rejects candidate-only cells and citations absent from the copied store", () => {
    const input = fixture();
    writeFileSync(input.candidate2, `${JSON.stringify({ query: "candidate-only", answer_text: "You know it.", citations: ["e-owner"] })}\n`);
    expect(() => auditLegacyContaminationParity({
      store_path: input.store,
      baseline_pass_files: [input.baseline1, input.baseline2],
      candidate_pass_files: [input.candidate1, input.candidate2],
    })).toThrow("candidate_population_not_baseline_subset");

    writeFileSync(input.candidate2, `${JSON.stringify({ query: "role", answer_text: "You know it.", citations: ["missing"] })}\n`);
    expect(() => auditLegacyContaminationParity({
      store_path: input.store,
      baseline_pass_files: [input.baseline1, input.baseline2],
      candidate_pass_files: [input.candidate1, input.candidate2],
    })).toThrow("citation_not_in_store");
  });
});
