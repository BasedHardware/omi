// domain-pending(DIV-CHAT-REV-001)
// domain-pending(DIV-CHAT-HASH-001)
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test } from "bun:test";

import type { QaProducerEvidenceDocument } from "../observability/producer-evidence";

const PORT = 4851;
const BASE_URL = `http://127.0.0.1:${PORT}`;
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
): Promise<{ readonly child: Bun.Subprocess; readonly readiness: Readiness }> => {
  const child = Bun.spawn([process.execPath, "apps/service/bin/dev-server.ts"], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      OMI_PORT: String(PORT),
      OMI_QA_DB: databasePath,
      OMI_RUN_ID: RUN,
      OMI_DEV_READY_RECORD: readinessPath,
      TZ: "UTC",
    },
    stdout: "ignore",
    stderr: "pipe",
  });
  try {
    await waitUntil(async () => {
      if (!existsSync(readinessPath)) return false;
      try {
        return (await fetch(`${BASE_URL}/ready`)).status === 200;
      } catch {
        return false;
      }
    });
  } catch (error) {
    const stderr = await new Response(child.stderr).text();
    child.kill("SIGTERM");
    throw new Error(`${String(error)}; dev-server stderr: ${stderr}`);
  }
  return {
    child,
    readiness: JSON.parse(readFileSync(readinessPath, "utf8")) as Readiness,
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
  path: string,
  token: string,
  body: unknown,
  shell: "macos" | "ios" = "macos",
): Promise<Response> => fetch(`${BASE_URL}${path}`, {
  method: "POST",
  headers: authorizedHeaders(token, shell),
  body: JSON.stringify(body),
});

const cutOverTasks = async (token: string): Promise<void> => {
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
    expect((await postJson("/v1/qa/control/observe", token, body)).status).toBe(200);
  }
  expect((await postJson("/v1/qa/control/activate", token, {
    epoch: 7,
    at_control_revision: 3,
  })).status).toBe(200);
};

const chatPayload = (shell: "macos" | "ios") => ({
  op: "create",
  opId: `op-subprocess-${shell}`,
  id: `subprocess-chat-${shell}`,
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

const listen = async (token: string, shell: "macos" | "ios"): Promise<void> => {
  const session = shell === "macos"
    ? "a661b15a-2401-4f5c-a4c4-23643dcf26d1"
    : "8f95c2d8-f398-4d72-94d3-580cffc96ef7";
  const socket = new WebSocket(
    `ws://127.0.0.1:${PORT}/v4/listen?client_conversation_id=${session}`,
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

const exerciseShell = async (token: string, shell: "macos" | "ios"): Promise<void> => {
  for (const path of [
    "/v1/memories",
    "/v1/tasks",
    "/v1/conversations",
    "/v1/folders",
    "/v1/settings",
  ]) {
    expect((await fetch(`${BASE_URL}${path}`, {
      headers: authorizedHeaders(token, shell),
    })).status).toBe(200);
  }
  expect((await postJson("/v1/chat-messages", token, chatPayload(shell), shell)).status).toBe(201);
  await listen(token, shell);
};

test("real dev-server owns one durable SQLite service for all seven domains", async () => {
  const directory = mkdtempSync(join(tmpdir(), "omi-dev-server-proof-"));
  const databasePath = join(directory, "qa.sqlite");
  const readinessPath = join(directory, "readiness.json");
  let child: Bun.Subprocess | null = null;
  try {
    const first = await spawnService(databasePath, readinessPath);
    child = first.child;
    expect(first.readiness).toMatchObject({
      schema: "omi.dev-service-readiness.v1",
      runId: RUN,
      executable: "apps/service/bin/dev-server.ts",
      baseUrl: BASE_URL,
      databasePath,
      evidencePath: "/v1/qa/evidence",
      ownerAccountId: "local-dev-user",
    });
    expect(first.readiness.pid).toBe(first.child.pid);
    await cutOverTasks(first.readiness.devToken);
    await exerciseShell(first.readiness.devToken, "macos");
    await exerciseShell(first.readiness.devToken, "ios");

    const createdFolder = await postJson("/v1/folders", first.readiness.devToken, {
      name: "Persisted across restart",
    });
    expect(createdFolder.status).toBe(201);
    expect(await createdFolder.json()).toEqual({ id: "qa-folder-created-001" });

    const producer = await fetch(`${BASE_URL}/v1/qa/evidence?run=${RUN}`, {
      headers: { authorization: `Bearer ${first.readiness.devToken}` },
    });
    expect(producer.status).toBe(200);
    const document = await producer.json() as QaProducerEvidenceDocument;
    expect(document.rows).toHaveLength(14);
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
    rmSync(readinessPath);

    const second = await spawnService(databasePath, readinessPath);
    child = second.child;
    const folders = await fetch(`${BASE_URL}/v1/folders`, {
      headers: authorizedHeaders(second.readiness.devToken, "macos"),
    });
    expect((await folders.json() as readonly { readonly id: string }[])
      .some((folder) => folder.id === "qa-folder-created-001")).toBeTrue();
    const history = await fetch(`${BASE_URL}/v1/chat-messages`, {
      headers: authorizedHeaders(second.readiness.devToken, "macos"),
    });
    const messages = (await history.json() as {
      readonly messages: readonly { readonly id: string }[];
    }).messages;
    expect(messages.map((message) => message.id)).toContain("subprocess-chat-macos");
    expect(messages.map((message) => message.id)).toContain("subprocess-chat-ios");

    expect((await fetch(`${BASE_URL}/v1/qa/reset`, {
      method: "POST",
      headers: { authorization: `Bearer ${second.readiness.devToken}` },
    })).status).toBe(200);
    const resetFolders = await fetch(`${BASE_URL}/v1/folders`, {
      headers: authorizedHeaders(second.readiness.devToken, "macos"),
    });
    expect((await resetFolders.json() as readonly { readonly id: string }[])
      .some((folder) => folder.id === "qa-folder-created-001")).toBeFalse();
    const resetHistory = await fetch(`${BASE_URL}/v1/chat-messages`, {
      headers: authorizedHeaders(second.readiness.devToken, "macos"),
    });
    expect((await resetHistory.json() as { readonly messages: readonly unknown[] }).messages)
      .toEqual([]);
  } finally {
    if (child !== null) await stopService(child);
    rmSync(directory, { recursive: true, force: true });
  }
}, 20_000);
