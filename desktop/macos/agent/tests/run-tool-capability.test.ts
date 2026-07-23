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
import { readSessionExecutionProfile } from "../src/runtime/session-execution-profile.js";
import { recordJournalTurn } from "../src/runtime/conversation-journal.js";

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

function createBroker(
  store: SqliteAgentStore,
  options: Omit<ConstructorParameters<typeof RunToolCapabilityBroker>[0], "store" | "profileForSession"> = {},
): RunToolCapabilityBroker {
  return new RunToolCapabilityBroker({
    store,
    ...options,
    profileForSession: (sessionId) => readSessionExecutionProfile(store, sessionId),
  });
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
  it("requires the canonical profile reader and rejects unknown canonical adapters", () => {
    const { store } = fixture();
    expect(() => new RunToolCapabilityBroker({ store } as never)).toThrow(
      /requires a canonical session profile reader/,
    );
    const session = store.insertSession({
      ownerId: "owner-1",
      surfaceKind: "main_chat",
      defaultAdapterId: "unknown-adapter",
    });
    const run = store.insertRun({
      sessionId: session.sessionId,
      clientId: "unknown-client",
      requestId: "unknown-request",
      status: "running",
      mode: "act",
    });
    const attempt = store.insertAttempt({
      runId: run.runId,
      attemptNo: 1,
      status: "running",
      adapterId: "unknown-adapter",
      adapterInstanceId: "unknown-worker",
    });
    const canonicalUnknown = createBroker(store);
    expect(() => canonicalUnknown.register({
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
    })).toThrow(/Unknown canonical session adapter unknown-adapter/);
    store.close();
  });

  it("uses the immutable canonical profile instead of conflicting legacy session columns", () => {
    const { store, session, run, attempt } = fixture("leaf");
    store.execute(
      "UPDATE sessions SET default_adapter_id = 'pi-mono', execution_role = 'coordinator' WHERE session_id = ?",
      [session.sessionId],
    );
    const capability = createBroker(store).register({
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
    });
    expect(capability).toMatchObject({ adapterId: "acp", executionRole: "leaf", profileGeneration: 1 });
    expect(capability.allowedToolNames).not.toContain("spawn_agent");
    store.close();
  });

  it("pins preceding assistant text to the run's admitted context snapshot", () => {
    const { store, session, run, attempt } = fixture();
    store.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", [
      JSON.stringify({
        prompt: "Continue from the accepted context",
        admittedContextSnapshot: {
          recentTurns: [
            { role: "assistant", content: "assistant-at-admission" },
            { role: "user", content: "accepted user prompt" },
          ],
          sourceOutcomes: [],
        },
      }),
      run.runId,
    ]);
    store.insertSurfaceConversation({
      ownerId: session.ownerId,
      surfaceKind: session.surfaceKind,
      externalRefKind: "chat",
      externalRefId: "default",
      conversationId: "conv-live-newer",
      agentSessionId: session.sessionId,
      createdAtMs: 1,
      lastActiveAtMs: 1,
    });
    recordJournalTurn(store, {
      ownerId: session.ownerId,
      conversationId: "conv-live-newer",
      turnId: "assistant-after-admission",
      role: "assistant",
      surfaceKind: session.surfaceKind,
      origin: "typed_chat",
      status: "completed",
      content: "newer-live-assistant-must-not-leak",
      contentBlocks: [],
      createdAtMs: 2,
    });

    const capability = createBroker(store).register({
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
    });
    expect(capability.precedingAssistantText).toBe("assistant-at-admission");
    store.close();
  });

  it("authorizes two direct-child memory calls and persists each single-use lifecycle", () => {
    const { store, session, run, attempt } = fixture("leaf");
    const broker = createBroker(store, { daemonBootEpoch: "boot-test" });
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
        activeOwnerId: session.ownerId,
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
    const broker = createBroker(store);
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
      capabilityRef: authorized.capabilityRef,
      activeOwnerId: session.ownerId,
      manifestDigest: "sha256:stale",
      outcome: "succeeded",
      result: "wrong",
    })).toThrow(/stale, duplicated, or was never dispatched/);
    expect(readToolInvocation(store, authorized.invocationId).status).toBe("dispatched");
    broker.completeInvocation({
      ...invocationIdentity(authorized),
      capabilityRef: authorized.capabilityRef,
      activeOwnerId: session.ownerId,
      outcome: "succeeded",
      result: "correct",
    });
    expect(() => broker.completeInvocation({
      ...invocationIdentity(authorized),
      capabilityRef: authorized.capabilityRef,
      activeOwnerId: session.ownerId,
      outcome: "succeeded",
      result: "duplicate",
    })).toThrow(/no longer active at completion/);
    store.close();
  });

  it("revalidates the active owner before accepting a durable completion", () => {
    const { store, session, run, attempt } = fixture();
    const broker = createBroker(store);
    const capability = broker.register({
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
    });
    const authorized = broker.authorize({
      capabilityRef: capability.capabilityRef,
      invocationId: "owner-switched-completion",
      runId: run.runId,
      attemptId: attempt.attemptId,
      activeOwnerId: session.ownerId,
      toolName: "get_memories",
      toolInput: {},
    });
    broker.markInvocationDispatched(authorized);

    expectCode(() => broker.completeInvocation({
      ...invocationIdentity(authorized),
      capabilityRef: authorized.capabilityRef,
      activeOwnerId: "owner-2",
      outcome: "succeeded",
      result: JSON.stringify({ ok: true }),
    }), "owner_mismatch");
    expect(readToolInvocation(store, authorized.invocationId)).toMatchObject({
      status: "outcome_unknown",
      errorCode: "run_tool_owner_changed",
    });
    store.close();
  });

  it("fails closed for wrong owner, run, attempt, role, and unmanifested tools", () => {
    const { store, session, run, attempt } = fixture("leaf");
    const broker = createBroker(store);
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
    const broker = createBroker(store);
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

  it("aborts an acquired execution lease and revalidates persisted authority at effect boundaries", () => {
    const { store, session, run, attempt } = fixture();
    const broker = createBroker(store);
    const capability = broker.register({
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
    });
    const authorized = broker.authorize({
      capabilityRef: capability.capabilityRef,
      invocationId: "leased-control-effect",
      runId: run.runId,
      attemptId: attempt.attemptId,
      activeOwnerId: session.ownerId,
      toolName: "spawn_agent",
      toolInput: { objective: "bounded effect" },
    });
    broker.markInvocationDispatched(authorized);
    const lease = broker.acquireExecutionLease(authorized, () => session.ownerId);
    lease.assertCurrentAuthority();
    expect(lease.signal.aborted).toBe(false);

    store.execute("UPDATE run_attempts SET status = 'cancelled' WHERE attempt_id = ?", [attempt.attemptId]);
    expectCode(() => lease.assertCurrentAuthority(), "attempt_terminal");
    expect(lease.signal.aborted).toBe(true);
    expectCode(() => broker.completeInvocation({
      ...invocationIdentity(authorized),
      capabilityRef: authorized.capabilityRef,
      activeOwnerId: session.ownerId,
      outcome: "failed",
      result: JSON.stringify({ ok: false, error: { code: "attempt_terminal" } }),
    }), "attempt_terminal");
    expect(readToolInvocation(store, authorized.invocationId)).toMatchObject({
      status: "outcome_unknown",
      errorCode: "run_tool_attempt_terminal",
    });
    store.close();
  });

  it("terminalizes every pending invocation and rejects late durable success after a run ends", () => {
    const { store, session, run, attempt } = fixture();
    const broker = createBroker(store);
    const capability = broker.register({
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
    });
    const prepared = broker.authorize({
      capabilityRef: capability.capabilityRef,
      invocationId: "terminal-prepared",
      runId: run.runId,
      attemptId: attempt.attemptId,
      activeOwnerId: session.ownerId,
      toolName: "get_memories",
      toolInput: {},
    });
    const dispatched = broker.authorize({
      capabilityRef: capability.capabilityRef,
      invocationId: "terminal-dispatched",
      runId: run.runId,
      attemptId: attempt.attemptId,
      activeOwnerId: session.ownerId,
      toolName: "get_memories",
      toolInput: { limit: 1 },
    });
    broker.markInvocationDispatched(dispatched);
    store.execute("UPDATE run_attempts SET status = 'succeeded' WHERE attempt_id = ?", [attempt.attemptId]);
    store.execute("UPDATE runs SET status = 'succeeded' WHERE run_id = ?", [run.runId]);
    broker.handleKernelEvent({
      eventId: "evt-run-terminal",
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
      type: "run.succeeded",
      retentionClass: "core",
      visibility: "internal",
      payloadJson: "{}",
      createdAtMs: 1,
    });

    expect(readToolInvocation(store, prepared.invocationId)).toMatchObject({
      status: "failed",
      errorCode: "run_tool_run_terminal",
    });
    expect(readToolInvocation(store, dispatched.invocationId)).toMatchObject({
      status: "outcome_unknown",
      errorCode: "run_tool_run_terminal",
    });
    expectCode(() => broker.completeInvocation({
      ...invocationIdentity(dispatched),
      capabilityRef: dispatched.capabilityRef,
      activeOwnerId: session.ownerId,
      outcome: "succeeded",
      result: JSON.stringify({ ok: true }),
    }), "run_terminal");
    expect(readToolInvocation(store, dispatched.invocationId).status).toBe("outcome_unknown");
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
      const broker = createBroker(store);
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
      const broker = createBroker(store);
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
    const broker = createBroker(store, { daemonBootEpoch: "boot-before" });
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

describe("RunToolCapabilityBroker spawn-time tool policy", () => {
  it("intersects a spawn-time toolPolicy with the computed allowlist", () => {
    const { store, session, run, attempt } = fixture("leaf");
    store.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", [
      JSON.stringify({
        prompt: "restricted child",
        metadata: { toolPolicy: { allowedToolNames: ["get_memories"] } },
      }),
      run.runId,
    ]);
    const broker = createBroker(store);
    const capability = broker.register({
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
    });

    expect(capability.allowedToolNames).toEqual(["get_memories"]);
    const authorized = broker.authorize({
      capabilityRef: capability.capabilityRef,
      invocationId: "policy-allowed-1",
      runId: run.runId,
      attemptId: attempt.attemptId,
      activeOwnerId: session.ownerId,
      toolName: "get_memories",
      toolInput: {},
    });
    expect(authorized.canonicalToolName).toBe("get_memories");
    expectCode(
      () => broker.authorize({
        capabilityRef: capability.capabilityRef,
        invocationId: "policy-denied-1",
        runId: run.runId,
        attemptId: attempt.attemptId,
        activeOwnerId: session.ownerId,
        toolName: "search_memories",
        toolInput: {},
      }),
      "tool_not_allowed",
    );
    store.close();
  });

  it("keeps the full role-computed allowlist when no toolPolicy is present", () => {
    const { store, session, run, attempt } = fixture("leaf");
    const broker = createBroker(store);
    const capability = broker.register({
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
    });
    // Baseline for the intersection test above: both tools are normally
    // available to a leaf run, so exclusion there is policy-driven.
    expect(capability.allowedToolNames).toContain("get_memories");
    expect(capability.allowedToolNames).toContain("search_memories");
    store.close();
  });

  it("fails closed when the toolPolicy intersection is empty or the policy is malformed", () => {
    for (const toolPolicy of [{ allowedToolNames: ["not_a_real_tool"] }, "bogus", { allowedToolNames: "bogus" }]) {
      const { store, session, run, attempt } = fixture("leaf");
      store.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", [
        JSON.stringify({ prompt: "restricted child", metadata: { toolPolicy } }),
        run.runId,
      ]);
      const broker = createBroker(store);
      const capability = broker.register({
        ownerId: session.ownerId,
        sessionId: session.sessionId,
        runId: run.runId,
        attemptId: attempt.attemptId,
      });
      expect(capability.allowedToolNames).toEqual([]);
      expectCode(
        () => broker.authorize({
          capabilityRef: capability.capabilityRef,
          invocationId: "policy-closed-1",
          runId: run.runId,
          attemptId: attempt.attemptId,
          activeOwnerId: session.ownerId,
          toolName: "get_memories",
          toolInput: {},
        }),
        "tool_not_allowed",
      );
      store.close();
    }
  });
});
