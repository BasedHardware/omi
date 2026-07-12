import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import {
  RunToolCapabilityBroker,
  RunToolCapabilityRejectedError,
  type AuthorizedRunToolInvocation,
} from "../src/runtime/run-tool-capability.js";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";
import { readToolInvocation } from "../src/runtime/tool-invocation-ledger.js";

const roots: string[] = [];

afterEach(() => {
  while (roots.length) rmSync(roots.pop()!, { recursive: true, force: true });
});

function fixture(role: "coordinator" | "leaf" = "coordinator") {
  const root = mkdtempSync(join(tmpdir(), "omi-capability-"));
  roots.push(root);
  const databasePath = join(root, "agent.sqlite");
  const store = new SqliteAgentStore({ databasePath, reconcileOnOpen: false });
  const session = store.insertSession({
    ownerId: "owner-1",
    surfaceKind: role === "leaf" ? "background_agent" : "main_chat",
    defaultAdapterId: "acp",
    executionRole: role,
  });
  const run = store.insertRun({
    sessionId: session.sessionId,
    clientId: "trace-client",
    requestId: "trace-request",
    status: "running",
    mode: "act",
  });
  const attempt = store.insertAttempt({
    runId: run.runId,
    attemptNo: 1,
    status: "running",
    adapterId: "acp",
    adapterInstanceId: "worker",
  });
  return { databasePath, store, session, run, attempt };
}

function expectCode(work: () => unknown, code: string): void {
  try {
    work();
    throw new Error("Expected capability rejection");
  } catch (error) {
    expect(error).toBeInstanceOf(RunToolCapabilityRejectedError);
    expect((error as RunToolCapabilityRejectedError).code).toBe(code);
  }
}

function invocationIdentity(invocation: AuthorizedRunToolInvocation) {
  return {
    invocationId: invocation.invocationId,
    ownerId: invocation.ownerId,
    sessionId: invocation.sessionId,
    runId: invocation.runId,
    attemptId: invocation.attemptId,
    profileGeneration: invocation.profileGeneration,
    manifestVersion: invocation.manifestVersion,
    manifestDigest: invocation.manifestDigest,
    daemonBootEpoch: invocation.daemonBootEpoch,
    executionGeneration: invocation.executionGeneration,
    inputHash: invocation.inputHash,
  };
}

describe("RunToolCapabilityBroker", () => {
  it("authorizes two direct-child memory calls and persists each single-use lifecycle", () => {
    const { store, session, run, attempt } = fixture("leaf");
    const broker = new RunToolCapabilityBroker({ store, daemonBootEpoch: "boot-test" });
    expect(session.executionRole).toBe("leaf");
    const capability = broker.register({
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
    });

    for (const [index, invocationId] of ["memory-1", "memory-2"].entries()) {
      const authorized = broker.authorize({
        capabilityRef: capability.capabilityRef,
        invocationId,
        runId: run.runId,
        attemptId: attempt.attemptId,
        activeOwnerId: session.ownerId,
        toolName: "get_memories",
        toolInput: { limit: index + 1 },
      });
      expect(authorized).toMatchObject({
        canonicalToolName: "get_memories",
        ownerId: session.ownerId,
        effectClass: "read_only",
        retryPolicy: "safe_retry",
        manifestDigest: expect.stringMatching(/^sha256:[a-f0-9]{64}$/),
      });
      broker.markInvocationDispatched(authorized);
      broker.completeInvocation({
        ...invocationIdentity(authorized),
        capabilityRef: authorized.capabilityRef,
        outcome: "succeeded",
        result: JSON.stringify({ ok: true, index }),
      });
      expect(readToolInvocation(store, invocationId).status).toBe("succeeded");
    }

    expectCode(
      () => broker.authorize({
        capabilityRef: capability.capabilityRef,
        invocationId: "memory-2",
        runId: run.runId,
        attemptId: attempt.attemptId,
        activeOwnerId: session.ownerId,
        toolName: "get_memories",
        toolInput: { limit: 2 },
      }),
      "invocation_replayed",
    );
    store.close();
  });

  it("rejects stale and duplicate Swift results by the exact persisted tuple", () => {
    const { store, session, run, attempt } = fixture();
    const broker = new RunToolCapabilityBroker({ store });
    const capability = broker.register({
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
    });
    const authorized = broker.authorize({
      capabilityRef: capability.capabilityRef,
      invocationId: "exact-result",
      runId: run.runId,
      attemptId: attempt.attemptId,
      activeOwnerId: session.ownerId,
      toolName: "get_memories",
      toolInput: {},
    });
    broker.markInvocationDispatched(authorized);
    expect(() => broker.completeInvocation({
      ...invocationIdentity(authorized),
      manifestDigest: "sha256:stale",
      outcome: "succeeded",
      result: "wrong",
    })).toThrow(/stale, duplicated, or was never dispatched/);
    expect(readToolInvocation(store, authorized.invocationId).status).toBe("dispatched");
    broker.completeInvocation({
      ...invocationIdentity(authorized),
      outcome: "succeeded",
      result: "correct",
    });
    expect(() => broker.completeInvocation({
      ...invocationIdentity(authorized),
      outcome: "succeeded",
      result: "duplicate",
    })).toThrow(/stale, duplicated, or was never dispatched/);
    store.close();
  });

  it("fails closed for wrong owner, run, attempt, role, and unmanifested tools", () => {
    const { store, session, run, attempt } = fixture("leaf");
    const broker = new RunToolCapabilityBroker({ store });
    const capability = broker.register({
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
    });
    const base = {
      capabilityRef: capability.capabilityRef,
      invocationId: "invoke",
      runId: run.runId,
      attemptId: attempt.attemptId,
      activeOwnerId: session.ownerId,
      toolName: "get_memories",
      toolInput: {},
    };
    expect(capability.allowedToolNames).not.toContain("spawn_agent");
    expectCode(() => broker.authorize({ ...base, activeOwnerId: "owner-2" }), "owner_mismatch");
    expectCode(() => broker.authorize({ ...base, runId: "run_other" }), "run_mismatch");
    expectCode(() => broker.authorize({ ...base, attemptId: "att_other" }), "attempt_mismatch");
    expectCode(() => broker.authorize({ ...base, toolName: "not_a_real_tool" }), "tool_not_manifested");
    expectCode(() => broker.authorize({ ...base, toolName: "spawn_agent" }), "tool_not_allowed");
    store.close();
  });

  it("keeps capability state internal and revokes it at terminal attempt", () => {
    const { store, session, run, attempt } = fixture();
    const broker = new RunToolCapabilityBroker({ store });
    const capability = broker.register({
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
    });
    store.execute("UPDATE run_attempts SET status = 'succeeded' WHERE attempt_id = ?", [attempt.attemptId]);
    store.execute("UPDATE runs SET status = 'succeeded' WHERE run_id = ?", [run.runId]);
    broker.handleKernelEvent({
      eventId: "evt-terminal",
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
      type: "attempt.succeeded",
      retentionClass: "core",
      visibility: "internal",
      payloadJson: "{}",
      createdAtMs: 1,
    });
    expect(broker.activeCapabilityForAttempt(attempt.attemptId)).toBeUndefined();
    expectCode(() => broker.authorize({
      capabilityRef: capability.capabilityRef,
      invocationId: "late",
      runId: run.runId,
      attemptId: attempt.attemptId,
      activeOwnerId: session.ownerId,
      toolName: "get_memories",
      toolInput: {},
    }), "capability_revoked");
    store.close();
  });

  it("derives screen-image availability from the immutable admitted context", () => {
    for (const [screenOutcome, expected] of [
      ["unavailable", false],
      ["available", true],
    ] as const) {
      const { store, session, run, attempt } = fixture();
      store.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", [
        JSON.stringify({
          prompt: "Inspect the screen only when admitted",
          admittedContextSnapshot: {
            sourceOutcomes: [{ source: "screen", outcome: screenOutcome }],
          },
        }),
        run.runId,
      ]);
      const broker = new RunToolCapabilityBroker({ store });
      const capability = broker.register({
        ownerId: session.ownerId,
        sessionId: session.sessionId,
        runId: run.runId,
        attemptId: attempt.attemptId,
      });
      expect(capability.allowedToolNames.includes("capture_screen")).toBe(expected);
      store.close();
    }
  });

  it("rejects new invocations as soon as either run or attempt starts cancelling", () => {
    for (const cancellingOwner of ["run", "attempt"] as const) {
      const { store, session, run, attempt } = fixture();
      const broker = new RunToolCapabilityBroker({ store });
      const capability = broker.register({
        ownerId: session.ownerId,
        sessionId: session.sessionId,
        runId: run.runId,
        attemptId: attempt.attemptId,
      });
      if (cancellingOwner === "run") {
        store.execute("UPDATE runs SET status = 'cancelling' WHERE run_id = ?", [run.runId]);
      } else {
        store.execute("UPDATE run_attempts SET status = 'cancelling' WHERE attempt_id = ?", [attempt.attemptId]);
      }
      expectCode(() => broker.authorize({
        capabilityRef: capability.capabilityRef,
        invocationId: `after-${cancellingOwner}-cancel`,
        runId: run.runId,
        attemptId: attempt.attemptId,
        activeOwnerId: session.ownerId,
        toolName: "get_memories",
        toolInput: {},
      }), cancellingOwner === "run" ? "run_terminal" : "attempt_terminal");
      store.close();
    }
  });

  it("reconciles prepared to failed and dispatched to outcome_unknown after restart", () => {
    const { databasePath, store, session, run, attempt } = fixture();
    const broker = new RunToolCapabilityBroker({ store, daemonBootEpoch: "boot-before" });
    const capability = broker.register({
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
    });
    const prepared = broker.authorize({
      capabilityRef: capability.capabilityRef,
      invocationId: "prepared-crash",
      runId: run.runId,
      attemptId: attempt.attemptId,
      activeOwnerId: session.ownerId,
      toolName: "get_memories",
      toolInput: {},
    });
    const dispatched = broker.authorize({
      capabilityRef: capability.capabilityRef,
      invocationId: "dispatched-crash",
      runId: run.runId,
      attemptId: attempt.attemptId,
      activeOwnerId: session.ownerId,
      toolName: "get_memories",
      toolInput: { limit: 1 },
    });
    broker.markInvocationDispatched(dispatched);
    expect(readToolInvocation(store, prepared.invocationId).status).toBe("prepared");
    store.close();

    const reopened = new SqliteAgentStore({ databasePath });
    expect(readToolInvocation(reopened, prepared.invocationId)).toMatchObject({
      status: "failed",
      errorCode: "daemon_restart_before_dispatch",
    });
    expect(readToolInvocation(reopened, dispatched.invocationId)).toMatchObject({
      status: "outcome_unknown",
      errorCode: "daemon_restart_after_dispatch",
      retryPolicy: "safe_retry",
    });
    reopened.close();
  });
});
