// domain-pending(DIV-CHAT-REV-001)
// domain-pending(DIV-CHAT-HASH-001)
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test } from "bun:test";

import { acquireAppFacingTestLease, writeAppFacingTestLeaseFile } from "../net/test-allocation";
import type { QaProducerEvidenceDocument } from "../observability/producer-evidence";

const RUN = "run-dev-server-subprocess-proof";

interface Readiness {
  readonly schema: string;
  readonly runId: string;
  readonly executable: string;
  readonly baseUrl: string;
  readonly databasePath: string;
  readonly pid: number;
  readonly evidencePath: string;
  readonly devToken: string;
  readonly ownerAccountId: string;
}

const waitUntil = async (condition: () => boolean | Promise<boolean>, timeoutMs = 5_000): Promise<void> => {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await condition()) return;
    await Bun.sleep(20);
  }
  throw new Error("condition timeout");
};

const spawnService = async (
  databasePath: string,
  readinessPath: string,
  extraEnv: Record<string, string> = {},
): Promise<{
  readonly child: Bun.Subprocess;
  readonly readiness: Readiness;
  readonly baseUrl: string;
  readonly port: number;
  readonly releaseLease: () => void;
}> => {
  const leaseDir = mkdtempSync(join(tmpdir(), "omi-dev-server-lease-"));
  const lease = acquireAppFacingTestLease({ runId: RUN });
  const leasePath = join(leaseDir, "app-facing-test-lease.json");
  writeAppFacingTestLeaseFile(leasePath, lease);
  const port = lease.port;
  const baseUrl = `http://127.0.0.1:${port}`;
  const child = Bun.spawn([
    process.execPath,
    "apps/service/bin/dev-server.ts",
    "--app-facing-test-lease",
    leasePath,
  ], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      OMI_PORT: String(port),
      OMI_QA_DB: databasePath,
      OMI_RUN_ID: RUN,
      OMI_DEV_READY_RECORD: readinessPath,
      TZ: "UTC",
      OMI_STT_ENGINE: "",
      OMI_STT_MODEL: "",
      OMI_STT_VENV: "",
      ...extraEnv,
    },
    stdout: "ignore",
    stderr: "pipe",
  });
  try {
    await waitUntil(async () => {
      if (!existsSync(readinessPath)) return false;
      try {
        return (await fetch(`${baseUrl}/ready`)).status === 200;
      } catch {
        return false;
      }
    });
  } catch (error) {
    const stderr = await new Response(child.stderr).text();
    child.kill("SIGTERM");
    lease.release();
    rmSync(leaseDir, { recursive: true, force: true });
    throw new Error(`${String(error)}; dev-server stderr: ${stderr}`);
  }
  return {
    child,
    readiness: JSON.parse(readFileSync(readinessPath, "utf8")) as Readiness,
    baseUrl,
    port,
    releaseLease: () => {
      lease.release();
      rmSync(leaseDir, { recursive: true, force: true });
    },
  };
};

const stopService = async (child: Bun.Subprocess): Promise<void> => {
  child.kill("SIGTERM");
  await child.exited;
};

const authorizedHeaders = (
  token: string,
  shell: "macos" | "ios",
): Record<string, string> => ({
  authorization: `Bearer ${token}`,
  "content-type": "application/json",
  "x-omi-client-id": `${RUN}::${shell}`,
});

const postJson = (
  baseUrl: string,
  path: string,
  token: string,
  body: unknown,
  shell: "macos" | "ios" = "macos",
): Promise<Response> => fetch(`${baseUrl}${path}`, {
  method: "POST",
  headers: authorizedHeaders(token, shell),
  body: JSON.stringify(body),
});

const cutOverTasks = async (baseUrl: string, token: string): Promise<void> => {
  for (const body of [
    {
      control_revision: 1,
      account_generation: "legacy",
      account_epoch: null,
      lifecycle_state: "active",
      deletion_epoch: null,
    },
    {
      control_revision: 2,
      account_generation: "migrating",
      account_epoch: null,
      lifecycle_state: "active",
      deletion_epoch: null,
    },
    {
      control_revision: 3,
      account_generation: "new",
      account_epoch: 7,
      lifecycle_state: "active",
      deletion_epoch: null,
    },
  ]) {
    expect((await postJson(baseUrl, "/v1/qa/control/observe", token, body)).status).toBe(200);
  }
  expect((await postJson(baseUrl, "/v1/qa/control/activate", token, {
    epoch: 7,
    at_control_revision: 3,
  })).status).toBe(200);
};

const chatPayload = (shell: "macos" | "ios", id = `subprocess-chat-${shell}`) => ({
  op: "create",
  opId: `op-subprocess-${shell}`,
  id,
  at: shell === "macos" ? 1_786_352_400_000 : 1_786_352_400_001,
  text: `synthetic ${shell}`,
  sender: "human",
  journalRevision: 1,
  type: "text",
  appId: null,
  chatSessionId: null,
  messageSource: "desktop_chat",
  metadata: null,
  attachmentIds: [],
});

const parseSseBlocks = (text: string): readonly Record<string, unknown>[] =>
  Object.freeze(text.split("\n\n")
    .filter((block) => block.trim().length > 0)
    .map((block) => JSON.parse(block.split("\n")
      .find((line) => line.startsWith("data: "))!.slice(6)) as Record<string, unknown>));

const fetchGenerationEvents = (
  baseUrl: string,
  token: string,
  generationId: string,
  shell: "macos" | "ios" = "macos",
): Promise<Response> => fetch(`${baseUrl}/v1/chat-generations/${generationId}/events`, {
  headers: authorizedHeaders(token, shell),
});

const fetchAgentEvents = (
  baseUrl: string,
  token: string,
  generationId: string,
  shell: "macos" | "ios" = "macos",
): Promise<Response> => fetch(`${baseUrl}/v1/chat-generations/${generationId}/agent-events`, {
  headers: authorizedHeaders(token, shell),
});

const listen = async (baseUrl: string, token: string, shell: "macos" | "ios"): Promise<void> => {
  const session = shell === "macos"
    ? "a661b15a-2401-4f5c-a4c4-23643dcf26d1"
    : "8f95c2d8-f398-4d72-94d3-580cffc96ef7";
  const socket = new WebSocket(
    `${baseUrl.replace("http://", "ws://")}/v4/listen?client_conversation_id=${session}`,
    { headers: authorizedHeaders(token, shell) },
  );
  let ready = false;
  socket.addEventListener("message", (event) => {
    const value = JSON.parse(String(event.data)) as { readonly status?: unknown };
    if (value.status === "ready") ready = true;
  });
  await new Promise<void>((resolve, reject) => {
    socket.addEventListener("open", () => resolve(), { once: true });
    socket.addEventListener("error", () => reject(new Error("listen socket failed")), {
      once: true,
    });
  });
  await waitUntil(() => ready);
  socket.send(new Uint8Array([1, 2, 3, 4]));
  await Bun.sleep(20);
  socket.close(1000, "done");
};

const exerciseShell = async (baseUrl: string, token: string, shell: "macos" | "ios"): Promise<void> => {
  for (const path of [
    "/v1/memories",
    "/v1/tasks",
    "/v1/conversations",
    "/v1/folders",
    "/v1/settings",
    "/v1/screen/days",
  ]) {
    expect((await fetch(`${baseUrl}${path}`, {
      headers: authorizedHeaders(token, shell),
    })).status).toBe(200);
  }
  expect((await postJson(baseUrl, "/v1/chat-messages", token, chatPayload(shell), shell)).status).toBe(201);
  await listen(baseUrl, token, shell);
};

test("real dev-server owns one durable SQLite service for all eight domains", async () => {
  const directory = mkdtempSync(join(tmpdir(), "omi-dev-server-proof-"));
  const databasePath = join(directory, "qa.sqlite");
  const readinessPath = join(directory, "readiness.json");
  let child: Bun.Subprocess | null = null;
  let releaseLease: (() => void) | null = null;
  try {
    const first = await spawnService(databasePath, readinessPath);
    child = first.child;
    releaseLease = first.releaseLease;
    expect(first.readiness).toMatchObject({
      schema: "omi.dev-service-readiness.v1",
      runId: RUN,
      executable: "apps/service/bin/dev-server.ts",
      baseUrl: first.baseUrl,
      databasePath,
      evidencePath: "/v1/qa/evidence",
      ownerAccountId: "local-dev-user",
    });
    expect(first.readiness.pid).toBe(first.child.pid);
    await cutOverTasks(first.baseUrl, first.readiness.devToken);
    await exerciseShell(first.baseUrl, first.readiness.devToken, "macos");
    await exerciseShell(first.baseUrl, first.readiness.devToken, "ios");

    const createdFolder = await postJson(first.baseUrl, "/v1/folders", first.readiness.devToken, {
      name: "Persisted across restart",
    });
    expect(createdFolder.status).toBe(201);
    expect(await createdFolder.json()).toEqual({ id: "qa-folder-created-001" });

    const producer = await fetch(`${first.baseUrl}/v1/qa/evidence?run=${RUN}`, {
      headers: { authorization: `Bearer ${first.readiness.devToken}` },
    });
    expect(producer.status).toBe(200);
    const document = await producer.json() as QaProducerEvidenceDocument;
    expect(document.rows).toHaveLength(16);
    for (const evidenceRow of document.rows) {
      if (evidenceRow.domain === "listen") {
        expect(evidenceRow.listen?.protocolReady).toBeGreaterThan(0);
        expect(evidenceRow.listen?.acceptedBinary).toBeGreaterThan(0);
        expect(evidenceRow.listen?.acceptedBinaryBytes).toBeGreaterThanOrEqual(4);
      } else {
        expect(evidenceRow.http?.successful).toBeGreaterThan(0);
      }
      if (evidenceRow.domain === "chat") {
        expect(evidenceRow.chat?.acceptedAdmission).toBe(1);
      }
    }

    await stopService(child);
    child = null;
    releaseLease();
    releaseLease = null;
    rmSync(readinessPath);

    const second = await spawnService(databasePath, readinessPath);
    child = second.child;
    releaseLease = second.releaseLease;
    const folders = await fetch(`${second.baseUrl}/v1/folders`, {
      headers: authorizedHeaders(second.readiness.devToken, "macos"),
    });
    expect((await folders.json() as readonly { readonly id: string }[])
      .some((folder) => folder.id === "qa-folder-created-001")).toBeTrue();
    const history = await fetch(`${second.baseUrl}/v1/chat-messages`, {
      headers: authorizedHeaders(second.readiness.devToken, "macos"),
    });
    const messages = (await history.json() as {
      readonly messages: readonly { readonly id: string }[];
    }).messages;
    expect(messages.map((message) => message.id)).toContain("subprocess-chat-macos");
    expect(messages.map((message) => message.id)).toContain("subprocess-chat-ios");

    expect((await fetch(`${second.baseUrl}/v1/qa/reset`, {
      method: "POST",
      headers: { authorization: `Bearer ${second.readiness.devToken}` },
    })).status).toBe(200);
    const resetFolders = await fetch(`${second.baseUrl}/v1/folders`, {
      headers: authorizedHeaders(second.readiness.devToken, "macos"),
    });
    expect((await resetFolders.json() as readonly { readonly id: string }[])
      .some((folder) => folder.id === "qa-folder-created-001")).toBeFalse();
    const resetHistory = await fetch(`${second.baseUrl}/v1/chat-messages`, {
      headers: authorizedHeaders(second.readiness.devToken, "macos"),
    });
    expect((await resetHistory.json() as { readonly messages: readonly unknown[] }).messages)
      .toEqual([]);
  } finally {
    if (child !== null) await stopService(child);
    releaseLease?.();
    rmSync(directory, { recursive: true, force: true });
  }
}, 20_000);

test("dev-server entrypoint completes a gateway-backed chat turn with default memory context", async () => {
  const directory = mkdtempSync(join(tmpdir(), "omi-dev-server-gateway-proof-"));
  const databasePath = join(directory, "qa.sqlite");
  const readinessPath = join(directory, "readiness.json");
  const gatewayToken = "subprocess-loopback-gateway-token";
  const gateway = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    async fetch(request) {
      const url = new URL(request.url);
      if (request.method === "GET" && (url.pathname === "/ready" || url.pathname === "/")) {
        return Response.json({
          schema: "omi.local-test-gateway.v1",
          disclosure: "local test gateway",
          production_model: false,
        });
      }
      const body = await request.json() as Record<string, unknown>;
      const messagesJson = JSON.stringify(body.messages);
      if (!messagesJson.includes("memory_projection")) {
        return new Response("missing memory context", { status: 500 });
      }
      return new Response([
        `data: ${JSON.stringify({ choices: [{ delta: { content: "Subprocess gateway " } }] })}\n\n`,
        `data: ${JSON.stringify({
          choices: [{ delta: { content: "answer." } }],
          usage: { prompt_tokens: 7, completion_tokens: 2, total_tokens: 9 },
        })}\n\n`,
        "data: [DONE]\n\n",
      ].join(""), {
        status: 200,
        headers: { "content-type": "text/event-stream" },
      });
    },
  });
  let child: Bun.Subprocess | null = null;
  let releaseLease: (() => void) | null = null;
  try {
    const spawned = await spawnService(databasePath, readinessPath, {
      OMI_LLM_GATEWAY_URL: `http://127.0.0.1:${gateway.port}`,
      OMI_LLM_GATEWAY_SERVICE_TOKEN: gatewayToken,
    });
    child = spawned.child;
    releaseLease = spawned.releaseLease;
    const token = spawned.readiness.devToken;
    const admitted = await postJson(
      spawned.baseUrl,
      "/v1/chat-messages",
      token,
      chatPayload("macos", "subprocess-gateway-chat"),
      "macos",
    );
    expect(admitted.status).toBe(201);
    const admission = await admitted.json() as {
      readonly generation: { readonly id: string };
    };
    const generationId = admission.generation.id;
    const canonicalBody = await (await fetchGenerationEvents(spawned.baseUrl, token, generationId)).text();
    const canonicalFrames = parseSseBlocks(canonicalBody);
    expect(canonicalFrames.filter((frame) => frame.kind === "done")).toHaveLength(1);
    expect(canonicalFrames.at(-1)).toMatchObject({
      kind: "done",
      message: { text: "Subprocess gateway answer.", generationOutcome: "completed" },
    });

    const agentBody = await (await fetchAgentEvents(spawned.baseUrl, token, generationId)).text();
    const agentEvents = parseSseBlocks(agentBody);
    expect(agentEvents.every((event) => event.runId === generationId)).toBe(true);
    expect(agentEvents).toContainEqual(expect.objectContaining({
      kind: "capability_receipt",
      details: expect.objectContaining({
        adapter: "omi.local-test-gateway.v1",
        tier: "unknown",
      }),
    }));
    const contextReceipt = agentEvents.find((event) => event.kind === "context_receipt");
    expect((contextReceipt?.details as { readonly tokenEstimate?: number }).tokenEstimate)
      .toBeGreaterThan(0);
    expect(contextReceipt).toMatchObject({
      kind: "context_receipt",
      details: expect.objectContaining({
        sourceKind: "context-packet",
        redactedPreview: "structured context packet",
      }),
    });

    const publicProjection = [canonicalBody, agentBody].join("\n");
    expect(publicProjection).not.toContain(gatewayToken);
    expect(publicProjection).not.toContain("mem1_");
    expect(publicProjection).not.toContain("cit1_");
  } finally {
    if (child !== null) await stopService(child);
    releaseLease?.();
    gateway.stop(true);
    rmSync(directory, { recursive: true, force: true });
  }
}, 20_000);
