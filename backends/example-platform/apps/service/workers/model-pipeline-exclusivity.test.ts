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
      ? Object.freeze({ kind: "completed" as const, value: await callback(new AbortController().signal) })
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
    Object.freeze({ kind: "completed" as const, value: await callback(new AbortController().signal) }));
  await expect(port.runExclusive(resource("c"), async () => { throw new Error("model failed"); }))
    .rejects.toThrow("model failed");
});

test("a captured callback closes when the exclusivity adapter returns", async () => {
  let captured: ((lossSignal: AbortSignal) => Promise<string>) | undefined;
  let modelCalls = 0;
  const port = defineModelPipelineExclusivity(async (_coordinate, callback) => {
    captured = (lossSignal) => callback(lossSignal) as Promise<string>;
    return Object.freeze({ kind: "busy" as const });
  });
  await expect(port.runExclusive(resource("d"), async () => {
    modelCalls += 1;
    return "forbidden";
  })).resolves.toEqual({ kind: "busy" });
  await expect(captured!(new AbortController().signal)).rejects.toThrow("callback_closed");
  expect(modelCalls).toBe(0);
});

test("the exact implementation-provided loss signal reaches and drains the callback", async () => {
  const controller = new AbortController();
  let seen: AbortSignal | undefined;
  const port = defineModelPipelineExclusivity(async (_coordinate, callback) => {
    const pending = callback(controller.signal);
    controller.abort(new Error("lease lost"));
    return Object.freeze({ kind: "completed" as const, value: await pending });
  });
  await expect(port.runExclusive(resource("e"), async (signal) => {
    seen = signal;
    if (!signal.aborted) {
      await new Promise<void>((resolve) => signal.addEventListener("abort", () => resolve(), { once: true }));
    }
    return "drained";
  })).resolves.toEqual({ kind: "completed", value: "drained" });
  expect(seen).toBe(controller.signal);
  expect(seen?.aborted).toBeTrue();
});

test("connection loss may return unavailable after one drained callback", async () => {
  const controller = new AbortController();
  const port = defineModelPipelineExclusivity(async (_coordinate, callback) => {
    const pending = callback(controller.signal);
    controller.abort(new Error("lease lost"));
    await expect(pending).rejects.toThrow("lease lost");
    return Object.freeze({ kind: "unavailable" as const });
  });
  await expect(port.runExclusive(resource("f"), async (signal) => {
    if (signal.aborted) throw signal.reason;
    await new Promise<void>((_resolve, reject) => {
      signal.addEventListener("abort", () => reject(signal.reason), { once: true });
    });
    return "unreachable";
  })).resolves.toEqual({ kind: "unavailable" });
});
