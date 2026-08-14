import type { PredicateBatchPromptBudget } from "../../apps/service/workers/predicate-batch-contract";
import { predicateAlignmentPromptCost } from "./glm";

/**
 * The GLM binding for predicate-batch admission.
 *
 * This is the only place the GLM prompt template prices production work. It
 * lives on the provider side deliberately: `predicate-batch-contract.ts` used
 * to value-import this function, which linked the whole GLM client — base URL,
 * HTTP, retry, repair — into every image running predicate-batch consolidation,
 * and pinned a production admission decision to one provider's wording.
 *
 * The units are characters of the rendered GLM prompt, which is what
 * `promptForPredicateAlignment(...).length` returns. Any other adapter must
 * supply its own binding in its own units rather than reusing this budget: the
 * number 20,000 means nothing outside this template.
 */
export const GLM_PREDICATE_BATCH_PROMPT_BUDGET: PredicateBatchPromptBudget = Object.freeze({
  cost: predicateAlignmentPromptCost,
  budget: 20_000,
});
