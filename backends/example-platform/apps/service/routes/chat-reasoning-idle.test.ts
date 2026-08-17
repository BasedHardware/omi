import { afterEach, describe, expect, test } from "bun:test";
import { Database } from "bun:sqlite";

import {
  createInMemoryLocalServiceStores,
  createLocalDevService,
} from "../app-facing";
import { REAL_MODEL_GENERATION_LIVENESS } from "../chat/real-model-liveness";
import { createGatewayChatGenerationSource } from "../chat/generation-source";
import { LOOPBACK_IDLE_TIMEOUT_SECONDS } from "../net/loopback";
import { CHAT_GENERATION_SSE_HEARTBEAT_INTERVAL_MS } from "./chat-messages";

/**
 * Incident replay. Bun's default `idleTimeout` is 10s. glm-4.7 reasoned for
 * 10.7s with no content frames, so the service→client socket went idle and
 * Bun reaped it (`[Bun.serve]: request timed out after 10 seconds`). The
 * generation then finished upstream into a connection nobody was holding.
 *
 * This stub emits reasoning frames for 15s and then content. Bun's message
 * says 10 seconds; the reap is observed around 12s, so 15s is past the
 * ceiling with margin. The service drops reasoning frames (they are not in
 * the ratified generation grammar), so the client socket is genuinely idle
 * unless SSE comment heartbeats fire. The test omits `idleTimeout` so a
 * bigger number cannot fake the pass.
 *
 * red-proof: DEFAULT stream heartbeat 0, and the client never sees
 * `event: done`. ChatProduction then falls through to
 * `chat.responseUnavailable` because the dropped socket carries no code.
 */
const REASONING_PREAMBLE_MS = 15_000;
const GATEWAY_TOKEN = "reasoning-idle-gateway-token";
const ACCOUNT = "reasoning-idle-account";

const openServers: Array<ReturnType<typeof Bun.serve>> = [];

afterEach(() => {
  for (const server of openServers.splice(0)) server.stop(true);
});

const sseRecord = (delta: Record<string, unknown>): Uint8Array =>
  new TextEncoder().encode(`data: ${JSON.stringify({ choices: [{ delta }] })}\n\n`);

const readSseUntilTerminal = async (
  response: Response,
  timeoutMs: number,
): Promise<string> => {
  if (response.body === null) return "";
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let text = "";
  const deadline = Date.now() + timeoutMs;
  try {
    while (Date.now() < deadline) {
      const remaining = Math.max(1, deadline - Date.now());
      const chunk = await Promise.race([
        reader.read(),
        Bun.sleep(remaining).then(() => ({ done: true as const, value: undefined })),
      ]);
      if (chunk.value !== undefined) text += decoder.decode(chunk.value, { stream: true });
      if (/\nevent: (?:done|failed|cancelled)\n[\s\S]*?\n\n/.test(`\n${text}`)) break;
      if (chunk.done) break;
    }
  } catch {
    // Bun idleTimeout aborts the request; the body errors instead of
    // delivering a terminal frame. That is the defect under test.
  }
  try {
    await reader.cancel();
  } catch {
    // already closed
  }
  return text;
};

describe("reasoning preamble vs Bun idleTimeout", () => {
  test("SSE comment heartbeats outrun Bun's default idleTimeout and the loopback ceiling", () => {
    // red-proof: heartbeat 0, or ≥ 10_000, fails the 15s preamble test below
    // because the default 10s socket dies first. A 30s idleTimeout with
    // heartbeat 0 would pass that test by raising the number — this
    // inequality is what makes the bigger number insufficient on its own.
    expect(CHAT_GENERATION_SSE_HEARTBEAT_INTERVAL_MS).toBeGreaterThan(0);
    expect(CHAT_GENERATION_SSE_HEARTBEAT_INTERVAL_MS).toBeLessThan(10_000);
    expect(LOOPBACK_IDLE_TIMEOUT_SECONDS).toBeGreaterThan(10);
    expect(LOOPBACK_IDLE_TIMEOUT_SECONDS * 1_000)
      .toBeGreaterThan(CHAT_GENERATION_SSE_HEARTBEAT_INTERVAL_MS);
  });

  test("a stub that reasons longer than the socket ceiling still delivers content", async () => {
    const gateway = Bun.serve({
      hostname: "127.0.0.1",
      port: 0,
      fetch() {
        return new Response(new ReadableStream<Uint8Array>({
          async start(controller) {
            const started = Date.now();
            while (Date.now() - started < REASONING_PREAMBLE_MS) {
              controller.enqueue(sseRecord({ reasoning_content: "thinking" }));
              await Bun.sleep(200);
            }
            controller.enqueue(sseRecord({ content: "Harborline is open." }));
            controller.enqueue(new TextEncoder().encode("data: [DONE]\n\n"));
            controller.close();
          },
        }), {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        });
      },
    });
    openServers.push(gateway);

    const db = new Database(":memory:");
    const local = createLocalDevService({
      db,
      stores: createInMemoryLocalServiceStores(),
      ownerAccountId: ACCOUNT,
      memoryCount: 0,
      accountTimezone: "UTC",
      devSecretLabel: "reasoning-idle-proof",
      generationLiveness: REAL_MODEL_GENERATION_LIVENESS,
      generationSource: createGatewayChatGenerationSource({
        gatewayUrl: `http://127.0.0.1:${gateway.port}`,
        laneId: "omi:auto:chat-agent",
        serviceToken: GATEWAY_TOKEN,
        retrySleep: async () => undefined,
      }),
    });
    const service = Bun.serve({
      hostname: "127.0.0.1",
      port: 0,
      fetch: local.app.fetch,
      websocket: local.websocket,
    });
    openServers.push(service);

    const admissionResponse = await fetch(`http://127.0.0.1:${service.port}/v1/chat-messages`, {
      method: "POST",
      headers: {
        authorization: `Bearer ${local.devToken}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        op: "create",
        opId: "op-reasoning-idle",
        id: "msg-reasoning-idle",
        at: 1_786_352_400_000,
        text: "Is Harborline open?",
        sender: "human",
        journalRevision: 1,
        type: "text",
        appId: null,
        chatSessionId: null,
        messageSource: "desktop_chat",
        metadata: null,
        attachmentIds: [],
      }),
    });
    expect(admissionResponse.status).toBe(201);
    const admission = await admissionResponse.json() as { generation: { id: string } };

    const eventsResponse = await fetch(
      `http://127.0.0.1:${service.port}/v1/chat-generations/${admission.generation.id}/events`,
      { headers: { authorization: `Bearer ${local.devToken}` } },
    );
    const body = await readSseUntilTerminal(eventsResponse, REASONING_PREAMBLE_MS + 4_000);
    db.close();

    expect(body).toContain(": heartbeat");
    expect(body).toContain("event: done");
    expect(body).toContain("Harborline is open.");
    expect(body).not.toContain("generation_timeout");
  }, 30_000);
});
