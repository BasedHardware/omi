#!/usr/bin/env bun

import { Database } from "bun:sqlite";
import { predicateIdForName, predicateRevisionForObservation } from "../core/consolidate/predicate-identity";
import {
  invokePredicateAlignment,
  type PredicateAlignmentAdjudicationContract,
  type PredicateAlignmentBatchSuccess,
  type PredicateAlignmentRequest,
} from "../core/consolidate/relations";
import type { Predicate } from "../core/schema";
import { predicateAlignmentPromptCost } from "../drivers/model/glm";

type Row = { predicate_id: string; name: string; slot_ids: readonly string[] };
const BUDGET = 20_000;
const contract: PredicateAlignmentAdjudicationContract = {
  model_version: "census-no-model",
  strategy: "predicate-alignment",
  prompt_version: "predicate-prompt-v2",
  schema_version: "predicate-response-v2",
  code_version: "relations-exhaustive-v3",
};

const load = (path: string): Row[] => {
  const db = new Database(path, { readonly: true, strict: true });
  try {
    const merged = new Map<string, { name: string; roles: Set<string> }>();
    for (const raw of db.query<{ predicate_id: string; content_json: string }, []>(
      "SELECT predicate_id, content_json FROM predicate_revisions",
    ).all()) {
      const value = JSON.parse(raw.content_json) as Record<string, unknown>;
      const name = value.identity_name ?? value.display_name;
      const roles = value.observed_roles ?? value.slot_ids ?? [];
      if (typeof name !== "string" || !Array.isArray(roles)
        || roles.some((role) => typeof role !== "string")) throw new Error("invalid predicate artifact");
      const entry = merged.get(raw.predicate_id) ?? { name, roles: new Set<string>() };
      for (const role of roles as string[]) entry.roles.add(role);
      merged.set(raw.predicate_id, entry);
    }
    return [...merged.entries()].map(([predicate_id, entry]) => ({
      predicate_id,
      name: entry.name,
      slot_ids: [...entry.roles].sort(),
    })).sort((left, right) => left.name.localeCompare(right.name)
      || left.predicate_id.localeCompare(right.predicate_id));
  } finally {
    db.close();
  }
};

const canonicalPredicates = (rows: readonly Row[]): Predicate[] => rows.map((row) =>
  predicateRevisionForObservation({
    owner_account_id: "owner:census",
    predicate_id: row.predicate_id,
    display_name: row.name,
    roles: row.slot_ids,
    lifecycle: "canonical",
  }).predicate);

const run = async (
  predicates: readonly Predicate[],
  successes: readonly PredicateAlignmentBatchSuccess[] = [],
) => {
  const requests: PredicateAlignmentRequest[] = [];
  const started = performance.now();
  const result = await invokePredicateAlignment({ invoke: async ({ input }) => {
    requests.push(input as PredicateAlignmentRequest);
    return { assertions: [] };
  } }, predicates, {
    owner_account_id: "owner:census",
    batch_prompt_budget: BUDGET,
    model_concurrency: 1,
    max_questions_per_invocation: 768,
    prompt_cost: predicateAlignmentPromptCost,
    adjudication_contract: contract,
    successful_questions: successes,
  });
  return {
    requests,
    result,
    elapsed_milliseconds: Math.round(performance.now() - started),
    successes: result.batch_outcomes.filter((outcome): outcome is PredicateAlignmentBatchSuccess => outcome.kind === "success"),
  };
};

const main = async (): Promise<void> => {
  const path = process.argv[2];
  if (!path) throw new Error("usage: predicate-coverage-census.ts <v9.sqlite>");
  const rows = load(path);
  const predicates = canonicalPredicates(rows);
  const initial = await run(predicates);
  const reversed = await run([...predicates].reverse());
  const shuffled = await run([...predicates].sort((left, right) =>
    left.predicate_id.slice(-16).localeCompare(right.predicate_id.slice(-16))));
  const added = predicateRevisionForObservation({
    owner_account_id: "owner:census",
    predicate_id: predicateIdForName("census new predicate"),
    display_name: "census new predicate",
    roles: ["subject"],
    lifecycle: "canonical",
  }).predicate;
  const incremental = await run([...predicates, added], initial.successes);
  const signature = (requests: readonly PredicateAlignmentRequest[]): string => JSON.stringify(requests);
  const costs = (requests: readonly PredicateAlignmentRequest[]) => requests.map(predicateAlignmentPromptCost);
  console.log(JSON.stringify({
    vocabulary: rows.length,
    total_pairs: rows.length * (rows.length - 1) / 2,
    covered_pairs: initial.result.coverage.planned_newly_covered_pairs,
    initial_questions: initial.requests.length,
    initial_min_rows: Math.min(...initial.requests.map((request) => request.predicates.length)),
    initial_max_rows: Math.max(...initial.requests.map((request) => request.predicates.length)),
    initial_max_cost: Math.max(...costs(initial.requests)),
    initial_total_cost: costs(initial.requests).reduce((sum, cost) => sum + cost, 0),
    initial_elapsed_milliseconds: initial.elapsed_milliseconds,
    reversed_byte_identical: signature(initial.requests) === signature(reversed.requests),
    shuffled_byte_identical: signature(initial.requests) === signature(shuffled.requests),
    incremental_questions: incremental.requests.length,
    incremental_max_cost: Math.max(...costs(incremental.requests)),
    incremental_total_cost: costs(incremental.requests).reduce((sum, cost) => sum + cost, 0),
    incremental_covered_before_plan: incremental.result.coverage.covered_pairs_before_plan,
    incremental_new_pairs: incremental.result.coverage.planned_newly_covered_pairs,
    incremental_remaining_pairs: incremental.result.coverage.remaining_pairs_after_plan,
    block_sizes: initial.requests.map((request) => request.predicates.length),
    incremental_block_sizes: incremental.requests.map((request) => request.predicates.length),
  }, null, 2));
};

await main();
