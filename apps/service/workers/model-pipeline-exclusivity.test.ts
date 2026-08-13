import { expect, test } from "bun:test";

import {
  defineModelPipelineExclusivity,
  MODEL_PIPELINE_RESOURCE_VERSION,
} from "./model-pipeline-exclusivity";

const resource = (fill: string) => Object.freeze({
  version: MODEL_PIPELINE_RESOURCE_VERSION,
  resource_digest: fill.repeat(64),
});

test("model pipeline exclusivity validates resources and exact outcomes", async () => {
  const port = defineModelPipelineExclusivity(async (coordinate, callback) =>
    coordinate.resource_digest.startsWith("a")
      ? Object.freeze({ kind: "completed" as const, value: await callback() })
      : Object.freeze({ kind: "busy" as const }));
  await expect(port.runExclusive(resource("a"), async () => "done"))
    .resolves.toEqual({ kind: "completed", value: "done" });
  await expect(port.runExclusive(resource("b"), async () => "never"))
    .resolves.toEqual({ kind: "busy" });
  await expect(port.runExclusive({ ...resource("a"), resource_digest: "raw-key" }, async () => null))
    .rejects.toThrow("invalid_resource");
});

test("a callback error remains attributable to the model phase", async () => {
  const port = defineModelPipelineExclusivity(async (_coordinate, callback) =>
    Object.freeze({ kind: "completed" as const, value: await callback() }));
  await expect(port.runExclusive(resource("c"), async () => { throw new Error("model failed"); }))
    .rejects.toThrow("model failed");
});

test("a captured callback closes when the exclusivity adapter returns", async () => {
  let captured: (() => Promise<string>) | undefined;
  let modelCalls = 0;
  const port = defineModelPipelineExclusivity(async (_coordinate, callback) => {
    captured = callback;
    return Object.freeze({ kind: "busy" as const });
  });
  await expect(port.runExclusive(resource("d"), async () => {
    modelCalls += 1;
    return "forbidden";
  })).resolves.toEqual({ kind: "busy" });
  await expect(captured!()).rejects.toThrow("callback_closed");
  expect(modelCalls).toBe(0);
});
