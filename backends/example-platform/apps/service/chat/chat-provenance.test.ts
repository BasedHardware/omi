import { expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { createLocalDevService } from "../app-facing";
import { createGatewayChatGenerationSource, readChatGenerationSourceCapability } from "./generation-source";
import { probeGatewayEngineIdentity, stampForGatewayEngine } from "./gateway-engine-identity";
import { reportForLegacyChatCapability } from "./capability-tier-report";

const here = dirname(fileURLToPath(import.meta.url));
const cannedGateway = join(here, "../../../integration/local-test-gateway.mjs");
const CANNED_OUTPUT = "Local test gateway answered.";
const REAL_PROVIDER_LABEL = "External model response";

const parseServiceSse = (text: string): readonly Record<string, unknown>[] =>
  Object.freeze(text.split("\n\n")
    .filter((block) => block.trim().length > 0)
    .map((block) => JSON.parse(block.split("\n")
      .find((line) => line.startsWith("data: "))!.slice(6)) as Record<string, unknown>));

const chatPayload = (id: string, text: string) => ({
  op: "create",
  opId: `op-${id}`,
  id,
  at: 1_786_352_400_000,
  text,
  sender: "human",
  journalRevision: 1,
  type: "text",
  appId: null,
  chatSessionId: null,
  messageSource: "desktop_chat",
  metadata: null,
  attachmentIds: [],
});

const waitForReady = async (readyPath: string, timeoutMs = 5_000): Promise<Record<string, unknown>> => {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      return JSON.parse(readFileSync(readyPath, "utf8")) as Record<string, unknown>;
    } catch {
      await Bun.sleep(25);
    }
  }
  throw new Error("gateway wrote no readiness record");
};

test("negative control: canned gateway answer is canned and the real-provider label is absent", async () => {
  // red-proof: if stampForGatewayEngine minted real-provider from this /ready,
  // the receipt tier would be real-provider and ChatProduction would render
  // "External model response". The canned SSE is "Local test gateway answered."
  const scratch = mkdtempSync(join(tmpdir(), "omi-chat-provenance-canned-"));
  const readyPath = join(scratch, "ready.json");
  const child = spawn("bun", [cannedGateway], {
    env: {
      ...process.env,
      OMI_LOCAL_TEST_GATEWAY_PORT: "0",
      OMI_LOCAL_TEST_GATEWAY_TOKEN: "local-test-gateway-token",
      OMI_LOCAL_TEST_GATEWAY_READY: readyPath,
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  const db = new Database(":memory:");
  try {
    const ready = await waitForReady(readyPath);
    const identity = await probeGatewayEngineIdentity(String(ready.url));
    expect(identity).toEqual({
      schema: "omi.local-test-gateway.v1",
      realModelProxy: false,
      model: null,
    });
    const stamp = stampForGatewayEngine(identity, "default");
    expect(stamp.tier).not.toBe("real-provider");
    expect(stamp.adapter).toBe("omi.local-test-gateway.v1");
    const source = createGatewayChatGenerationSource({
      gatewayUrl: String(ready.url),
      laneId: "omi:auto:chat-agent",
      serviceToken: "local-test-gateway-token",
      engineIdentity: identity,
    });
    expect(readChatGenerationSourceCapability(source)).toEqual(stamp);
    expect(reportForLegacyChatCapability(stamp).claimsRealAgentSuccess).toBe(false);
    expect(reportForLegacyChatCapability(stamp).tier).toBe("pure-contract");

    const service = createLocalDevService({
      db,
      ownerAccountId: "local-dev-user",
      memoryCount: 0,
      accountTimezone: "UTC",
      devSecretLabel: "chat-provenance-canned",
      generationSource: source,
    });
    const headers = {
      authorization: `Bearer ${service.devToken}`,
      "content-type": "application/json",
    };
    const admitted = await service.app.request("/v1/chat-messages", {
      method: "POST",
      headers,
      body: JSON.stringify(chatPayload("canned-provenance", "ping-canned")),
    });
    expect(admitted.status).toBe(201);
    const admission = await admitted.json() as { readonly generation: { readonly id: string } };
    const frames = parseServiceSse(await (await service.app.request(
      `/v1/chat-generations/${admission.generation.id}/events`,
      { headers: { authorization: headers.authorization } },
    )).text());
    expect(frames.at(-1)).toMatchObject({
      kind: "done",
      message: { text: CANNED_OUTPUT, generationOutcome: "completed" },
    });
    const agentFrames = parseServiceSse(await (await service.app.request(
      `/v1/chat-generations/${admission.generation.id}/agent-events`,
      { headers: { authorization: headers.authorization } },
    )).text());
    const capability = agentFrames.find((event) => event.kind === "capability_receipt") as {
      readonly details?: { readonly tier?: unknown; readonly adapter?: unknown };
    } | undefined;
    expect(capability?.details).toEqual({
      tier: "unknown",
      adapter: "omi.local-test-gateway.v1",
      deterministic: false,
    });
    expect(capability?.details?.tier).not.toBe("real-provider");
    const publicProjection = JSON.stringify({ frames, agentFrames });
    expect(publicProjection).not.toContain(REAL_PROVIDER_LABEL);
    expect(publicProjection).not.toContain("omi.local-model-gateway.v1");
  } finally {
    child.kill("SIGTERM");
    db.close();
    rmSync(scratch, { recursive: true, force: true });
  }
}, 15_000);

test("real-proxy identity is required before a real-provider stamp, and the canned string is not used", () => {
  const stamp = stampForGatewayEngine({
    schema: "omi.local-model-gateway.v1",
    realModelProxy: true,
    model: "glm-4.7",
  }, "default");
  expect(stamp).toEqual({
    tier: "real-provider",
    adapter: "omi.local-model-gateway.v1/glm-4.7",
    deterministic: false,
  });
  const report = reportForLegacyChatCapability(stamp, "passed");
  expect(report.claimsRealAgentSuccess).toBe(false);
  expect(report.providerEvidence).toBe("gateway-routed");
  expect(report.tier).toBe("local-integration");
});
