import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import {
  DESKTOP_APPROVAL_TOOLS,
  RunToolCapabilityBroker,
  RunToolCapabilityRejectedError,
  toolApprovalInvocationBinding,
  type AuthorizedRunToolInvocation,
} from "../src/runtime/run-tool-capability.js";
import { desktopToolPolicyInternals, evaluateDesktopToolPolicy } from "../src/runtime/desktop-tool-policy.js";
import { allOmiToolManifest } from "../src/runtime/omi-tool-manifest.js";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";
import { readToolInvocation } from "../src/runtime/tool-invocation-ledger.js";
import { readSessionExecutionProfile } from "../src/runtime/session-execution-profile.js";
import { recordJournalTurn } from "../src/runtime/conversation-journal.js";

const roots: string[] = [];

afterEach(() => {
  while (roots.length) rmSync(roots.pop()!, { recursive: true, force: true });
});

function fixture(
  role: "coordinator" | "leaf" = "coordinator",
  mode: "ask" | "act" = "act",
  surfaceKind?: string,
) {
  const root = mkdtempSync(join(tmpdir(), "omi-capability-"));
  roots.push(root);
  const databasePath = join(root, "agent.sqlite");
  const store = new SqliteAgentStore({ databasePath, reconcileOnOpen: false });
  const session = store.insertSession({
    ownerId: "owner-1",
    surfaceKind: surfaceKind ?? (role === "leaf" ? "background_agent" : "main_chat"),
    defaultAdapterId: "acp",
    executionRole: role,
  });
  const run = store.insertRun({
    sessionId: session.sessionId,
    clientId: "trace-client",
    requestId: "trace-request",
    status: "running",
    mode,
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
  it("hard-denies ask-mode service writes without trusting an external-ref prefix", () => {
    const { store, session, run, attempt } = fixture("coordinator", "ask");
    store.execute(
      "UPDATE sessions SET surface_kind = 'service', external_ref_kind = 'service', external_ref_id = 'arbitrary-label' WHERE session_id = ?",
      [session.sessionId],
    );
    const broker = createBroker(store);
    const capability = broker.register({
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
    });
    const base = {
      capabilityRef: capability.capabilityRef,
      runId: run.runId,
      attemptId: attempt.attemptId,
      activeOwnerId: session.ownerId,
      toolInput: {},
    };

    expect(capability.builtInToolPolicy).toBe("read_only");

    expectCode(
      () => broker.authorize({ ...base, invocationId: "write", toolName: "create_memory" }),
      "tool_not_allowed",
    );
    expect(
      broker.authorize({ ...base, invocationId: "read", toolName: "search_memories" }).effectClass,
    ).toBe("read_only");
    store.close();
  });

  it("keeps ordinary ask-mode chat adapter built-ins and manifest writes on default authority", () => {
    const { store, session, run, attempt } = fixture("coordinator", "ask");
    const broker = createBroker(store);
    const capability = broker.register({
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
    });
    expect(capability.builtInToolPolicy).toBe("default");
    expect(() => broker.authorize({
      capabilityRef: capability.capabilityRef,
      invocationId: "ordinary-write",
      runId: run.runId,
      attemptId: attempt.attemptId,
      activeOwnerId: session.ownerId,
      toolName: "create_memory",
      toolInput: {},
    })).not.toThrow();
    store.close();
  });

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

  it("classifies create_memory as a coordinator main-chat non-idempotent write", () => {
    const { store, session, run, attempt } = fixture();
    const broker = createBroker(store);
    const capability = broker.register({
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
    });

    expect(capability.allowedToolNames).toContain("create_memory");
    const authorized = broker.authorize({
      capabilityRef: capability.capabilityRef,
      invocationId: "create-memory-1",
      runId: run.runId,
      attemptId: attempt.attemptId,
      activeOwnerId: session.ownerId,
      toolName: "create_memory",
      toolInput: { content: "I prefer tea." },
    });
    expect(authorized).toMatchObject({
      canonicalToolName: "create_memory",
      surfaceKind: "main_chat",
      executionRole: "coordinator",
      effectClass: "non_idempotent_write",
      retryPolicy: "never_auto_retry",
    });
    expect(readToolInvocation(store, authorized.invocationId)).toMatchObject({
      effectClass: "non_idempotent_write",
      retryPolicy: "never_auto_retry",
    });
    store.close();
  });

  it.each([
    ["realtime_voice", "coordinator"],
    ["task_chat", "coordinator"],
    ["background_agent", "leaf"],
    ["delegated_agent", "leaf"],
  ] as const)("does not authorize create_memory from %s/%s", (surfaceKind, executionRole) => {
    const root = mkdtempSync(join(tmpdir(), "omi-capability-memory-scope-"));
    roots.push(root);
    const store = new SqliteAgentStore({ databasePath: join(root, "agent.sqlite"), reconcileOnOpen: false });
    const session = store.insertSession({
      ownerId: "owner-1",
      surfaceKind,
      defaultAdapterId: "acp",
      executionRole,
    });
    const run = store.insertRun({
      sessionId: session.sessionId,
      clientId: "scope-client",
      requestId: `scope-request-${surfaceKind}`,
      status: "running",
      mode: "act",
    });
    const attempt = store.insertAttempt({
      runId: run.runId,
      attemptNo: 1,
      status: "running",
      adapterId: "acp",
      adapterInstanceId: "scope-worker",
    });
    const broker = createBroker(store);
    const capability = broker.register({
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
    });
    expect(capability.allowedToolNames).not.toContain("create_memory");
    expectCode(() => broker.authorize({
      capabilityRef: capability.capabilityRef,
      invocationId: `create-memory-${surfaceKind}`,
      runId: run.runId,
      attemptId: attempt.attemptId,
      activeOwnerId: session.ownerId,
      toolName: "create_memory",
      toolInput: { content: "must not be saved" },
    }), "tool_not_allowed");
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

  it("requires a persisted desktop approval before authorizing sensitive tools", () => {
    const { store, session, run, attempt } = fixture();
    const broker = createBroker(store);
    const capability = broker.register({
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
    });
    const base = {
      capabilityRef: capability.capabilityRef,
      runId: run.runId,
      attemptId: attempt.attemptId,
      activeOwnerId: session.ownerId,
      toolName: "list_message_chats",
      toolInput: {},
    };

    expectCode(() => broker.authorize({ ...base, invocationId: "without-approval" }), "approval_required");

    store.insertGrant({
      sessionId: session.sessionId,
      runId: run.runId,
      capability: "desktop.messaging.read",
      operation: "list_message_chats",
      resourcePattern: "*",
      effect: "allow",
      source: "user",
    });
    const authorized = broker.authorize({ ...base, invocationId: "with-approval" });
    expect(authorized.canonicalToolName).toBe("list_message_chats");
    store.close();
  });

  it("authorizes surface-scoped voice tools for swift_realtime runs without leaking them elsewhere", () => {
    // Regression: realtime-voice runs relay Swift-executed voice tools that no
    // chat adapter advertises. An adapter-only allowlist rejected every such
    // tool (think_deeper, web_search, point_click) with tool_not_allowed in production.
    const root = mkdtempSync(join(tmpdir(), "omi-capability-"));
    roots.push(root);
    const store = new SqliteAgentStore({ databasePath: join(root, "agent.sqlite"), reconcileOnOpen: false });
    const session = store.insertSession({
      ownerId: "owner-1",
      surfaceKind: "main_chat",
      defaultAdapterId: "pi-mono",
      executionRole: "coordinator",
    });
    const run = store.insertRun({
      sessionId: session.sessionId,
      clientId: "voice-client",
      requestId: "voice-request",
      status: "running",
      mode: "act",
      inputJson: JSON.stringify({
        metadata: { externalSurface: { authority: "swift_realtime", turnId: "turn-1" } },
      }),
    });
    const attempt = store.insertAttempt({
      runId: run.runId,
      attemptNo: 1,
      status: "running",
      adapterId: "pi-mono",
      adapterInstanceId: "worker",
    });
    const broker = createBroker(store);
    const capability = broker.register({
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
    });
    expect(capability.surfaceKind).toBe("realtime_voice");
    expect(capability.allowedToolNames).toContain("think_deeper");
    expect(capability.allowedToolNames).toContain("web_search");
    expect(capability.allowedToolNames).toContain("point_click");
    expect(capability.allowedToolNames).not.toContain("record_interject_feedback");
    const authorized = broker.authorize({
      capabilityRef: capability.capabilityRef,
      invocationId: "invoke-voice",
      runId: run.runId,
      attemptId: attempt.attemptId,
      activeOwnerId: session.ownerId,
      toolName: "web_search",
      toolInput: { query: "what's the weather in nyc right now?" },
    });
    expect(authorized.canonicalToolName).toBe("web_search");
    store.close();

    // A plain ACP chat run must not inherit voice-only tools. Typed desktop
    // chat advertises web_search through the pi-mono adapter, not this ACP fixture.
    const chat = fixture();
    const chatCapability = createBroker(chat.store).register({
      ownerId: chat.session.ownerId,
      sessionId: chat.session.sessionId,
      runId: chat.run.runId,
      attemptId: chat.attempt.attemptId,
    });
    expect(chatCapability.allowedToolNames).not.toContain("think_deeper");
    expect(chatCapability.allowedToolNames).not.toContain("web_search");
    expect(chatCapability.allowedToolNames).not.toContain("point_click");
    expect(chatCapability.allowedToolNames).not.toContain("record_interject_feedback");
    chat.store.close();
  });

  it("offers the realtime voice screenshot only to realtime voice runs", () => {
    const allowedFor = (surfaceKind: string) => {
      const root = mkdtempSync(join(tmpdir(), "omi-capability-"));
      roots.push(root);
      const store = new SqliteAgentStore({ databasePath: join(root, "agent.sqlite"), reconcileOnOpen: false });
      const voice = surfaceKind === "realtime_voice";
      const session = store.insertSession({
        ownerId: "owner-1",
        surfaceKind: voice ? "main_chat" : surfaceKind,
        defaultAdapterId: "pi-mono",
        executionRole: "coordinator",
      });
      const run = store.insertRun({
        sessionId: session.sessionId,
        clientId: "screen-client",
        requestId: `screen-${surfaceKind}`,
        status: "running",
        mode: "act",
        inputJson: JSON.stringify({
          prompt: "What is on my screen?",
          admittedContextSnapshot: { sourceOutcomes: [{ source: "screen", outcome: "available" }] },
          ...(voice ? { metadata: { externalSurface: { authority: "swift_realtime", turnId: "turn-1" } } } : {}),
        }),
      });
      const attempt = store.insertAttempt({
        runId: run.runId,
        attemptNo: 1,
        status: "running",
        adapterId: "pi-mono",
        adapterInstanceId: "worker",
      });
      const capability = createBroker(store).register({
        ownerId: session.ownerId,
        sessionId: session.sessionId,
        runId: run.runId,
        attemptId: attempt.attemptId,
      });
      store.close();
      return capability;
    };

    for (const surfaceKind of ["main_chat", "floating_bar", "floating_pill", "task_chat", "workstream"]) {
      const capability = allowedFor(surfaceKind);
      expect(capability.adapterId, surfaceKind).toBe("pi-mono");
      expect(capability.allowedToolNames, surfaceKind).toContain("capture_screen");
      expect(capability.allowedToolNames, surfaceKind).not.toContain("screenshot");
    }
    const voice = allowedFor("realtime_voice");
    expect(voice.surfaceKind).toBe("realtime_voice");
    expect(voice.allowedToolNames).toContain("screenshot");
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

describe("RunToolCapabilityBroker desktop tool approvals", () => {
  const sendInput = { to: "+15551234567", text: "Running late" };

  function parkedSend(
    options: Omit<ConstructorParameters<typeof RunToolCapabilityBroker>[0], "store" | "profileForSession"> = {},
  ) {
    const fx = fixture();
    const broker = createBroker(fx.store, options);
    const capability = broker.register({
      ownerId: fx.session.ownerId,
      sessionId: fx.session.sessionId,
      runId: fx.run.runId,
      attemptId: fx.attempt.attemptId,
    });
    const outcome = broker.authorizeRelayInvocationOrRequestApproval({
      capabilityRef: capability.capabilityRef,
      invocationId: "send-1",
      toolName: "send_message",
      toolInput: sendInput,
      activeOwnerId: fx.session.ownerId,
    });
    if (outcome.kind !== "approval_required") throw new Error("expected the send to park");
    return { ...fx, broker, capability, outcome };
  }

  function dispatchRow(store: SqliteAgentStore, dispatchId: string) {
    return store.getRow("SELECT * FROM desktop_dispatches WHERE dispatch_id = ?", [dispatchId]);
  }

  function counts(store: SqliteAgentStore) {
    return {
      dispatches: Number(store.getRow("SELECT COUNT(*) AS count FROM desktop_dispatches").count),
      ledger: Number(store.getRow("SELECT COUNT(*) AS count FROM tool_invocation_ledger").count),
    };
  }

  it("never lets the model name the resource a grant covers", () => {
    const { store, session, run, attempt } = fixture();
    const broker = createBroker(store);
    const capability = broker.register({
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
    });
    const send = (invocationId: string, toolInput: Record<string, unknown>) =>
      broker.authorizeRelayInvocationOrRequestApproval({
        capabilityRef: capability.capabilityRef,
        invocationId,
        toolName: "send_message",
        toolInput,
        activeOwnerId: session.ownerId,
      });

    // Reproduces the review finding: a smuggled resource_ref used to become
    // the grant pattern, so one approval covered any later recipient that
    // repeated the same ref. The manifest schema has no such field.
    expectCode(() => send("forged-ref", { to: "bob", text: "hi", resource_ref: "x" }), "invalid_tool_input");
    expectCode(() => send("missing-text", { to: "bob" }), "invalid_tool_input");
    expectCode(() => send("wrong-type", { to: "bob", text: 42 }), "invalid_tool_input");
    expect(counts(store)).toEqual({ dispatches: 0, ledger: 0 });

    // A session grant the user minted for bob covers bob and nobody else.
    store.insertGrant({
      sessionId: session.sessionId,
      runId: null,
      capability: "desktop.messaging.send",
      operation: "send_message",
      resourcePattern: "bob",
      effect: "allow",
      source: "user",
      expiresAtMs: Date.now() + 60_000,
    });
    expect(send("to-bob", { to: "bob", text: "hi" }).kind).toBe("authorized");
    const mallory = send("to-mallory", { to: "mallory", text: "hi" });
    expect(mallory.kind).toBe("approval_required");
    if (mallory.kind === "approval_required") expect(mallory.dispatch.resourceRef).toBe("mallory");
    store.close();
  });

  it("refuses to park an input the card cannot show in full", () => {
    const { store, session, run, attempt } = fixture();
    const broker = createBroker(store);
    const capability = broker.register({
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
    });

    expectCode(() => broker.authorizeRelayInvocationOrRequestApproval({
      capabilityRef: capability.capabilityRef,
      invocationId: "huge-script",
      toolName: "run_applescript",
      toolInput: { script: "display dialog \"hi\"\n".repeat(400) },
      activeOwnerId: session.ownerId,
    }), "input_too_large_to_approve");
    // Nothing was prepared: the model shortens the input and calls again.
    expect(counts(store)).toEqual({ dispatches: 0, ledger: 0 });
    store.close();
  });

  it("keeps a hard policy deny rejected instead of parking it", () => {
    const { store, session, run, attempt } = fixture();
    const broker = createBroker(store, {
      desktopToolPolicy: (request) => ({
        ...evaluateDesktopToolPolicy(request),
        decision: "deny",
        reason: "denied by test policy",
      }),
    });
    const capability = broker.register({
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
    });

    expectCode(() => broker.authorizeRelayInvocationOrRequestApproval({
      capabilityRef: capability.capabilityRef,
      invocationId: "denied",
      toolName: "send_message",
      toolInput: sendInput,
      activeOwnerId: session.ownerId,
    }), "approval_required");
    expect(counts(store)).toEqual({ dispatches: 0, ledger: 0 });
    store.close();
  });

  it("refuses an approval whose owner or attempt changed while the card was open", () => {
    const cancelled: unknown[] = [];
    const { store, session, run, attempt, broker, outcome } = parkedSend({
      onApprovalsCancelled: (closed) => cancelled.push(...closed),
    });
    const binding = toolApprovalInvocationBinding(outcome.dispatch)!;

    // Another owner cannot answer this card, and asking revokes the capability.
    expectCode(
      () => broker.assertApprovalAuthority({ dispatchId: outcome.dispatch.dispatchId, binding, activeOwnerId: "owner-2" }),
      "owner_mismatch",
    );
    expect(dispatchRow(store, outcome.dispatch.dispatchId)).toMatchObject({ status: "cancelled", resolved_by: "system" });
    expect(readToolInvocation(store, "send-1")).toMatchObject({ status: "failed", errorCode: "run_tool_owner_changed" });
    expect(cancelled).toEqual([{
      dispatchId: outcome.dispatch.dispatchId,
      invocationId: "send-1",
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
      reason: "owner_changed",
    }]);
    expectCode(
      () => broker.approveInvocation({ dispatchId: outcome.dispatch.dispatchId, binding, activeOwnerId: session.ownerId }),
      "capability_revoked",
    );
    store.close();
  });

  it("refuses an approval once its attempt is no longer the live one", () => {
    const { store, session, run, attempt, broker, outcome } = parkedSend();
    const binding = toolApprovalInvocationBinding(outcome.dispatch)!;
    store.execute("UPDATE run_attempts SET status = 'failed' WHERE attempt_id = ?", [attempt.attemptId]);
    store.insertAttempt({ runId: run.runId, attemptNo: 2, status: "running", adapterId: "acp", adapterInstanceId: "worker-2" });

    expectCode(
      () => broker.approveInvocation({ dispatchId: outcome.dispatch.dispatchId, binding, activeOwnerId: session.ownerId }),
      "attempt_terminal",
    );
    expect(dispatchRow(store, outcome.dispatch.dispatchId).status).toBe("cancelled");
    expect(readToolInvocation(store, "send-1").status).toBe("failed");
    store.close();
  });

  it("reports the approvals it closes on owner revocation", () => {
    const cancelled: unknown[] = [];
    const { store, session, run, broker, outcome } = parkedSend({
      onApprovalsCancelled: (closed) => cancelled.push(...closed),
    });

    expect(broker.revokeForOwner(session.ownerId)).toBe(1);

    expect(cancelled).toEqual([expect.objectContaining({ dispatchId: outcome.dispatch.dispatchId, reason: "owner_changed" })]);
    expect(dispatchRow(store, outcome.dispatch.dispatchId).status).toBe("cancelled");
    expect(broker.hasPendingApprovals(run.runId)).toBe(false);
    store.close();
  });

  it("restores a released approval when the surrounding transaction rolls back", () => {
    const { store, session, run, broker, outcome } = parkedSend();
    const binding = toolApprovalInvocationBinding(outcome.dispatch)!;

    const { released } = broker.approveInvocation({ dispatchId: outcome.dispatch.dispatchId, binding, activeOwnerId: session.ownerId });
    expect(broker.hasPendingApprovals(run.runId)).toBe(false);

    broker.restorePendingApproval(released);

    expect(broker.hasPendingApprovals(run.runId)).toBe(true);
    expectCode(() => broker.markInvocationDispatched(outcome.invocation), "approval_required");
    const again = broker.approveInvocation({ dispatchId: outcome.dispatch.dispatchId, binding, activeOwnerId: session.ownerId });
    expect(again.record.invocationId).toBe("send-1");
    store.close();
  });

  it("parks a sensitive send behind one approval dispatch bound to the prepared invocation", () => {
    const { store, session, run, attempt, broker, outcome } = parkedSend({ nowMs: () => 5_000 });
    const { invocation, dispatch, request } = outcome;

    expect(invocation.canonicalToolName).toBe("send_message");
    expect(readToolInvocation(store, "send-1")).toMatchObject({ status: "prepared", toolName: "send_message" });
    expect(dispatch).toMatchObject({
      kind: "approval",
      status: "pending",
      ownerId: session.ownerId,
      sourceSessionId: session.sessionId,
      sourceRunId: run.runId,
      sourceAttemptId: attempt.attemptId,
      capability: "desktop.messaging.send",
      operation: "send_message",
      resourceRef: "+15551234567",
      recommendedDefault: "deny",
      expiresAtMs: 5_000 + request.expiresAtMs - request.requestedAtMs,
    });
    expect(toolApprovalInvocationBinding(dispatch)).toMatchObject({
      invocationId: "send-1",
      toolName: "send_message",
      inputHash: invocation.inputHash,
      daemonBootEpoch: broker.daemonBootEpoch,
    });
    expect(JSON.parse(dispatch.payloadJson).preview).toEqual(sendInput);
    expect(broker.hasPendingApprovals(run.runId)).toBe(true);

    // Possession of the invocation object is not authority to dispatch it.
    expectCode(() => broker.markInvocationDispatched(invocation), "approval_required");
    expectCode(() => broker.acquireExecutionLease(invocation, () => session.ownerId), "approval_required");
    expect(readToolInvocation(store, "send-1").status).toBe("prepared");
    store.close();
  });

  it("admits exactly the approved invocation once and nothing else", () => {
    const { store, session, run, broker, outcome } = parkedSend();
    const binding = toolApprovalInvocationBinding(outcome.dispatch)!;
    store.resolveDesktopDispatch(outcome.dispatch.dispatchId, {
      ownerId: session.ownerId,
      status: "resolved",
      resolvedBy: "user",
      resolutionJson: JSON.stringify({ decision: "allow" }),
    });

    const { record } = broker.approveInvocation({ dispatchId: outcome.dispatch.dispatchId, binding, activeOwnerId: session.ownerId });
    expect(record).toMatchObject({ invocationId: "send-1", status: "prepared" });
    expect(broker.hasPendingApprovals(run.runId)).toBe(false);
    broker.markInvocationDispatched(outcome.invocation);
    expect(readToolInvocation(store, "send-1").status).toBe("dispatched");

    // The same dispatch cannot admit anything a second time, and a fresh
    // identical call is a new invocation that has to ask again.
    expectCode(
      () => broker.approveInvocation({ dispatchId: outcome.dispatch.dispatchId, binding, activeOwnerId: session.ownerId }),
      "capability_revoked",
    );
    const again = broker.authorizeRelayInvocationOrRequestApproval({
      capabilityRef: outcome.invocation.capabilityRef,
      invocationId: "send-2",
      toolName: "send_message",
      toolInput: sendInput,
      activeOwnerId: session.ownerId,
    });
    expect(again.kind).toBe("approval_required");
    expect(store.getRow("SELECT COUNT(*) AS count FROM grants").count).toBe(0);
    store.close();
  });

  it("rejects an approval whose binding no longer matches the prepared invocation", () => {
    const { store, session, broker, outcome } = parkedSend();
    const binding = toolApprovalInvocationBinding(outcome.dispatch)!;

    expectCode(
      () => broker.approveInvocation({
        dispatchId: outcome.dispatch.dispatchId,
        binding: { ...binding, inputHash: "sha256:tampered" },
        activeOwnerId: session.ownerId,
      }),
      "invocation_replayed",
    );
    expectCode(
      () => broker.approveInvocation({ dispatchId: "disp_unknown", binding, activeOwnerId: session.ownerId }),
      "capability_revoked",
    );
    // A failed approval leaves the invocation parked, not admitted.
    expectCode(() => broker.markInvocationDispatched(outcome.invocation), "approval_required");
    expect(readToolInvocation(store, "send-1").status).toBe("prepared");
    store.close();
  });

  it("fails a denied or expired invocation closed without ever dispatching it", () => {
    const { store, session, run, broker, outcome } = parkedSend();
    const binding = toolApprovalInvocationBinding(outcome.dispatch)!;

    const denied = broker.denyInvocation({ dispatchId: outcome.dispatch.dispatchId, binding, code: "approval_denied" }).record;
    expect(denied).toMatchObject({ status: "failed", errorCode: "approval_denied", dispatchedAtMs: null });
    expect(broker.hasPendingApprovals(run.runId)).toBe(false);
    // The ledger row is terminal, so the dispatch transition has no prepared tuple to claim.
    expect(() => broker.markInvocationDispatched(outcome.invocation)).toThrow("stale or already dispatched");
    expect(readToolInvocation(store, "send-1").status).toBe("failed");

    // Denial does not poison the capability: the next sensitive call asks again.
    const next = broker.authorizeRelayInvocationOrRequestApproval({
      capabilityRef: outcome.invocation.capabilityRef,
      invocationId: "send-3",
      toolName: "send_message",
      toolInput: sendInput,
      activeOwnerId: session.ownerId,
    });
    expect(next.kind).toBe("approval_required");
    store.close();
  });

  it("skips the dispatch when a covering scoped grant already exists", () => {
    const { store, session, run, attempt } = fixture();
    const broker = createBroker(store, { nowMs: () => 10_000 });
    const capability = broker.register({
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
    });
    store.insertGrant({
      sessionId: session.sessionId,
      runId: null,
      capability: "desktop.messaging.send",
      operation: "send_message",
      resourcePattern: "+15551234567",
      effect: "allow",
      source: "user",
      expiresAtMs: 20_000,
    });

    const covered = broker.authorizeRelayInvocationOrRequestApproval({
      capabilityRef: capability.capabilityRef,
      invocationId: "send-covered",
      toolName: "send_message",
      toolInput: sendInput,
      activeOwnerId: session.ownerId,
    });
    const otherRecipient = broker.authorizeRelayInvocationOrRequestApproval({
      capabilityRef: capability.capabilityRef,
      invocationId: "send-other",
      toolName: "send_message",
      toolInput: { ...sendInput, to: "+15550000000" },
      activeOwnerId: session.ownerId,
    });

    expect(covered.kind).toBe("authorized");
    expect(otherRecipient.kind).toBe("approval_required");
    expect(store.getRow("SELECT COUNT(*) AS count FROM desktop_dispatches").count).toBe(1);
    store.close();
  });

  it("gives list tools a stable resource so a session grant can name them", () => {
    const { store, session, run, attempt } = fixture();
    const broker = createBroker(store);
    const capability = broker.register({
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
    });
    const parked = broker.authorizeRelayInvocationOrRequestApproval({
      capabilityRef: capability.capabilityRef,
      invocationId: "mail-1",
      toolName: "list_mail_messages",
      toolInput: { limit: 10 },
      activeOwnerId: session.ownerId,
    });
    if (parked.kind !== "approval_required") throw new Error("expected mail read to park");
    expect(parked.dispatch.resourceRef).toBe("mail:inbox");

    store.insertGrant({
      sessionId: session.sessionId,
      runId: null,
      capability: "desktop.mail.read",
      operation: "list_mail_messages",
      resourcePattern: "mail:inbox",
      effect: "allow",
      source: "user",
      expiresAtMs: Date.now() + 60_000,
    });
    const covered = broker.authorizeRelayInvocationOrRequestApproval({
      capabilityRef: capability.capabilityRef,
      invocationId: "mail-2",
      toolName: "list_mail_messages",
      toolInput: { limit: 10 },
      activeOwnerId: session.ownerId,
    });
    expect(covered.kind).toBe("authorized");
    store.close();
  });

  it("parks every live screenshot behind its own Allow Once card, and no grant covers the next one", () => {
    const { store, session, run, attempt } = fixture();
    store.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", [
      JSON.stringify({
        prompt: "What is on my screen?",
        admittedContextSnapshot: { sourceOutcomes: [{ source: "screen", outcome: "available" }] },
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
    const capture = (invocationId: string) => broker.authorizeRelayInvocationOrRequestApproval({
      capabilityRef: capability.capabilityRef,
      invocationId,
      toolName: "capture_screen",
      toolInput: {},
      activeOwnerId: session.ownerId,
    });

    const parked = capture("screen-1");
    if (parked.kind !== "approval_required") throw new Error("expected the screenshot to park");
    expect(readToolInvocation(store, "screen-1").status).toBe("prepared");
    expect(parked.dispatch).toMatchObject({
      kind: "approval",
      status: "pending",
      capability: "desktop.context.screenshot_image",
      operation: "capture_screen",
      resourceRef: "screen",
    });
    expect(parked.request.title).toBe("Take a screenshot");
    expect(parked.request.options.map((option) => option.id)).toEqual(["allow_once", "deny"]);
    expectCode(() => broker.markInvocationDispatched(parked.invocation), "approval_required");

    store.insertGrant({
      sessionId: session.sessionId,
      runId: null,
      capability: "desktop.context.screenshot_image",
      operation: "capture_screen",
      resourcePattern: "screen",
      effect: "allow",
      source: "user",
      expiresAtMs: Date.now() + 60_000,
    });
    // Even a well-formed grant row for exactly this resource does not cover a capture.
    expect(capture("screen-2").kind).toBe("approval_required");
    store.close();
  });

  describe("ui_snapshot", () => {
    function snapshotBroker() {
      const fx = fixture();
      const broker = createBroker(fx.store);
      const capability = broker.register({
        ownerId: fx.session.ownerId,
        sessionId: fx.session.sessionId,
        runId: fx.run.runId,
        attemptId: fx.attempt.attemptId,
      });
      const snapshot = (invocationId: string, toolInput: Record<string, unknown>) =>
        broker.authorizeRelayInvocationOrRequestApproval({
          capabilityRef: capability.capabilityRef,
          invocationId,
          toolName: "ui_snapshot",
          toolInput,
          activeOwnerId: fx.session.ownerId,
        });
      return { ...fx, broker, capability, snapshot };
    }

    it("parks behind an observe approval scoped to the lowercased app", () => {
      const { store, capability, snapshot } = snapshotBroker();
      expect(capability.allowedToolNames).toContain("ui_snapshot");

      const parked = snapshot("snap-1", { bundle_id: " com.apple.TextEdit ", window_title: "Untitled" });

      if (parked.kind !== "approval_required") throw new Error("expected the snapshot to park");
      expect(parked.dispatch).toMatchObject({
        capability: "desktop.automation.observe",
        operation: "ui_snapshot",
        resourceRef: "com.apple.textedit",
      });
      expect(parked.invocation.effectClass).toBe("read_only");
      expect(parked.invocation.retryPolicy).toBe("safe_retry");
      expect(parked.request.options.map((option) => option.id)).toEqual(["allow_once", "allow_session", "deny"]);
      store.close();
    });

    it("lets a session grant for one app run its next snapshot without a card while another app still asks", () => {
      const { store, session, snapshot } = snapshotBroker();
      store.insertGrant({
        sessionId: session.sessionId,
        runId: null,
        capability: "desktop.automation.observe",
        operation: "ui_snapshot",
        resourcePattern: "com.apple.textedit",
        effect: "allow",
        source: "user",
        expiresAtMs: Date.now() + 60_000,
      });

      expect(snapshot("textedit", { bundle_id: "com.apple.TextEdit" }).kind).toBe("authorized");
      const notes = snapshot("notes", { bundle_id: "com.apple.Notes" });
      expect(notes.kind).toBe("approval_required");
      if (notes.kind === "approval_required") expect(notes.dispatch.resourceRef).toBe("com.apple.notes");
      store.close();
    });

    it("does not let a wildcard or act grant cover an app", () => {
      const { store, session, snapshot } = snapshotBroker();
      for (const [capability, resourcePattern] of [
        ["desktop.automation.observe", "*"],
        ["desktop.automation.act", "com.apple.textedit"],
      ] as const) {
        store.insertGrant({
          sessionId: session.sessionId,
          runId: null,
          capability,
          operation: "ui_snapshot",
          resourcePattern,
          effect: "allow",
          source: "user",
          expiresAtMs: Date.now() + 60_000,
        });
      }

      expect(snapshot("textedit", { bundle_id: "com.apple.TextEdit" }).kind).toBe("approval_required");
      store.close();
    });

    it("rejects a refused app without writing a dispatch or a ledger row", () => {
      const { store, snapshot } = snapshotBroker();

      expectCode(() => snapshot("terminal", { bundle_id: "com.apple.Terminal" }), "approval_required");
      expectCode(() => snapshot("omi", { bundle_id: "com.omi.computer-macos" }), "approval_required");
      expectCode(() => snapshot("malformed", { bundle_id: "Terminal" }), "approval_required");
      expect(counts(store)).toEqual({ dispatches: 0, ledger: 0 });
      store.close();
    });

    it("holds the input to the manifest schema", () => {
      const { store, snapshot } = snapshotBroker();

      expectCode(() => snapshot("by-name", { bundle_id: "com.apple.TextEdit", app_name: "TextEdit" }), "invalid_tool_input");
      expectCode(() => snapshot("no-app", { window_title: "Untitled" }), "invalid_tool_input");
      expectCode(() => snapshot("empty", { bundle_id: "" }), "invalid_tool_input");
      expect(counts(store)).toEqual({ dispatches: 0, ledger: 0 });
      store.close();
    });
  });

  it("closes the pending dispatch when the attempt ends before the user answers", () => {
    const cancelled: unknown[] = [];
    const { store, session, run, attempt, broker, outcome } = parkedSend({
      onApprovalsCancelled: (closed) => cancelled.push(...closed),
    });

    broker.handleKernelEvent({
      eventId: "evt_terminal",
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
      type: "attempt.cancelled",
      retentionClass: "core",
      visibility: "ui",
      payloadJson: "{}",
      createdAtMs: Date.now(),
    });

    expect(cancelled).toEqual([{
      dispatchId: outcome.dispatch.dispatchId,
      invocationId: "send-1",
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
      reason: "attempt_terminal",
    }]);
    expect(dispatchRow(store, outcome.dispatch.dispatchId)).toMatchObject({ status: "cancelled", resolved_by: "system" });
    expect(readToolInvocation(store, "send-1")).toMatchObject({ status: "failed", errorCode: "run_tool_attempt_terminal" });
    expect(() => store.resolveDesktopDispatch(outcome.dispatch.dispatchId, {
      ownerId: session.ownerId,
      status: "resolved",
      resolutionJson: JSON.stringify({ decision: "allow" }),
    })).toThrow("not pending");
    store.close();
  });

  it("never replays a parked invocation across a daemon restart", () => {
    const { databasePath, store, session, run, outcome } = parkedSend({ daemonBootEpoch: "boot-before" });
    expect(readToolInvocation(store, "send-1").status).toBe("prepared");
    store.close();

    const reopened = new SqliteAgentStore({ databasePath });
    expect(readToolInvocation(reopened, "send-1")).toMatchObject({
      status: "failed",
      errorCode: "daemon_restart_before_dispatch",
      retryPolicy: "never_auto_retry",
    });
    expect(dispatchRow(reopened, outcome.dispatch.dispatchId)).toMatchObject({
      status: "expired",
      resolved_by: "daemon_startup_reconciliation",
    });
    const resolved = reopened.allRows(
      "SELECT payload_json FROM events WHERE type = 'approval.resolved' AND run_id = ?",
      [run.runId],
    );
    expect(resolved).toHaveLength(1);
    expect(JSON.parse(String(resolved[0]!.payload_json))).toMatchObject({
      approvalId: outcome.dispatch.dispatchId,
      invocationId: "send-1",
      decision: "expired",
      automatic: true,
    });
    // A user answer that arrives after the restart finds nothing to admit.
    expect(() => reopened.resolveDesktopDispatch(outcome.dispatch.dispatchId, {
      ownerId: session.ownerId,
      status: "resolved",
      resolutionJson: JSON.stringify({ decision: "allow" }),
    })).toThrow("not pending");

    // Reconciliation is idempotent: a second open records nothing new.
    expect(reopened.reconcileStartup().expiredToolApprovalDispatchIds).toEqual([]);
    expect(reopened.getRow("SELECT COUNT(*) AS count FROM events WHERE type = 'approval.resolved'").count).toBe(1);
    reopened.close();
  });
});

describe("desktop approval set and sensitive policy bundles", () => {
  /**
   * Relay-callable tools the policy classifies into a sensitive bundle that
   * deliberately do not park behind the approval card. Each entry says why;
   * a sensitive tool neither gated nor justified here fails the test.
   */
  const UNGATED_SENSITIVE_TOOLS: Record<string, string> = {
    // The macOS permission prompt is itself the approval, and Swift already
    // requires the person's current-turn consent before it opens.
    request_permission: "native prompt plus current-turn consent",
    // Scope: not one of the on-device tools issue #20938 gates. Safeguard: it
    // only types into a Claude or ChatGPT "add custom connector" form that is
    // already open in the person's signed-in browser. Risk it keeps: it takes
    // an arbitrary server_url and can press the form's submit button.
    fill_cloud_connector_form: "outside #20938's device tools; needs the connector form already open",
  };

  function relayCallable(toolName: string): boolean {
    const tool = allOmiToolManifest.find((entry) => entry.name === toolName);
    return Boolean(tool?.adapters["pi-mono"]?.advertised || tool?.adapters["omi-tools-stdio"]?.advertised);
  }

  function sensitiveBundles(toolName: string): string[] {
    const descriptor = desktopToolPolicyInternals.descriptorFromToolName(toolName);
    return (descriptor?.bundles ?? []).filter(desktopToolPolicyInternals.isSensitiveBundle);
  }

  const relayTools = [...new Set(allOmiToolManifest.map((tool) => tool.name))].filter(relayCallable);

  it("classifies every relay-callable tool on purpose, never by the read-only default", () => {
    const unclassified = relayTools.filter((name) => !desktopToolPolicyInternals.isExplicitlyClassified(name));
    expect(unclassified).toEqual([]);
  });

  it("parks every relay-callable tool in a sensitive bundle, save the justified exceptions", () => {
    const sensitive = relayTools.filter((name) => sensitiveBundles(name).length > 0);
    expect(sensitive).toContain("capture_screen");
    const ungated = sensitive.filter((name) => !DESKTOP_APPROVAL_TOOLS.has(name)).sort();
    expect(ungated).toEqual(Object.keys(UNGATED_SENSITIVE_TOOLS).sort());
  });

  it("keeps screen-image tools that are not gated off every chat relay", () => {
    for (const name of ["get_screenshot", "screenshot"]) {
      expect(sensitiveBundles(name), name).toEqual(["desktop.context.screenshot_image"]);
      expect(relayCallable(name), name).toBe(false);
    }
  });

  it("classifies show_rewind_evidence as stored-frame text, not pixels for the model", () => {
    expect(desktopToolPolicyInternals.descriptorFromToolName("show_rewind_evidence")?.bundles)
      .toEqual(["desktop.context.screen_summary"]);
  });

  it("keeps every gated tool sensitive and relay-callable, and the local-only exception off the relays", () => {
    for (const name of DESKTOP_APPROVAL_TOOLS) {
      expect(sensitiveBundles(name), name).not.toEqual([]);
      expect(relayCallable(name), name).toBe(true);
    }
    expect(relayCallable("get_screenshot")).toBe(false);
  });

  it("gives every gated tool the long model-side wait so a person has time to answer the card", () => {
    for (const name of DESKTOP_APPROVAL_TOOLS) {
      expect(allOmiToolManifest.find((tool) => tool.name === name)?.timeoutClass, name).toBe("long");
    }
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

describe("RunToolCapabilityBroker JIT knowledge-ledger gate", () => {
  const LEDGER_TOOLS = [
    "search_knowledge",
    "read_playbook",
    "search_historical_facts",
    "get_entity_timeline_tool",
    "save_playbook",
    "create_standing_trigger",
    "close_fact",
  ];

  it("keeps the ledger tools out of the authorized allowlist by default", () => {
    const { store, session, run, attempt } = fixture("coordinator");
    const broker = createBroker(store);
    const capability = broker.register({
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
    });

    for (const toolName of LEDGER_TOOLS) {
      expect(capability.allowedToolNames, toolName).not.toContain(toolName);
    }
    expectCode(
      () => broker.authorize({
        capabilityRef: capability.capabilityRef,
        invocationId: "ledger-gate-off-1",
        runId: run.runId,
        attemptId: attempt.attemptId,
        activeOwnerId: session.ownerId,
        toolName: "search_knowledge",
        toolInput: { query: "release checklist" },
      }),
      "tool_not_allowed",
    );
    store.close();
  });

  it("authorizes the ledger tools once the run's admitted metadata carries the JIT gate", () => {
    const { store, session, run, attempt } = fixture("coordinator");
    store.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", [
      JSON.stringify({ prompt: "save a playbook", metadata: { jitKnowledgeToolsEnabled: true } }),
      run.runId,
    ]);
    const broker = createBroker(store);
    const capability = broker.register({
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
    });

    for (const toolName of LEDGER_TOOLS) {
      expect(capability.allowedToolNames, toolName).toContain(toolName);
    }
    const authorized = broker.authorize({
      capabilityRef: capability.capabilityRef,
      invocationId: "ledger-gate-on-1",
      runId: run.runId,
      attemptId: attempt.attemptId,
      activeOwnerId: session.ownerId,
      toolName: "search_knowledge",
      toolInput: { query: "release checklist" },
    });
    expect(authorized.canonicalToolName).toBe("search_knowledge");
    store.close();
  });

  it("narrows an admitted service JIT run to read-only ledger retrieval", () => {
    const { store, session, run, attempt } = fixture("coordinator", "ask", "service");
    store.execute("UPDATE runs SET input_json = ? WHERE run_id = ?", [
      JSON.stringify({
        prompt: "ground this notification",
        metadata: {
          jitKnowledgeToolsEnabled: true,
          jitBudget: {
            contractVersion: "jit-cloud-qa-v1",
            executionID: "execution-1",
            maxProviderAttempts: 3,
            maxOutputTokensPerAttempt: 2048,
            maxNormalizedInputTokensPerAttempt: 32768,
            maxEstimatedSpendMicroUSD: 50000,
          },
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

    expect(capability.allowedToolNames).toEqual([
      "get_entity_timeline_tool",
      "read_playbook",
      "search_historical_facts",
      "search_knowledge",
    ]);
    expectCode(
      () => broker.authorize({
        capabilityRef: capability.capabilityRef,
        invocationId: "jit-service-write-1",
        runId: run.runId,
        attemptId: attempt.attemptId,
        activeOwnerId: session.ownerId,
        toolName: "save_playbook",
        toolInput: { description: "not admitted", body: "not admitted" },
      }),
      "tool_not_allowed",
    );
    store.close();
  });
});
