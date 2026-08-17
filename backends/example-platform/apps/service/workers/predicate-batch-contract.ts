import type {
  PredicateAlignmentAdjudicationContract,
  PredicateAlignmentRequest,
} from "../../../core/consolidate/relations";
import type { RegisteredMemoryStrategy } from "../../../core/consolidate/strategy-assignment";

/**
 * How many predicates fit in one adjudication batch is a property of the model
 * that will answer it, not of this module. The prompt template belongs to the
 * adapter, so only the adapter can price it and only the adapter knows its own
 * context ceiling.
 *
 * This used to be `predicateAlignmentPromptCost` value-imported from
 * `drivers/model/glm`, with a flat 20,000 budget. That had two costs. It linked
 * the GLM provider client into every image that runs predicate-batch
 * consolidation, and — worse — it made a production admission decision out of
 * the character length of one specific provider's prompt wording, so editing
 * that wording silently changed production batching and pointing at any other
 * serving model left the budget measuring the wrong template entirely.
 *
 * Injected instead, in the shape ratified for the `apps/qa` read-composition
 * split: the construction site names the binding, the worker stays
 * provider-neutral.
 */
export interface PredicateBatchPromptBudget {
  /** Prices one request in the adapter's own units. */
  readonly cost: (request: PredicateAlignmentRequest) => number;
  /** The adapter's ceiling, in the same units `cost` returns. */
  readonly budget: number;
}

const fail = (code: string): never => {
  throw new TypeError(`predicate batch prompt budget ${code}`);
};

/** Fail closed: a malformed binding must not silently admit an unbounded batch. */
export const assertPredicateBatchPromptBudget = (
  value: unknown,
): PredicateBatchPromptBudget => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) fail("invalid_binding");
  const record = value as { cost?: unknown; budget?: unknown };
  if (typeof record.cost !== "function") fail("invalid_cost");
  if (!Number.isSafeInteger(record.budget) || (record.budget as number) < 1) fail("invalid_budget");
  return Object.freeze({
    cost: record.cost as (request: PredicateAlignmentRequest) => number,
    budget: record.budget as number,
  });
};

export const predicateBatchAdjudicationContract = (
  strategy: Readonly<RegisteredMemoryStrategy>,
): PredicateAlignmentAdjudicationContract => Object.freeze({
  model_version: strategy.coordinates.model_version,
  strategy: "predicate-alignment",
  prompt_version: strategy.coordinates.prompt_version,
  schema_version: strategy.coordinates.schema_version,
  code_version: strategy.coordinates.code_version,
});
