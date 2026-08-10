// domain-pending(DIV-CHAT-REV-001)
// domain-pending(DIV-CHAT-HASH-001)
import { Database } from "bun:sqlite";
import { afterEach, describe, expect, test } from "bun:test";

import { createLocalDevService, type LocalService } from "../app-facing";
import type {
  QaEvidenceDomain,
  QaEvidenceShell,
  QaProducerEvidenceDocument,
  QaProducerEvidenceRow,
} from "../observability/producer-evidence";

const OWNER = "producer-evidence-owner";
const RUN = "run-producer-evidence-01";
const SECOND_RUN = "run-producer-evidence-02";
const openServers: Array<ReturnType<typeof Bun.serve>> = [];

afterEach(() => {
  for (const server of openServers.splice(0)) server.stop(true);
});

const boot = (): LocalService => createLocalDevService({
  db: new Database(":memory:"),
  ownerAccountId: OWNER,
  memoryCount: 2,
  accountTimezone: "UTC",
  devSecretLabel: "producer-evidence-proof",
  listenDefaultUnmetered: true,
  chatSupervisor: Object.freeze({
    onAdmitted: (): void => {},
    cancel: (): void => {},
    recoverInterrupted: (): void => {},
  }),
});

const headers = (
  service: LocalService,
  shell: QaEvidenceShell,
  runId = RUN,
): Record<string, string> => ({
  authorization: `Bearer ${service.devToken}`,
  "content-type": "application/json",
  "x-omi-client-id": `${runId}::${shell}`,
});

const evidence = async (
  service: LocalService,
  runId = RUN,
): Promise<QaProducerEvidenceDocument> => {
  const response = await service.app.request(`/v1/qa/evidence?run=${encodeURIComponent(runId)}`, {
    headers: { authorization: `Bearer ${service.devToken}` },
  });
  expect(response.status).toBe(200);
  return await response.json() as QaProducerEvidenceDocument;
};

const row = (
  document: QaProducerEvidenceDocument,
  shell: QaEvidenceShell,
  domain: QaEvidenceDomain,
): QaProducerEvidenceRow => document.rows.find((candidate) =>
  candidate.shell === shell && candidate.domain === domain)!;

const chatPayload = (id: string): Readonly<Record<string, unknown>> => Object.freeze({
  op: "create",
  opId: `op-${id}`,
  id,
  at: 1_786_352_400_000,
  text: "synthetic chat evidence",
  sender: "human",
  journalRevision: 1,
  type: "text",
  appId: null,
  chatSessionId: null,
  messageSource: "desktop_chat",
  metadata: null,
  attachmentIds: [],
});

const waitUntil = async (condition: () => boolean, timeoutMs = 2_000): Promise<void> => {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (condition()) return;
    await Bun.sleep(5);
  }
  throw new Error("condition timeout");
};

describe("GET /v1/qa/evidence", () => {
  test("joins exact run, shell and route-owned domains only after successful responses", async () => {
    const service = boot();
    for (const [path, domain] of [
      ["/v1/memories", "memories"],
      ["/v1/conversations", "conversations"],
      ["/v1/folders", "folders"],
      ["/v1/settings", "settings"],
    ] as const) {
      expect((await service.app.request(path, { headers: headers(service, "macos") })).status)
        .toBe(200);
      expect(row(await evidence(service), "macos", domain).http?.successful).toBe(1);
    }

    for (const observation of [
      { control_revision: 1, account_generation: "legacy", account_epoch: null },
      { control_revision: 2, account_generation: "migrating", account_epoch: null },
      { control_revision: 3, account_generation: "new", account_epoch: 7 },
    ] as const) {
      expect(service.writePath.control.observe({
        account_id: OWNER,
        lifecycle_state: "active",
        deletion_epoch: null,
        ...observation,
      }).accepted).toBeTrue();
    }
    expect(service.writePath.control.activate(OWNER, {
      epoch: 7,
      at_control_revision: 3,
    }).activated).toBeTrue();
    expect((await service.app.request("/v1/tasks", { headers: headers(service, "macos") })).status)
      .toBe(200);

    expect((await service.app.request("/v1/memories", {
      headers: headers(service, "ios"),
    })).status).toBe(200);
    expect((await service.app.request("/v1/memories", {
      headers: { authorization: `Bearer ${service.devToken}` },
    })).status).toBe(200);
    expect((await service.app.request("/v1/memories?limit=0", {
      headers: headers(service, "macos"),
    })).status).toBe(400);
    expect((await service.app.request("/v1/memories", {
      headers: { ...headers(service, "macos"), "x-omi-client-id": `${RUN}::windows` },
    })).status).toBe(200);
    expect((await service.app.request("/v1/memories", {
      headers: {
        authorization: `Bearer ${service.devToken}`,
        "x-omi-run-id": RUN,
        "x-omi-client-id": "ios",
      },
    })).status).toBe(200);
    expect((await service.app.request("/v1/memories", {
      headers: {
        authorization: `Bearer ${service.devToken}`,
        "x-omi-client-id": `${RUN}::macos,${SECOND_RUN}::macos`,
      },
    })).status).toBe(200);

    const document = await evidence(service);
    expect(document.schema).toBe("omi.producer-evidence.v1");
    expect(document.runId).toBe(RUN);
    expect(document.rows).toHaveLength(14);
    expect(new Set(document.rows.map((candidate) =>
      `${candidate.runId}/${candidate.shell}/${candidate.domain}`)).size).toBe(14);
    expect(row(document, "macos", "tasks").http?.successful).toBe(1);
    expect(row(document, "macos", "memories").http?.successful).toBe(1);
    expect(row(document, "ios", "memories").http?.successful).toBe(2);
    expect(row(await evidence(service, SECOND_RUN), "macos", "memories").http?.successful)
      .toBe(0);
  });

  test("bounds retained run cardinality without an overflow join bucket", async () => {
    const service = boot();
    for (let index = 0; index < 33; index += 1) {
      expect((await service.app.request("/v1/memories", {
        headers: headers(service, "macos", `bounded-run-${index}`),
      })).status).toBe(200);
    }
    expect(row(await evidence(service, "bounded-run-0"), "macos", "memories").http?.successful)
      .toBe(1);
    expect(row(await evidence(service, "bounded-run-32"), "macos", "memories").http?.successful)
      .toBe(0);
  });

  test("rejects absent, duplicate, malformed and reserved lookup keys", async () => {
    const service = boot();
    const auth = { authorization: `Bearer ${service.devToken}` };
    for (const path of [
      "/v1/qa/evidence",
      "/v1/qa/evidence?run=a&run=b",
      "/v1/qa/evidence?run=__unattributed__",
      "/v1/qa/evidence?run=has%20space",
      `/v1/qa/evidence?run=${RUN}&domain=memories`,
    ]) {
      expect((await service.app.request(path, { headers: auth })).status).toBe(400);
    }
    expect((await service.app.request(`/v1/qa/evidence?run=${RUN}`)).status).toBe(401);
  });

  test("Chat dispatch/replay and Listen ready/binary arbiters remain distinct", async () => {
    const service = boot();
    const rejected = await service.app.request("/v1/chat-messages", {
      method: "POST",
      headers: headers(service, "macos"),
      body: JSON.stringify({}),
    });
    expect(rejected.status).toBe(422);
    expect(row(await evidence(service), "macos", "chat")).toMatchObject({
      http: { successful: 0 },
      chat: { acceptedAdmission: 0 },
    });

    const payload = chatPayload("evidence-chat-01");
    const first = await service.app.request("/v1/chat-messages", {
      method: "POST",
      headers: headers(service, "macos"),
      body: JSON.stringify(payload),
    });
    const replay = await service.app.request("/v1/chat-messages", {
      method: "POST",
      headers: headers(service, "macos"),
      body: JSON.stringify(payload),
    });
    expect([first.status, replay.status]).toEqual([201, 200]);
    expect(row(await evidence(service), "macos", "chat")).toMatchObject({
      http: { successful: 2 },
      chat: { acceptedAdmission: 1 },
    });

    const server = Bun.serve({
      hostname: "127.0.0.1",
      port: 0,
      fetch: service.app.fetch,
      websocket: service.websocket,
    });
    openServers.push(server);
    const session = "a661b15a-2401-4f5c-a4c4-23643dcf26d1";
    const socket = new WebSocket(
      `ws://127.0.0.1:${server.port}/v4/listen?client_conversation_id=${session}`,
      { headers: headers(service, "ios") },
    );
    let ready = false;
    socket.addEventListener("message", (event) => {
      const frame = JSON.parse(String(event.data)) as { readonly status?: unknown };
      if (frame.status === "ready") ready = true;
    });
    await new Promise<void>((resolve, reject) => {
      socket.addEventListener("open", () => resolve(), { once: true });
      socket.addEventListener("error", () => reject(new Error("websocket open failed")), {
        once: true,
      });
    });
    await waitUntil(() => ready);
    expect(row(await evidence(service), "ios", "listen").listen).toEqual({
      protocolReady: 1,
      acceptedBinary: 0,
      acceptedBinaryBytes: 0,
    });
    socket.send(new Uint8Array());
    await Bun.sleep(10);
    expect(row(await evidence(service), "ios", "listen").listen?.acceptedBinary).toBe(0);
    socket.send(new Uint8Array([1, 2, 3, 4]));
    await waitUntil(() => service.evidence.snapshot(RUN).rows.some((candidate) =>
      candidate.shell === "ios" && candidate.domain === "listen"
      && candidate.listen?.acceptedBinary === 1));
    expect(row(await evidence(service), "ios", "listen").listen).toEqual({
      protocolReady: 1,
      acceptedBinary: 1,
      acceptedBinaryBytes: 4,
    });
    socket.close(1000, "done");
  });

  test("explicit reset clears every producer coordinate", async () => {
    const service = boot();
    expect((await service.app.request("/v1/memories", {
      headers: headers(service, "macos"),
    })).status).toBe(200);
    expect(row(await evidence(service), "macos", "memories").http?.successful).toBe(1);
    expect((await service.app.request("/v1/qa/reset", {
      method: "POST",
      headers: { authorization: `Bearer ${service.devToken}` },
    })).status).toBe(200);
    expect(row(await evidence(service), "macos", "memories").http?.successful).toBe(0);
  });
});
