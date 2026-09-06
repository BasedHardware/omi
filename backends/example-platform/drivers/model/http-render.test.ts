import { expect, test } from "bun:test";
import { createHttpRenderModel } from "./http-render";
import { projectTreeInputSnapshot } from "../../core/retrieve/index";
import { snapshot } from "../../core/retrieve/tree.fixture";
import { buildDeterministicAnchors } from "../../core/retrieve/tree";
import { isProducedRenderNode, renderStructuralTree } from "../../core/retrieve/render";

const options = { endpoint: "https://gateway.example/v1/chat/completions", apiKey: "test-only", laneId: "omi:auto:memory-render", firebaseUid: "firebase-user-different-from-owner" };
test("real structural renderer consumes grounded gateway JSON and preserves semantic routing", async () => {
  const calls: RequestInit[] = [];
  const model = createHttpRenderModel({ ...options, fetch: (async (_url, init) => {
    calls.push(init!);
    return Response.json({ choices: [{ message: { content: JSON.stringify({ summary_text: "Supported summary", citations: ["e1"] }) } }] });
  }) });
  const input = projectTreeInputSnapshot(snapshot(), { account_timezone: "UTC" });
  const renders = await renderStructuralTree(buildDeterministicAnchors(input), input, model, {
    strategy: "test", model_version: options.laneId, prompt_version: "v1", policy_version: "v1", schema_version: "v1",
  });
  expect(renders.length).toBeGreaterThan(0);
  expect(renders.every(render => isProducedRenderNode(render) && render.status === "ready")).toBe(true);
  expect(JSON.parse(String(calls[0]!.body)).model).toBe(options.laneId);
  expect(new Headers(calls[0]!.headers).get("x-omi-user-uid")).toBe("firebase-user-different-from-owner");
  expect(calls[0]!.redirect).toBe("error");
});

test("provider failures, forged citations and oversized bodies cannot yield a render", async () => {
  for (const response of [
    new Response("secret provider error", { status: 500 }),
    Response.json({ choices: [{ message: { content: JSON.stringify({ summary_text: "Forged", citations: ["hidden-evidence"] }) } }] }),
    new Response("x".repeat(262145)),
  ]) {
    const model = createHttpRenderModel({ ...options, fetch: (async () => response) });
    await expect(model.render({ strategy: "test", version: "v1", input: { claims: [{ evidence_refs: ["e1"] }] } })).rejects.toThrow("render_provider_unavailable");
  }
  expect(() => createHttpRenderModel({ ...options, laneId: "provider-model" })).toThrow();
  expect(() => createHttpRenderModel({ ...options, endpoint: "http://gateway.example" })).toThrow();
});

test("request cancellation stops an already-open provider body", async () => {
  const controller = new AbortController();
  let cancelled = 0;
  let providerSignal: AbortSignal | null = null;
  const model = createHttpRenderModel({ ...options, signal: controller.signal, fetch: async (_url, init) => {
    providerSignal = init.signal!;
    return new Response(new ReadableStream({
      pull() { controller.abort(); },
      cancel() { cancelled += 1; },
    }));
  } });
  await expect(model.render({ strategy: "test", version: "v1", input: { claims: [{ evidence_refs: ["e1"] }] } })).rejects.toThrow("render_provider_unavailable");
  expect(cancelled).toBe(1);
  expect((providerSignal as AbortSignal | null)?.aborted).toBe(true);
});
