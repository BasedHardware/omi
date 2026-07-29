import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import { initializeAcpWithDetachedAuth } from "../src/acp-initialize-auth.js";
import { AcpError, isAcpProviderAuthFailure } from "../src/adapters/acp.js";
import type { OutboundMessageDraft, QueryMessage } from "../src/protocol.js";
import { failureFromError } from "../src/runtime/failures.js";
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

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe("ACP provider auth terminalize-first (T1/T2)", () => {
  it("terminalizes initialize auth-required before OAuth completes, then reinitializes after success", async () => {
    const oauth = deferred<void>();
    const authRequired = new AcpError("Authentication required", -32000);
    const signalAuthRequired = vi.fn();
    const reinitialize = vi.fn(async () => {});
    const log = vi.fn();
    const sent: OutboundMessageDraft[] = [];

    await (async () => {
      try {
        await initializeAcpWithDetachedAuth({
          initialize: async () => {
            throw authRequired;
          },
          onAuthRequired: () => {},
          signalAuthRequired,
          startAuthFlow: () => oauth.promise,
          reinitialize,
          log,
        });
      } catch (error) {
        const failure = failureFromError(error, {
          code: "runtime_error",
          source: "runtime",
          retryable: false,
        });
        sent.push({ type: "error", message: failure.userMessage, failure });
      }
    })();

    expect(signalAuthRequired).toHaveBeenCalledOnce();
    expect(sent).toMatchObject([{
      type: "error",
      failure: { failureCode: "authentication" },
    }]);
    expect(reinitialize).not.toHaveBeenCalled();

    oauth.resolve();
    await Promise.resolve();

    expect(reinitialize).toHaveBeenCalledOnce();
    expect(log).not.toHaveBeenCalled();
  });

  it("logs a detached OAuth failure after terminalizing initialize auth-required", async () => {
    const oauth = deferred<void>();
    const authRequired = new AcpError("Authentication required", -32000);
    const log = vi.fn();

    await expect(
      initializeAcpWithDetachedAuth({
        initialize: async () => {
          throw authRequired;
        },
        onAuthRequired: () => {},
        signalAuthRequired: () => {},
        startAuthFlow: () => oauth.promise,
        reinitialize: async () => {},
        log,
      }),
    ).rejects.toBe(authRequired);

    oauth.reject(new Error("OAuth callback timed out"));
    await Promise.resolve();
    await Promise.resolve();

    expect(log).toHaveBeenCalledWith("ACP authentication retry failed: Error: OAuth callback timed out");
  });

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
