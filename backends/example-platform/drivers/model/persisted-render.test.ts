import { expect, test } from "bun:test";
import { createPersistedRenderModel } from "./persisted-render";
import { readAfterApplicationAuthorization } from "../../core/retrieve/authorization-boundary";
import { snapshot } from "../../core/retrieve/tree.fixture";
import { buildDeterministicAnchors } from "../../core/retrieve/tree";
import { isProducedRenderNode, renderStructuralTree } from "../../core/retrieve/render";

const projected = () => readAfterApplicationAuthorization({
  owner_account_id: "owner",
  credential: { owner_account_id: "owner", credential_kind: "mcp_api_key", app_id: "app:a", key_id: "key:a", scopes: ["memories.read"], active: true },
  persisted_grant: { owner_account_id: "owner", consumer: "mcp", app_id: "app:a", key_id: "key:a", enabled: true, default_read: true, scopes: ["memories.read"] },
}, () => ({ snapshot: snapshot(), options: { account_timezone: "UTC" } }));
const options = { strategy: "test", model_version: "v1", prompt_version: "v1", policy_version: "v1", schema_version: "v1" };

test("persisted grounded responses recreate identical branded renders and bind render versions", async () => {
  const rows = new Map<string, string>();
  let calls = 0;
  const input = projected();
  const make = (renderOptions = options) => createPersistedRenderModel({
    projected: input, options: renderOptions,
    model: { render: async () => ({ summary_text: `Summary ${++calls}`, citations: ["e1"] }) },
    read: async key => rows.get(key) ?? null,
    publish: async (key, response) => { if (!rows.has(key)) rows.set(key, response); return rows.get(key)!; },
  });
  const tree = buildDeterministicAnchors(input);
  const first = await renderStructuralTree(tree, input, make(), options);
  const priorCalls = calls;
  const resumed = await renderStructuralTree(tree, input, make(), options);
  expect(first.length).toBeGreaterThan(0);
  expect(resumed).toEqual(first);
  expect(resumed.every(isProducedRenderNode)).toBe(true);
  expect(calls).toBe(priorCalls);
  const updated = { ...options, prompt_version: "v2" };
  await renderStructuralTree(tree, input, make(updated), updated);
  expect(calls).toBeGreaterThan(priorCalls);
});

test("cache corruption and provider output with unsupported citations fail before publication", async () => {
  let publications = 0;
  for (const cached of [null, JSON.stringify({ summary_text: "Forged", citations: ["private-evidence"] })]) {
    const model = createPersistedRenderModel({
      projected: projected(), options,
      model: { render: async () => ({ summary_text: "Forged", citations: ["private-evidence"] }) },
      read: async () => cached,
      publish: async (_key, response) => { publications++; return response; },
    });
    await expect(model.render({ strategy: "test", version: "v1", input: { claims: [{ evidence_refs: ["e1"] }] } })).rejects.toThrow("ungrounded_render_response");
  }
  expect(publications).toBe(0);
});
