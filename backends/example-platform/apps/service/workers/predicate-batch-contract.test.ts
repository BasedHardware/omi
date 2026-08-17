import { describe, expect, test } from "bun:test";

import { GLM_PREDICATE_BATCH_PROMPT_BUDGET } from "../../../drivers/model/predicate-batch-bindings";
import { assertPredicateBatchPromptBudget } from "./predicate-batch-contract";

describe("predicate batch prompt budget binding", () => {
  test("this module names no provider", async () => {
    // The defect this fence exists for: `predicateAlignmentPromptCost` used to
    // be value-imported from `drivers/model/glm` here, which linked the whole
    // GLM client into every image running predicate-batch consolidation and
    // made a production admission decision out of one provider's prompt
    // wording. Assert the import is gone at the source, not just in a trace.
    const source = await Bun.file(
      new URL("./predicate-batch-contract.ts", import.meta.url),
    ).text();
    // Match import specifiers only. The doc comment above the interface names
    // `drivers/model/glm` deliberately, to record what this fence is for; a
    // naive substring check would forbid explaining the defect it prevents.
    const specifiers = [...source.matchAll(/from\s*["']([^"']+)["']/g)].map((match) => match[1]!);
    expect(specifiers.length).toBeGreaterThan(0);
    expect(specifiers.filter((specifier) => specifier.includes("drivers/model"))).toEqual([]);
    // And no value import of any kind survives: the module is types-only plus
    // its own two functions.
    expect(source).not.toMatch(/^import\s+(?!type\b)/m);
  });

  test("accepts a well-formed binding and freezes it", () => {
    const budget = assertPredicateBatchPromptBudget({ cost: () => 1, budget: 20_000 });
    expect(budget.budget).toBe(20_000);
    expect(Object.isFrozen(budget)).toBe(true);
  });

  test("the GLM binding is well-formed", () => {
    const budget = assertPredicateBatchPromptBudget(GLM_PREDICATE_BATCH_PROMPT_BUDGET);
    expect(budget.budget).toBe(20_000);
    expect(typeof budget.cost).toBe("function");
  });

  test("fails closed rather than admitting an unbounded batch", () => {
    const rejected: readonly unknown[] = [
      null,
      undefined,
      [],
      "20000",
      {},
      { cost: () => 1 },
      { budget: 20_000 },
      { cost: 20_000, budget: 20_000 },
      { cost: () => 1, budget: 0 },
      { cost: () => 1, budget: -1 },
      { cost: () => 1, budget: 1.5 },
      { cost: () => 1, budget: Number.NaN },
      { cost: () => 1, budget: Number.POSITIVE_INFINITY },
      { cost: () => 1, budget: "20000" },
    ];
    for (const value of rejected) {
      expect(() => assertPredicateBatchPromptBudget(value)).toThrow("predicate batch prompt budget");
    }
  });
});
