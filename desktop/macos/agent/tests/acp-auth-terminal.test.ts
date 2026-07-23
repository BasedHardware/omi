import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { AcpError, isAcpProviderAuthFailure } from "../src/adapters/acp.js";
import type { OutboundMessageDraft, QueryMessage } from "../src/protocol.js";
import { JsonlTransport } from "../src/runtime/jsonl-transport.js";
import { createKernelHarness } from "./kernel-fakes.js";

const roots: string[] = [];

afterEach(() => {
  while (roots.length) rmSync(roots.pop()!, { recursive: true, force: true });
});

function acpAuthFixture() {
  const root = mkdtempSync(join(tmpdir(), "omi-acp-auth-"));
  roots.push(root);
  const { store, adapter, kernel } = createKernelHarness(join(root, "agent.sqlite"), "acp");
  const session = store.insertSession({
    ownerId: "owner",
    surfaceKind: "main_chat",
    externalRefKind: "chat",
    externalRefId: "default",
    defaultAdapterId: "acp",
    defaultCwd: "/tmp/pinned-workspace",
    modelProfile: "pinned-model",
  });
  const sent: OutboundMessageDraft[] = [];
  const logs: string[] = [];
  let authSignals = 0;
  let activeOwner = "owner";
  const transport = new JsonlTransport({
    kernel,
    ownerId: "owner",
    activeOwnerId: () => activeOwner,
    send: (message) => sent.push(message),
    log: (message) => logs.push(message),
    defaultAdapterId: "acp",
    isRecoverableError: (error, adapterId) =>
      adapterId === "acp" && isAcpProviderAuthFailure(error),
    onRecoverableError: async () => {
      authSignals += 1;
      sent.push({ type: "auth_required", methods: [] });
    },
    maxRecoverableRetries: 2,
  });
  return { store, adapter, session, sent, logs, transport, authSignals: () => authSignals };
}

function query(sessionId: string, overrides: Partial<QueryMessage> = {}): QueryMessage {
  return {
    type: "query",
    protocolVersion: 2,
    requestId: "request-1",
    clientId: "client-1",
    ownerId: "owner",
    sessionId,
    prompt: "hello",
    mode: "act",
    ...overrides,
  };
}

describe("ACP provider auth terminalize-first (T1/T2)", () => {
  it("T1: -32000 auth failure terminalizes immediately without OAuth retry", async () => {
    const { store, adapter, session, sent, logs, transport, authSignals } = acpAuthFixture();
    adapter.failNextExecutionError = new AcpError("Authentication required", -32000);

    const startedAt = Date.now();
    await transport.handleQuery(query(session.sessionId, { requestId: "request-auth-1" }));
    const elapsedMs = Date.now() - startedAt;

    expect(elapsedMs).toBeLessThan(1_000);
    expect(adapter.executed).toHaveLength(1);
    expect(
      store.allRows(
        "SELECT attempt_no, status FROM run_attempts WHERE run_id = (SELECT run_id FROM runs WHERE request_id = ?)",
        ["request-auth-1"],
      ),
    ).toEqual([{ attempt_no: 1, status: "failed" }]);
    expect(authSignals()).toBe(1);
    expect(logs.some((line) => line.includes("Auth flow already in progress"))).toBe(false);

    const result = sent.findLast((message) => message.type === "result");
    expect(result).toMatchObject({
      type: "result",
      terminalStatus: "failed",
      failure: { failureCode: "authentication" },
    });
    store.close();
  });

  it("T2: a second auth failure does not join an in-band OAuth wait", async () => {
    const { store, adapter, session, logs, transport, authSignals } = acpAuthFixture();
    adapter.failNextExecutionError = new AcpError("Authentication required", -32000);
    await transport.handleQuery(query(session.sessionId, { requestId: "request-auth-a" }));

    adapter.failNextExecutionError = new AcpError("Authentication required", -32000);
    await transport.handleQuery(query(session.sessionId, { requestId: "request-auth-b" }));

    expect(authSignals()).toBe(2);
    expect(logs.filter((line) => line.includes("Auth flow already in progress"))).toEqual([]);
    expect(store.getRow("SELECT COUNT(*) AS count FROM run_attempts").count).toBe(2);
    store.close();
  });
});
