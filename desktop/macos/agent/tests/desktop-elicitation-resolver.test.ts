import { describe, expect, it, vi } from "vitest";
import {
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

const questionRequest = normalizeAskUser({
  adapterId: "acp",
  agentLabel: "Omi",
  args: { question: "Which branch?", options: ["main"] },
})!;

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

  return { kernel, created, emitResolution, subscriberCount: () => subscribers.length };
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
    await expect(pending).resolves.toEqual({ kind: "selected", optionId: "once" });
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
    await expect(pending).resolves.toEqual({ kind: "selected", optionId: "once" });
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

    await expect(resolver(permissionRequest)).resolves.toEqual({ kind: "selected", optionId: "no" });
    expect(stub.kernel.createDesktopDispatch).not.toHaveBeenCalled();
  });

  it("denies when the request carries no adapter session at all", async () => {
    const stub = kernelStub();
    const resolver = createKernelElicitationResolver({ kernel: stub.kernel as any, log: () => {} });

    await expect(
      resolver({ ...permissionRequest, externalSessionId: null }),
    ).resolves.toEqual({ kind: "selected", optionId: "no" });
  });

  it("denies when the dispatch cannot be recorded", async () => {
    const stub = kernelStub({
      createDesktopDispatch: vi.fn(() => { throw new Error("store is closed"); }),
    });
    const resolver = createKernelElicitationResolver({ kernel: stub.kernel as any, log: () => {} });

    await expect(resolver(permissionRequest)).resolves.toEqual({ kind: "selected", optionId: "no" });
  });
});

describe("resolution mapping", () => {
  it("accepts only an option the agent actually offered", () => {
    expect(outcomeFromResolution(permissionRequest, "resolved", { optionId: "once" }))
      .toEqual({ kind: "selected", optionId: "once" });
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
