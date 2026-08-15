import { expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { createLocalDevService } from "../apps/service/app-facing";
import { createProductionGatewayToolLoop } from "../apps/service/chat/gateway-tool-composition";
import { createGatewayChatGenerationSource } from "../apps/service/chat/generation-source";
import { QA_FIXTURE_TIME_ANCHOR_UTC } from "../apps/service/qa/seed";

const here = dirname(fileURLToPath(import.meta.url));
const script = join(here, "local-model-gateway.mjs");
const stack = readFileSync(join(here, "dev-stack.sh"), "utf8");
const app = readFileSync(join(here, "dev-app.sh"), "utf8");
const source = readFileSync(script, "utf8");
const MOCK_KEY = "mock-glm-key-for-local-tests";
const GATEWAY_TOKEN = "local-model-gateway-token";
const KEY_ENV_NAMES = ["GLM_API_KEY", "ZAI_API_KEY", "OMI_BENCH_OPENAI_API_KEY"] as const;

const gatewayEnv = (overrides: Record<string, string | undefined> = {}): NodeJS.ProcessEnv => {
  const env: NodeJS.ProcessEnv = { ...process.env };
  for (const name of KEY_ENV_NAMES) delete env[name];
  for (const [name, value] of Object.entries(overrides)) {
    if (value === undefined) delete env[name];
    else env[name] = value;
  }
  return env;
};

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

const spawnGateway = (env: NodeJS.ProcessEnv) => {
  const stdout: Buffer[] = [];
  const stderr: Buffer[] = [];
  const child = spawn("bun", [script], {
    env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  child.stdout?.on("data", (chunk) => stdout.push(chunk as Buffer));
  child.stderr?.on("data", (chunk) => stderr.push(chunk as Buffer));
  return {
    child,
    text: () => `${Buffer.concat(stdout)}${Buffer.concat(stderr)}`,
  };
};

test("default stack still selects the canned local test gateway", () => {
  expect(stack).toContain('GATEWAY_LAUNCHER="$HERE/local-test-gateway.mjs"');
  expect(stack).toContain("GATEWAY_PORT=8788");
  expect(stack).toContain("never a production model, never the production API host");
  expect(stack).toContain('OMI_LLM_GATEWAY_URL="$GATEWAY_URL"');
  expect(stack).toContain('OMI_LLM_GATEWAY_SERVICE_TOKEN="$GATEWAY_TOKEN"');
  expect(stack).toMatch(/OMI_CHAT_MODEL/);
  expect(stack).toContain("local-model-gateway.mjs");
  expect(app).toContain("local test gateway");
  expect(app).toContain("not a real model");
  expect(app).toContain("reused the listeners already serving 4851 and 8788");
  expect(app).toContain('GATEWAY_URL="http://127.0.0.1:8788"');
});

test("model gateway disclosures are honest and do not reuse the test-gateway strings", () => {
  expect(source).toContain("real_model_proxy");
  expect(source).toContain("local real-model proxy");
  expect(source).not.toContain("never a production model");
  expect(source).not.toContain("production_model: false");
  expect(source).not.toContain("https://api.omi.me");
  expect(source).toContain("/v1/chat/completions");
  expect(stack).not.toContain("https://api.omi.me");
  expect(app).not.toMatch(/api\.omi\.me|\?rig=dev/);
});

test("production entrypoints do not value-import the model gateway shim", () => {
  const result = spawnSync("bun", [
    "run",
    "scripts/trace-value-imports.ts",
    "drivers/postgres/firebase-authorized-memory-service-process.ts",
    "drivers/postgres/firebase-authorized-memory-service-app.ts",
    "apps/mcp/bun-http.ts",
    "--forbid",
    "integration/local-model-gateway",
  ], {
    cwd: join(here, ".."),
    encoding: "utf8",
  });
  expect(result.status).toBe(0);
  expect(`${result.stdout}${result.stderr}`).not.toContain("FORBIDDEN");
});

test("refuses to start when no provider key env is set", async () => {
  const child = spawn("bun", [script], {
    env: gatewayEnv({
      OMI_LOCAL_MODEL_GATEWAY_PORT: "0",
      OMI_LOCAL_MODEL_GATEWAY_TOKEN: GATEWAY_TOKEN,
    }),
    stdio: ["ignore", "pipe", "pipe"],
  });
  const stderr: Buffer[] = [];
  child.stderr?.on("data", (chunk) => stderr.push(chunk as Buffer));
  const status = await new Promise<number | null>((resolve) => {
    child.on("exit", (code) => resolve(code));
  });
  const text = Buffer.concat(stderr).toString("utf8");
  expect(status).toBe(2);
  expect(text).toContain("GLM_API_KEY");
  expect(text).toContain("ZAI_API_KEY");
  expect(text).toContain("OMI_BENCH_OPENAI_API_KEY");
  expect(text).not.toContain(MOCK_KEY);
});

test("loopback model gateway authenticates, rewrites the lane, and pipes SSE including tool_calls", async () => {
  const captured: Array<{
    readonly url: string;
    readonly authorization: string | null;
    readonly body: Record<string, unknown>;
  }> = [];
  const sse = [
    `data: ${JSON.stringify({ choices: [{ delta: { tool_calls: [{ index: 0, id: "call_1", function: { name: "get_action_items", arguments: "{" } }] } }] })}\n\n`,
    `data: ${JSON.stringify({ choices: [{ delta: { tool_calls: [{ index: 0, function: { arguments: "}" } }] } }] })}\n\n`,
    "data: [DONE]\n\n",
  ].join("");
  const provider = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    async fetch(request) {
      const body = await request.json() as Record<string, unknown>;
      captured.push({
        url: request.url,
        authorization: request.headers.get("authorization"),
        body,
      });
      if (new URL(request.url).pathname !== "/chat/completions") {
        return new Response("wrong path", { status: 404 });
      }
      return new Response(sse, {
        status: 200,
        headers: { "content-type": "text/event-stream" },
      });
    },
  });
  const scratch = mkdtempSync(join(tmpdir(), "omi-local-model-gateway-"));
  const readyPath = join(scratch, "ready.json");
  const spawned = spawnGateway(gatewayEnv({
    GLM_API_KEY: MOCK_KEY,
    OMI_BENCH_OPENAI_BASE_URL: `http://127.0.0.1:${provider.port}`,
    OMI_BENCH_OPENAI_MODEL: "glm-4.7",
    OMI_LOCAL_MODEL_GATEWAY_PORT: "0",
    OMI_LOCAL_MODEL_GATEWAY_TOKEN: GATEWAY_TOKEN,
    OMI_LOCAL_MODEL_GATEWAY_READY: readyPath,
  }));
  try {
    const ready = await waitForReady(readyPath);
    expect(ready.disclosure).toBe("local real-model proxy");
    expect(ready.real_model_proxy).toBe(true);
    expect(ready.provider_host).toBe("127.0.0.1");
    expect(ready.production_model).toBeUndefined();
    expect(String(ready.url)).toMatch(/^http:\/\/127\.0\.0\.1:\d+$/);
    const denied = await fetch(`${ready.url}/v1/chat/completions`, { method: "POST" });
    expect(denied.status).toBe(401);
    const wrongLane = await fetch(`${ready.url}/v1/chat/completions`, {
      method: "POST",
      headers: {
        authorization: `Bearer ${GATEWAY_TOKEN}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model: "glm-4.7",
        messages: [{ role: "user", content: "hi" }],
        stream: true,
      }),
    });
    expect(wrongLane.status).toBe(400);
    const tools = [{ type: "function", function: { name: "get_action_items" } }];
    const allowed = await fetch(`${ready.url}/v1/chat/completions`, {
      method: "POST",
      headers: {
        authorization: `Bearer ${GATEWAY_TOKEN}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model: "omi:auto:chat-agent",
        messages: [{ role: "user", content: "hi" }],
        tools,
        tool_choice: "auto",
        stream: true,
        stream_options: { include_usage: true },
      }),
    });
    expect(allowed.status).toBe(200);
    const body = await allowed.text();
    expect(body).toBe(sse);
    expect(body).toContain("data: [DONE]");
    expect(body).toContain("tool_calls");
    expect(captured).toHaveLength(1);
    expect(captured[0]?.url).toBe(`http://127.0.0.1:${provider.port}/chat/completions`);
    expect(captured[0]?.authorization).toBe(`Bearer ${MOCK_KEY}`);
    expect(captured[0]?.body.model).toBe("glm-4.7");
    expect(captured[0]?.body.messages).toEqual([{ role: "user", content: "hi" }]);
    expect(captured[0]?.body.tools).toEqual(tools);
    expect(captured[0]?.body.tool_choice).toBe("auto");
    expect(captured[0]?.body.stream).toBe(true);
    expect(captured[0]?.body.stream_options).toEqual({ include_usage: true });
    const logs = spawned.text();
    expect(logs).not.toContain(MOCK_KEY);
    expect(logs).not.toContain(GATEWAY_TOKEN);
  } finally {
    spawned.child.kill("SIGTERM");
    provider.stop(true);
    rmSync(scratch, { recursive: true, force: true });
  }
});

test("provider 4xx/5xx are surfaced as errors, not fake streams", async () => {
  const provider = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    fetch() {
      return new Response("upstream-no", {
        status: 503,
        headers: { "content-type": "text/plain" },
      });
    },
  });
  const scratch = mkdtempSync(join(tmpdir(), "omi-local-model-gateway-err-"));
  const readyPath = join(scratch, "ready.json");
  const spawned = spawnGateway(gatewayEnv({
    ZAI_API_KEY: MOCK_KEY,
    OMI_BENCH_OPENAI_BASE_URL: `http://127.0.0.1:${provider.port}`,
    OMI_LOCAL_MODEL_GATEWAY_PORT: "0",
    OMI_LOCAL_MODEL_GATEWAY_TOKEN: GATEWAY_TOKEN,
    OMI_LOCAL_MODEL_GATEWAY_READY: readyPath,
  }));
  try {
    const ready = await waitForReady(readyPath);
    const response = await fetch(`${ready.url}/v1/chat/completions`, {
      method: "POST",
      headers: {
        authorization: `Bearer ${GATEWAY_TOKEN}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model: "omi:auto:chat-agent",
        messages: [{ role: "user", content: "hi" }],
        stream: true,
      }),
    });
    expect(response.status).toBe(503);
    expect(await response.text()).toBe("upstream-no");
    expect(response.headers.get("content-type")).toContain("text/plain");
    expect(spawned.text()).not.toContain(MOCK_KEY);
  } finally {
    spawned.child.kill("SIGTERM");
    provider.stop(true);
    rmSync(scratch, { recursive: true, force: true });
  }
});

const sseBody = (...events: readonly string[]): string => events
  .map((event) => `data: ${event}\n\n`)
  .join("");

const contentSse = (text: string): string => sseBody(
  JSON.stringify({ choices: [{ delta: { content: text } }] }),
  JSON.stringify({
    choices: [{ delta: {} }],
    usage: { prompt_tokens: 8, completion_tokens: 2, total_tokens: 10 },
  }),
  "[DONE]",
);

const toolCallSse = (): string => sseBody(
  JSON.stringify({
    choices: [{
      delta: {
        tool_calls: [{
          index: 0,
          id: "call_get_action_items",
          function: { name: "get_action_items", arguments: "{}" },
        }],
      },
    }],
  }),
  "[DONE]",
);

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

test("real service accepts a streamed completion and a tool-call round trip through the shim", async () => {
  const provider = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    async fetch(request) {
      const body = await request.json() as {
        readonly messages?: readonly Record<string, unknown>[];
        readonly tool_choice?: unknown;
        readonly model?: unknown;
      };
      expect(body.model).toBe("glm-4.7");
      const encoded = JSON.stringify(body.messages ?? []);
      if (encoded.includes('"role":"tool"') || body.tool_choice === "none") {
        return new Response(contentSse("Tool round complete."), {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        });
      }
      if (encoded.includes("ping-tools")) {
        return new Response(toolCallSse(), {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        });
      }
      return new Response(contentSse("Shim streamed completion."), {
        status: 200,
        headers: { "content-type": "text/event-stream" },
      });
    },
  });
  const scratch = mkdtempSync(join(tmpdir(), "omi-local-model-gateway-svc-"));
  const readyPath = join(scratch, "ready.json");
  const spawned = spawnGateway(gatewayEnv({
    GLM_API_KEY: MOCK_KEY,
    OMI_BENCH_OPENAI_BASE_URL: `http://127.0.0.1:${provider.port}`,
    OMI_BENCH_OPENAI_MODEL: "glm-4.7",
    OMI_LOCAL_MODEL_GATEWAY_PORT: "0",
    OMI_LOCAL_MODEL_GATEWAY_TOKEN: GATEWAY_TOKEN,
    OMI_LOCAL_MODEL_GATEWAY_READY: readyPath,
  }));
  const db = new Database(":memory:");
  try {
    const ready = await waitForReady(readyPath);
    let serviceForGatewayTools: ReturnType<typeof createLocalDevService> | null = null;
    const generationSource = createGatewayChatGenerationSource({
      gatewayUrl: String(ready.url),
      laneId: "omi:auto:chat-agent",
      serviceToken: GATEWAY_TOKEN,
      readOnlyToolLoopForInput: (input) => {
        const service = serviceForGatewayTools;
        if (service === null) return undefined;
        const ownerAccountId = service.seedIdentity().owner_account_id;
        if (typeof ownerAccountId !== "string" || ownerAccountId !== input.context.ownerAccountId) {
          throw new Error("gateway tool owner mismatch");
        }
        return createProductionGatewayToolLoop({
          fetch: (request) => service.app.fetch(request),
          bearerToken: service.devToken,
          nowEpochMilliseconds: () => Date.parse(QA_FIXTURE_TIME_ANCHOR_UTC),
          agentRunEvents: service.writePath.agentRunEvents,
          approvalCoordinator: service.writePath.agentApprovalCoordinator,
        });
      },
    });
    const service = createLocalDevService({
      db,
      ownerAccountId: "local-dev-user",
      memoryCount: 0,
      accountTimezone: "UTC",
      devSecretLabel: "local-model-gateway-e2e",
      generationSource,
    });
    serviceForGatewayTools = service;
    const headers = {
      authorization: `Bearer ${service.devToken}`,
      "content-type": "application/json",
    };
    const complete = await service.app.request("/v1/chat-messages", {
      method: "POST",
      headers,
      body: JSON.stringify(chatPayload("shim-complete", "ping-complete")),
    });
    expect(complete.status).toBe(201);
    const completeAdmission = await complete.json() as { readonly generation: { readonly id: string } };
    const completeEvents = parseServiceSse(await (await service.app.request(
      `/v1/chat-generations/${completeAdmission.generation.id}/events`,
      { headers: { authorization: headers.authorization } },
    )).text());
    expect(completeEvents.at(-1)).toMatchObject({
      kind: "done",
      message: { text: "Shim streamed completion.", generationOutcome: "completed" },
    });

    const tools = await service.app.request("/v1/chat-messages", {
      method: "POST",
      headers,
      body: JSON.stringify(chatPayload("shim-tools", "ping-tools")),
    });
    expect(tools.status).toBe(201);
    const toolsAdmission = await tools.json() as { readonly generation: { readonly id: string } };
    const toolEvents = parseServiceSse(await (await service.app.request(
      `/v1/chat-generations/${toolsAdmission.generation.id}/events`,
      { headers: { authorization: headers.authorization } },
    )).text());
    expect(toolEvents.at(-1)).toMatchObject({
      kind: "done",
      message: { text: "Tool round complete.", generationOutcome: "completed" },
    });
    expect(spawned.text()).not.toContain(MOCK_KEY);
  } finally {
    spawned.child.kill("SIGTERM");
    provider.stop(true);
    db.close();
    rmSync(scratch, { recursive: true, force: true });
  }
}, 15_000);
