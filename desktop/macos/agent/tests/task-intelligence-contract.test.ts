import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

function readJson(relativePath: string): Record<string, unknown> {
  const path = resolve(process.cwd(), "../../..", relativePath);
  return JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;
}

describe("task intelligence v1 contract", () => {
  it("publishes the kernel bridge schema and an example", () => {
    const contract = readJson(
      "backend/config/task_intelligence_contract_v1.json",
    );
    const definitions = contract.$defs as Record<string, unknown>;
    const examples = contract.examples as Record<string, unknown>;

    expect(contract.schema_version).toBe(1);
    expect(definitions.kernel_workstream_bridge).toBeDefined();
    expect(examples.kernel_workstream_bridge).toBeDefined();
  });

  it("keeps recorded capture adapter outputs identical across modalities", () => {
    const fixture = readJson(
      "backend/tests/unit/fixtures/task_intelligence/capture_v1.json",
    );
    const cases = fixture.cases as Array<Record<string, unknown>>;

    for (const testCase of cases) {
      const inputs = testCase.inputs as Record<string, Record<string, unknown>>;
      expect(inputs.transcript.stub_output).toEqual(inputs.screen.stub_output);
    }
  });
});
