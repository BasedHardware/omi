import { describe, expect, it, vi } from "vitest";
import {
  askUser,
  createKernelElicitationResolver,
  outcomeFromResolution,
} from "../src/runtime/desktop-elicitation-resolver.js";
import { normalizeAcpPermission, normalizeAskUser } from "../src/runtime/desktop-elicitation.js";
import type { AgentEvent } from "../src/runtime/types.js";

const permissionRequest = normalizeAcpPermission({
  adapterId: "hermes",
  agentLabel: "Hermes",
  params: {
    sessionId: "native-1",
    toolCall: { toolCallId: "t1", title: "Write a file", kind: "edit" },
    options: [
      { optionId: "once", name: "Allow once", kind: "allow_once" },
      { optionId: "no", name: "Deny", kind: "reject_once" },
    ],
  },
})!;

const [questionRequest] = normalizeAskUser({
  adapterId: "acp",
  agentLabel: "Omi",
  args: { questions: [{ question: "Which branch?", options: ["main"] }] },
});

function kernelStub(overrides: Record<string, unknown> = {}) {
  const subscribers: Array<(event: AgentEvent) => void> = [];
  const created: Array<Record<string, unknown>> = [];
  const kernel = {
    createDesktopDispatch: vi.fn((input: Record<string, unknown>) => {
      created.push(input);
      return { dispatchId: "disp-1", ...input } as any;
    }),
    sessionForAdapterNativeSession: vi.fn(() => ({
      sessionId: "sess-1",
      ownerId: "owner-1",
      runId: "run-1",
    })),
    subscribe: vi.fn((subscriber: (event: AgentEvent) => void) => {
      subscribers.push(subscriber);
      return () => {
        const index = subscribers.indexOf(subscriber);
        if (index >= 0) subscribers.splice(index, 1);
      };
    }),
    ...overrides,
  };

  const emitResolution = (payload: Record<string, unknown>, type = "approval.resolved") => {
    const event = {
      eventId: "evt-1",
      sessionId: "sess-1",
      runId: "run-1",
      attemptId: null,
      type,
      retentionClass: "standard",
      visibility: "internal",
      payloadJson: JSON.stringify(payload),
      createdAtMs: 0,
    } as unknown as AgentEvent;
    for (const subscriber of [...subscribers]) subscriber(event);
  };

  const emitRunEvent = (type: string, runId: string) => {
    const event = {
      eventId: "evt-run", sessionId: "sess-1", runId, attemptId: null, type,
      retentionClass: "standard", visibility: "internal", payloadJson: "{}", createdAtMs: 0,
    } as unknown as AgentEvent;
    for (const subscriber of [...subscribers]) subscriber(event);
  };

  return { kernel, created, emitResolution, emitRunEvent, subscriberCount: () => subscribers.length };
}

describe("elicitation dispatch creation", () => {
  it("records a pending approval bound to the kernel session, with no expiry", async () => {
    const stub = kernelStub();
    const resolver = createKernelElicitationResolver({ kernel: stub.kernel as any, log: () => {} });

    const pending = resolver(permissionRequest);
    await Promise.resolve();

    expect(stub.kernel.sessionForAdapterNativeSession).toHaveBeenCalledWith("hermes", "native-1");
    expect(stub.created[0]).toMatchObject({
      ownerId: "owner-1",
      kind: "approval",
      sourceSessionId: "sess-1",
      sourceRunId: "run-1",
      title: "Hermes needs permission",
      decisionPrompt: "Write a file",
      expiresAtMs: null,
    });

    stub.emitResolution({ dispatchId: "disp-1", status: "resolved", resolution: { optionId: "once" } });
    await expect(pending).resolves.toEqual({ kind: "selected", optionIds: ["once"] });
  });

  it("records a question as a routing_choice carrying its options", async () => {
    const stub = kernelStub();
    const resolver = createKernelElicitationResolver({ kernel: stub.kernel as any, log: () => {} });

    const pending = resolver({ ...questionRequest, externalSessionId: "native-1" });
    await Promise.resolve();

    expect(stub.created[0]).toMatchObject({ kind: "routing_choice" });
    expect(JSON.parse(stub.created[0].payloadJson as string)).toMatchObject({
      mode: "question",
      allowsFreeText: true,
      options: [{ optionId: "main", label: "main", effect: "choice" }],
    });

    stub.emitResolution({ dispatchId: "disp-1", status: "resolved", resolution: { optionId: "main" } });
    await pending;
  });

  it("stops listening once its own dispatch resolves", async () => {
    const stub = kernelStub();
    const resolver = createKernelElicitationResolver({ kernel: stub.kernel as any, log: () => {} });

    const pending = resolver(permissionRequest);
    await Promise.resolve();
    expect(stub.subscriberCount()).toBe(1);

    stub.emitResolution({ dispatchId: "disp-1", status: "resolved", resolution: { optionId: "no" } });
    await pending;
    expect(stub.subscriberCount()).toBe(0);
  });

  it("ignores resolutions belonging to other dispatches", async () => {
    const stub = kernelStub();
    const resolver = createKernelElicitationResolver({ kernel: stub.kernel as any, log: () => {} });

    let settled = false;
    const pending = resolver(permissionRequest).then((outcome) => {
      settled = true;
      return outcome;
    });
    await Promise.resolve();

    stub.emitResolution({ dispatchId: "disp-other", status: "resolved", resolution: { optionId: "once" } });
    stub.emitResolution({ dispatchId: "disp-1", status: "resolved" }, "run.completed");
    await Promise.resolve();
    expect(settled).toBe(false);

    stub.emitResolution({ dispatchId: "disp-1", status: "resolved", resolution: { optionId: "once" } });
    await expect(pending).resolves.toEqual({ kind: "selected", optionIds: ["once"] });
  });
});

describe("the surface is told when a question starts and stops waiting", () => {
  function notifierSpy() {
    const pending: Array<Record<string, unknown>> = [];
    const resolved: Array<Record<string, unknown>> = [];
    return {
      notifier: {
        pending: (input: any) => pending.push(input),
        resolved: (input: any) => resolved.push(input),
      },
      pending,
      resolved,
    };
  }

  it("announces the pending question with everything the card needs", async () => {
    const stub = kernelStub();
    const spy = notifierSpy();
    const resolver = createKernelElicitationResolver({
      kernel: stub.kernel as any,
      notifier: spy.notifier,
      log: () => {},
    });

    const promise = resolver(permissionRequest);
    await Promise.resolve();

    expect(spy.pending).toHaveLength(1);
    expect(spy.pending[0]).toMatchObject({
      dispatchId: "disp-1",
      ownerId: "owner-1",
      sessionId: "sess-1",
      runId: "run-1",
    });
    expect((spy.pending[0] as any).request).toMatchObject({
      mode: "permission",
      allowsFreeText: false,
    });

    stub.emitResolution({ dispatchId: "disp-1", status: "resolved", resolution: { optionId: "once" } });
    await promise;
    expect(spy.resolved).toEqual([
      { dispatchId: "disp-1", ownerId: "owner-1", outcome: "answered" },
    ]);
  });

  it("announces resolution on a cancellation too, so no card outlives its question", async () => {
    const stub = kernelStub();
    const spy = notifierSpy();
    const resolver = createKernelElicitationResolver({
      kernel: stub.kernel as any,
      notifier: spy.notifier,
      log: () => {},
    });

    const promise = resolver(permissionRequest);
    await Promise.resolve();
    stub.emitResolution({ dispatchId: "disp-1", status: "cancelled" });
    await promise;

    expect(spy.resolved).toEqual([
      { dispatchId: "disp-1", ownerId: "owner-1", outcome: "cancelled" },
    ]);
  });

  it("announces nothing when it never reached a person", async () => {
    const stub = kernelStub({ sessionForAdapterNativeSession: vi.fn(() => null) });
    const spy = notifierSpy();
    const resolver = createKernelElicitationResolver({
      kernel: stub.kernel as any,
      notifier: spy.notifier,
      log: () => {},
    });

    await resolver(permissionRequest);

    expect(spy.pending).toEqual([]);
    expect(spy.resolved).toEqual([]);
  });
});

describe("elicitation fails closed when no person is reachable", () => {
  it("denies when the adapter session has no kernel binding", async () => {
    const stub = kernelStub({ sessionForAdapterNativeSession: vi.fn(() => null) });
    const resolver = createKernelElicitationResolver({ kernel: stub.kernel as any, log: () => {} });

    await expect(resolver(permissionRequest)).resolves.toEqual({ kind: "selected", optionIds: ["no"] });
    expect(stub.kernel.createDesktopDispatch).not.toHaveBeenCalled();
  });

  it("denies when the request carries no adapter session at all", async () => {
    const stub = kernelStub();
    const resolver = createKernelElicitationResolver({ kernel: stub.kernel as any, log: () => {} });

    await expect(
      resolver({ ...permissionRequest, externalSessionId: null }),
    ).resolves.toEqual({ kind: "selected", optionIds: ["no"] });
  });

  it("denies when the dispatch cannot be recorded", async () => {
    const stub = kernelStub({
      createDesktopDispatch: vi.fn(() => { throw new Error("store is closed"); }),
    });
    const resolver = createKernelElicitationResolver({ kernel: stub.kernel as any, log: () => {} });

    await expect(resolver(permissionRequest)).resolves.toEqual({ kind: "selected", optionIds: ["no"] });
  });
});

describe("resolution mapping", () => {
  it("accepts only an option the agent actually offered", () => {
    expect(outcomeFromResolution(permissionRequest, "resolved", { optionId: "once" }))
      .toEqual({ kind: "selected", optionIds: ["once"] });
    expect(outcomeFromResolution(permissionRequest, "resolved", { optionId: "smuggled" }))
      .toMatchObject({ kind: "cancelled" });
  });

  it("refuses typed text on a permission, where the protocol has no field for it", () => {
    expect(outcomeFromResolution(permissionRequest, "resolved", { text: "go ahead" }))
      .toMatchObject({ kind: "cancelled" });
  });

  it("accepts typed text on a question that allows it", () => {
    expect(outcomeFromResolution(questionRequest, "resolved", { text: "release/0.12" }))
      .toEqual({ kind: "answered", text: "release/0.12" });
    expect(outcomeFromResolution(questionRequest, "resolved", { text: "   " }))
      .toMatchObject({ kind: "cancelled" });
  });

  it("treats any non-resolved status as a cancellation", () => {
    expect(outcomeFromResolution(permissionRequest, "cancelled", null))
      .toEqual({ kind: "cancelled", reason: "cancelled" });
    expect(outcomeFromResolution(permissionRequest, "expired", null))
      .toEqual({ kind: "cancelled", reason: "expired" });
  });
});

describe("the surface and the runtime agree on the answer's shape", () => {
  it("round-trips exactly what the card sends", async () => {
    const { elicitationResolution } = await import(
      "../src/runtime/desktop-elicitation-resolver.js"
    );
    const [question] = normalizeAskUser({
      adapterId: "acp",
      agentLabel: "Omi",
      args: {
        questions: [{ question: "Constraints?", options: ["a", "b"], allow_multiple: true }],
      },
    });

    // These are the exact keys ElicitationWire.resolvePayload puts on the wire.
    // They drifted once -- the card sent optionIds while the runtime read
    // optionId -- and every answer was recorded empty.
    const stored = elicitationResolution({ optionIds: ["a", "b"], text: "and this" });
    expect(outcomeFromResolution(question, "resolved", stored))
      .toEqual({ kind: "selected", optionIds: ["a", "b"], text: "and this" });

    const cancelled = elicitationResolution({});
    expect(outcomeFromResolution(question, "resolved", cancelled))
      .toMatchObject({ kind: "cancelled" });
  });
});

describe("a question does not outlive its run", () => {
  it("releases the card when the run it belongs to ends", async () => {
    const stub = kernelStub();
    const resolved: string[] = [];
    const promise = askUser(
      {
        kernel: stub.kernel as any,
        log: () => {},
        notifier: { pending: () => {}, resolved: (i: any) => resolved.push(i.outcome) },
      },
      questionRequest,
      { sessionId: "sess-9", ownerId: "owner-9", runId: "run-9" },
    );
    await Promise.resolve();

    // The turn was cancelled while the question was still on screen. Without
    // this the card sat there and the user answered a revoked run.
    stub.emitRunEvent("run.cancelled", "run-9");
    await expect(promise).resolves.toMatchObject({ kind: "cancelled" });
    expect(resolved).toEqual(["cancelled"]);
  });

  it("ignores a terminal event from a different run", async () => {
    const stub = kernelStub();
    let settled = false;
    const promise = askUser(
      { kernel: stub.kernel as any, log: () => {} },
      questionRequest,
      { sessionId: "sess-9", ownerId: "owner-9", runId: "run-9" },
    ).then((outcome) => { settled = true; return outcome; });
    await Promise.resolve();

    stub.emitRunEvent("run.failed", "some-other-run");
    await Promise.resolve();
    expect(settled).toBe(false);

    stub.emitResolution({ dispatchId: "disp-1", status: "resolved", resolution: { optionId: "main" } });
    await expect(promise).resolves.toEqual({ kind: "selected", optionIds: ["main"] });
  });
});

describe("multi-select answers", () => {
  it("keeps every chosen option for a multi-select question", () => {
    const [multi] = normalizeAskUser({
      adapterId: "acp",
      agentLabel: "Omi",
      args: {
        questions: [{ question: "Constraints?", options: ["a", "b", "c"], allow_multiple: true }],
      },
    });

    expect(outcomeFromResolution(multi, "resolved", { optionIds: ["a", "c"] }))
      .toEqual({ kind: "selected", optionIds: ["a", "c"] });
    // Ids that were never offered cannot be smuggled in alongside real ones.
    expect(outcomeFromResolution(multi, "resolved", { optionIds: ["a", "nope"] }))
      .toEqual({ kind: "selected", optionIds: ["a"] });
  });

  it("carries chosen options and typed words together", () => {
    const [multi] = normalizeAskUser({
      adapterId: "acp",
      agentLabel: "Omi",
      args: {
        questions: [{ question: "Constraints?", options: ["a", "b"], allow_multiple: true }],
      },
    });

    expect(outcomeFromResolution(multi, "resolved", { optionIds: ["a"], text: "and this" }))
      .toEqual({ kind: "selected", optionIds: ["a"], text: "and this" });

    // Typed words alone are still the plain answered shape.
    expect(outcomeFromResolution(multi, "resolved", { text: "just this" }))
      .toEqual({ kind: "answered", text: "just this" });
  });

  it("never lets typed words reach a permission", () => {
    const permission = normalizeAcpPermission({
      adapterId: "hermes",
      agentLabel: "Hermes",
      params: {
        sessionId: "s",
        toolCall: { title: "Run", kind: "execute" },
        options: [{ optionId: "once", name: "Allow once", kind: "allow_once" }],
      },
    })!;

    // ACP answers with an optionId and nothing else; text has no way home.
    expect(outcomeFromResolution(permission, "resolved", { optionIds: ["once"], text: "why not" }))
      .toEqual({ kind: "selected", optionIds: ["once"] });
  });

  it("keeps a single-select question single even when several ids arrive", () => {
    const [single] = normalizeAskUser({
      adapterId: "acp",
      agentLabel: "Omi",
      args: { questions: [{ question: "Stack?", options: ["a", "b"] }] },
    });

    expect(outcomeFromResolution(single, "resolved", { optionIds: ["a", "b"] }))
      .toEqual({ kind: "selected", optionIds: ["a"] });
  });
});

describe("a question on screen counts as progress, not a stall", () => {
  it("reports a human is being asked only while one actually is", async () => {
    const { humanIsBeingAsked } = await import("../src/runtime/desktop-elicitation-resolver.js");
    const stub = kernelStub();

    // Idle watchdogs cancel a turn that has produced no traffic. A turn blocked
    // on a card produces none, and cancelling it revokes the run before the
    // user's answer can land.
    expect(humanIsBeingAsked()).toBe(false);

    const promise = askUser(
      { kernel: stub.kernel as any, log: () => {} },
      questionRequest,
      { sessionId: "sess-9", ownerId: "owner-9", runId: "run-9" },
    );
    await Promise.resolve();
    expect(humanIsBeingAsked()).toBe(true);

    stub.emitResolution({ dispatchId: "disp-1", status: "resolved", resolution: { optionId: "main" } });
    await promise;
    expect(humanIsBeingAsked()).toBe(false);
  });

  it("stops reporting one even when the wait ends badly", async () => {
    const { humanIsBeingAsked } = await import("../src/runtime/desktop-elicitation-resolver.js");
    const stub = kernelStub();

    const promise = askUser(
      { kernel: stub.kernel as any, log: () => {} },
      questionRequest,
      { sessionId: "sess-9", ownerId: "owner-9", runId: null },
    );
    await Promise.resolve();
    expect(humanIsBeingAsked()).toBe(true);

    // A cancelled question must not leave a watchdog believing forever that
    // somebody is still deciding.
    stub.emitResolution({ dispatchId: "disp-1", status: "cancelled" });
    await promise;
    expect(humanIsBeingAsked()).toBe(false);
  });
});

describe("ask_user records a question against the session it was called from", () => {
  it("does not need an adapter-native session to reach the user", async () => {
    const stub = kernelStub();
    const seen: Array<Record<string, unknown>> = [];
    const promise = askUser(
      { kernel: stub.kernel as any, log: () => {}, notifier: { pending: (i: any) => seen.push(i), resolved: () => {} } },
      questionRequest,
      { sessionId: "sess-9", ownerId: "owner-9", runId: "run-9" },
    );
    await Promise.resolve();

    // The ACP path has to look a session up; ask_user already knows one.
    expect(stub.kernel.sessionForAdapterNativeSession).not.toHaveBeenCalled();
    expect(stub.created[0]).toMatchObject({
      ownerId: "owner-9",
      sourceSessionId: "sess-9",
      sourceRunId: "run-9",
      kind: "routing_choice",
      expiresAtMs: null,
    });
    expect(seen).toHaveLength(1);

    stub.emitResolution({ dispatchId: "disp-1", status: "resolved", resolution: { text: "release/0.12" } });
    await expect(promise).resolves.toEqual({ kind: "answered", text: "release/0.12" });
  });

  it("returns a cancellation when the user dismisses instead of answering", async () => {
    const stub = kernelStub();
    const promise = askUser(
      { kernel: stub.kernel as any, log: () => {} },
      questionRequest,
      { sessionId: "sess-9", ownerId: "owner-9", runId: null },
    );
    await Promise.resolve();

    stub.emitResolution({ dispatchId: "disp-1", status: "cancelled" });
    await expect(promise).resolves.toMatchObject({ kind: "cancelled" });
  });
});
