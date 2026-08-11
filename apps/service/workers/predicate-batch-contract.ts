import type {
  PredicateAlignmentAdjudicationContract,
  PredicateAlignmentRequest,
} from "../../../core/consolidate/relations";
import type { RegisteredMemoryStrategy } from "../../../core/consolidate/strategy-assignment";
import { predicateAlignmentPromptCost } from "../../../drivers/model/glm";

export const PREDICATE_BATCH_PROMPT_BUDGET = 20_000;

export const predicateBatchPromptCost = (
  request: PredicateAlignmentRequest,
): number => predicateAlignmentPromptCost(request);

export const predicateBatchAdjudicationContract = (
  strategy: Readonly<RegisteredMemoryStrategy>,
): PredicateAlignmentAdjudicationContract => Object.freeze({
  model_version: strategy.coordinates.model_version,
  strategy: "predicate-alignment",
  prompt_version: strategy.coordinates.prompt_version,
  schema_version: strategy.coordinates.schema_version,
  code_version: strategy.coordinates.code_version,
});
