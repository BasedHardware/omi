import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import type { OutboundMessageDraft } from "../src/protocol.js";
import { RelayToolApprovals, type PendingSwiftToolCall } from "../src/runtime/relay-tool-approvals.js";
import type { AuthorizedRunToolInvocation } from "../src/runtime/run-tool-capability.js";
import { readToolInvocation } from "../src/runtime/tool-invocation-ledger.js";
import { createKernelHarness, waitUntil } from "./kernel-fakes.js";

const createdDirs: string[] = [];

afterEach(() => {
  for (const dir of createdDirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

interface FakeClient {
  name: string;
}

interface WrittenResult {
  client: FakeClient;
  callId: string;
  result: Record<string, unknown>;
  invocationId: string | undefined;
  outcome: string | undefined;
}

/** Deterministic timers: nothing fires until the test says so. */
class ManualTimers {
  private next = 1;
  readonly scheduled = new Map<number, { callback: () => void; delayMs: number }>();

  set = (callback: () => void, delayMs: number): unknown => {
    const handle = this.next++;
    this.scheduled.set(handle, { callback, delayMs });
    return handle;
  };

  clear = (handle: unknown): void => {
    this.scheduled.delete(handle as number);
  };

  fireAll(): void {
    for (const [handle, timer] of [...this.scheduled]) {
      this.scheduled.delete(handle);
      timer.callback();
    }
  }
}

const sendInput = { to: "+15551234567", text: "Running late" };

async function relayFixture() {
  const dir = mkdtempSync(join(tmpdir(), "omi-relay-approvals-"));
  createdDirs.push(dir);
  const harness = createKernelHarness(join(dir, "omi-agentd.sqlite3"), "acp");
  const { store, adapter, kernel } = harness;
  kernel.setDesktopToolApprovalsEnabled(true);
  const resolved = kernel.resolveSurfaceSession({
    ownerId: "owner",
    surfaceRef: { surfaceKind: "main_chat", externalRefKind: "chat", externalRefId: "relay-approvals" },
    defaultAdapterId: "acp",
  });
  adapter.deferResult();
  const runPromise = kernel.executeRun({
    ownerId: "owner",
    sessionId: resolved.agentSessionId,
    surfaceKind: "main_chat",
    externalRefKind: "chat",
    externalRefId: "relay-approvals",
    defaultAdapterId: "acp",
    adapterId: "acp",
    clientId: "relay-client",
    requestId: "relay-request",
    prompt: "Tell Alice I'm running late",
    cwd: "/tmp/relay-approvals",
    admittedContextSnapshot: kernel.contextSnapshot(resolved.agentSessionId, "owner", "main_chat"),
  });
  await waitUntil(() => adapter.executed.length === 1);
  const capabilityRef = adapter.executed[0]!.toolCapabilityRef;

  const sent: OutboundMessageDraft[] = [];
  const written: WrittenResult[] = [];
  const timers = new ManualTimers();
  const pendingSwiftCalls = new Map<string, PendingSwiftToolCall<FakeClient>>();
  const relay = new RelayToolApprovals<FakeClient>({
    kernel,
    send: (message) => sent.push(message),
    writeRelayToolResult: (client, callId, result, invocation, outcome) =>
      written.push({ client, callId, result: JSON.parse(result), invocationId: invocation?.invocationId, outcome }),
    pendingSwiftCalls,
    activeOwnerId: () => "owner",
    log: () => undefined,
    setTimer: timers.set,
    clearTimer: timers.clear,
  });
  kernel.subscribe((event) => relay.handleKernelEvent(event));

  const park = (client: FakeClient, invocationId: string, toolInput: Record<string, unknown> = sendInput) => {
    const outcome = kernel.authorizeRelayedRunToolInvocationOrRequestApproval({
      capabilityRef,
      invocationId,
      toolName: "send_message",
      toolInput,
      activeOwnerId: "owner",
    });
    if (outcome.kind !== "approval_required") throw new Error("expected send_message to park");
    relay.park({
      client,
      callId: `call-${invocationId}`,
      invocation: outcome.invocation,
      toolInput,
      dispatch: outcome.dispatch,
      request: outcome.request,
    });
    return outcome;
  };
  const finish = async () => {
    adapter.resolveDeferred({ terminalStatus: "completed", text: "done" });
    await runPromise;
  };
  const frames = (type: string) => sent.filter((message) => message.type === type);
  return { store, kernel, relay, sent, written, timers, pendingSwiftCalls, park, frames, finish, capabilityRef };
}

describe("relay tool approvals", () => {
  it("shows the card, then an allow dispatches to Swift exactly once", async () => {
    const fx = await relayFixture();
    const client: FakeClient = { name: "pi-mono" };
    const outcome = fx.park(client, "send-1");

    expect(fx.frames("approval_requested")).toHaveLength(1);
    expect(fx.frames("approval_requested")[0]).toMatchObject({
      approvalId: outcome.dispatch.dispatchId,
      invocationId: "send-1",
      toolName: "send_message",
      preview: sendInput,
      defaultOptionId: "deny",
    });
    expect(fx.frames("authorized_tool_execution")).toHaveLength(0);
    expect(fx.written).toHaveLength(0);
    expect(fx.timers.scheduled.size).toBe(1);

    fx.kernel.resolveDesktopDispatch(outcome.dispatch.dispatchId, {
      ownerId: "owner",
      status: "resolved",
      resolvedBy: "user",
      resolutionJson: JSON.stringify({ decision: "allow" }),
    });

    expect(fx.frames("approval_resolved")).toHaveLength(1);
    expect(fx.frames("approval_resolved")[0]).toMatchObject({ approvalId: outcome.dispatch.dispatchId, decision: "allow", selectedOptionId: "allow_once" });
    const executions = fx.frames("authorized_tool_execution");
    expect(executions).toHaveLength(1);
    expect(executions[0]).toMatchObject({ invocationId: "send-1", toolName: "send_message", input: sendInput, inputHash: outcome.invocation.inputHash });
    expect(fx.pendingSwiftCalls.get("send-1")).toMatchObject({ client, callId: "call-send-1" });
    expect(readToolInvocation(fx.store, "send-1").status).toBe("dispatched");
    // The expiry timer is gone; the Swift execution timer took its place.
    expect(fx.timers.scheduled.size).toBe(1);
    expect(fx.written).toHaveLength(0);

    // A second resolution of the same card changes nothing.
    expect(() => fx.kernel.resolveDesktopDispatch(outcome.dispatch.dispatchId, {
      ownerId: "owner",
      status: "resolved",
      resolutionJson: JSON.stringify({ decision: "allow" }),
    })).toThrow();
    expect(fx.frames("authorized_tool_execution")).toHaveLength(1);
    await fx.finish();
    fx.store.close();
  });

  it("a deny answers the model with approval_denied and never reaches Swift", async () => {
    const fx = await relayFixture();
    const client: FakeClient = { name: "pi-mono" };
    const outcome = fx.park(client, "send-1");

    fx.kernel.resolveDesktopDispatch(outcome.dispatch.dispatchId, {
      ownerId: "owner",
      status: "resolved",
      resolvedBy: "user",
      resolutionJson: JSON.stringify({ decision: "deny" }),
    });

    expect(fx.frames("authorized_tool_execution")).toHaveLength(0);
    expect(fx.frames("approval_resolved")[0]).toMatchObject({ decision: "deny", selectedOptionId: "deny" });
    expect(fx.written).toEqual([{
      client,
      callId: "call-send-1",
      result: { ok: false, error: { code: "approval_denied", message: "The user declined this action.", reason: "deny" } },
      invocationId: "send-1",
      outcome: "failed",
    }]);
    expect(fx.timers.scheduled.size).toBe(0);
    expect(readToolInvocation(fx.store, "send-1")).toMatchObject({ status: "failed", errorCode: "approval_denied" });
    await fx.finish();
    fx.store.close();
  });

  it("expiry fails the call closed as a system decision", async () => {
    const fx = await relayFixture();
    const client: FakeClient = { name: "pi-mono" };
    const outcome = fx.park(client, "send-1");

    fx.timers.fireAll();

    expect(fx.frames("authorized_tool_execution")).toHaveLength(0);
    expect(fx.frames("approval_resolved")[0]).toMatchObject({
      approvalId: outcome.dispatch.dispatchId,
      decision: "expired",
      automatic: true,
      resolvedBy: "system",
    });
    expect(fx.written[0]).toMatchObject({
      callId: "call-send-1",
      result: { ok: false, error: { code: "approval_denied", reason: "expired" } },
      outcome: "failed",
    });
    expect(fx.store.getRow("SELECT status FROM desktop_dispatches WHERE dispatch_id = ?", [outcome.dispatch.dispatchId]).status).toBe("expired");
    expect(readToolInvocation(fx.store, "send-1")).toMatchObject({ status: "failed", errorCode: "approval_expired" });
    // A late answer after expiry finds nothing to admit.
    expect(() => fx.kernel.resolveDesktopDispatch(outcome.dispatch.dispatchId, {
      ownerId: "owner",
      status: "resolved",
      resolutionJson: JSON.stringify({ decision: "allow" }),
    })).toThrow("not pending");
    await fx.finish();
    fx.store.close();
  });

  it("a disconnected relay client closes its own card without writing anywhere", async () => {
    const fx = await relayFixture();
    const gone: FakeClient = { name: "gone" };
    const staying: FakeClient = { name: "staying" };
    const first = fx.park(gone, "send-1");
    const second = fx.park(staying, "send-2", { ...sendInput, text: "Still here" });

    fx.relay.rejectForClient(gone);

    expect(fx.store.getRow("SELECT status FROM desktop_dispatches WHERE dispatch_id = ?", [first.dispatch.dispatchId]).status).toBe("cancelled");
    expect(fx.store.getRow("SELECT status FROM desktop_dispatches WHERE dispatch_id = ?", [second.dispatch.dispatchId]).status).toBe("pending");
    expect(readToolInvocation(fx.store, "send-1")).toMatchObject({ status: "failed", errorCode: "approval_cancelled" });
    expect(readToolInvocation(fx.store, "send-2").status).toBe("prepared");
    // Nobody is left to receive a result for the disconnected client.
    expect(fx.written).toHaveLength(0);
    expect(fx.frames("approval_resolved")).toEqual([
      expect.objectContaining({ approvalId: first.dispatch.dispatchId, decision: "cancelled" }),
    ]);
    // The other client's card is still live and still answerable.
    fx.kernel.resolveDesktopDispatch(second.dispatch.dispatchId, {
      ownerId: "owner",
      status: "resolved",
      resolutionJson: JSON.stringify({ decision: "allow" }),
    });
    expect(fx.frames("authorized_tool_execution")).toEqual([expect.objectContaining({ invocationId: "send-2" })]);
    await fx.finish();
    fx.store.close();
  });

  it("a duplicate invocation id is refused while the first is parked or in flight", async () => {
    const fx = await relayFixture();
    const client: FakeClient = { name: "pi-mono" };
    const outcome = fx.park(client, "send-1");

    // The broker already refuses a replayed invocation id; the relay also does
    // when handed the same invocation twice.
    fx.relay.park({
      client,
      callId: "call-dup",
      invocation: outcome.invocation,
      toolInput: sendInput,
      dispatch: outcome.dispatch,
      request: outcome.request,
    });
    expect(fx.written).toEqual([expect.objectContaining({
      callId: "call-dup",
      result: { ok: false, error: { code: "invocation_replayed", message: "Duplicate tool invocation" } },
    })]);
    expect(fx.frames("approval_requested")).toHaveLength(1);

    fx.kernel.resolveDesktopDispatch(outcome.dispatch.dispatchId, {
      ownerId: "owner",
      status: "resolved",
      resolutionJson: JSON.stringify({ decision: "allow" }),
    });
    expect(fx.frames("authorized_tool_execution")).toHaveLength(1);
    fx.relay.dispatchToSwift(client, "call-dup-2", outcome.invocation, sendInput);
    expect(fx.written).toHaveLength(2);
    expect(fx.written[1]!.result).toMatchObject({ error: { code: "invocation_replayed" } });
    expect(fx.frames("authorized_tool_execution")).toHaveLength(1);
    await fx.finish();
    fx.store.close();
  });

  it("run cancellation fails the parked call and the card ends with one resolution", async () => {
    const fx = await relayFixture();
    const client: FakeClient = { name: "pi-mono" };
    const outcome = fx.park(client, "send-1");

    await fx.kernel.cancelRun(outcome.invocation.runId, { ownerId: "owner" });
    await fx.finish();

    expect(fx.written).toEqual([expect.objectContaining({
      callId: "call-send-1",
      result: { ok: false, error: expect.objectContaining({ code: expect.stringMatching(/run_terminal|attempt_terminal/) }) },
      outcome: "failed",
    })]);
    expect(fx.frames("approval_resolved")).toEqual([
      expect.objectContaining({ approvalId: outcome.dispatch.dispatchId, decision: "cancelled", automatic: true }),
    ]);
    expect(fx.frames("authorized_tool_execution")).toHaveLength(0);
    expect(fx.timers.scheduled.size).toBe(0);
    fx.store.close();
  });

  it("an owner change ends the card with one frame and one failed result, before anything else", async () => {
    const fx = await relayFixture();
    const client: FakeClient = { name: "pi-mono" };
    const outcome = fx.park(client, "send-1");

    fx.kernel.revokeRunToolCapabilitiesForOwner("owner", "owner_changed");

    // The resolution reached Swift as soon as the revocation happened, not on
    // some later event.
    expect(fx.frames("approval_resolved")).toEqual([
      expect.objectContaining({ approvalId: outcome.dispatch.dispatchId, decision: "cancelled", automatic: true }),
    ]);
    expect(fx.written).toEqual([expect.objectContaining({
      callId: "call-send-1",
      result: { ok: false, error: { code: "approval_denied", message: expect.any(String), reason: "cancelled" } },
      outcome: "failed",
    })]);
    expect(fx.frames("authorized_tool_execution")).toHaveLength(0);
    expect(fx.timers.scheduled.size).toBe(0);
    // The daemon's owner sweep afterwards finds nothing left to fail twice.
    fx.relay.rejectForOwner("owner", "owner_changed", "Active owner changed during tool execution");
    expect(fx.written).toHaveLength(1);
    await fx.finish();
    fx.store.close();
  });

  it("a Swift execution that never answers becomes outcome_unknown and fails the model's call", async () => {
    const fx = await relayFixture();
    const client: FakeClient = { name: "pi-mono" };
    const outcome = fx.park(client, "send-1");
    fx.kernel.resolveDesktopDispatch(outcome.dispatch.dispatchId, {
      ownerId: "owner",
      status: "resolved",
      resolutionJson: JSON.stringify({ decision: "allow" }),
    });
    expect(readToolInvocation(fx.store, "send-1").status).toBe("dispatched");

    fx.timers.fireAll();

    expect(fx.pendingSwiftCalls.size).toBe(0);
    expect(readToolInvocation(fx.store, "send-1")).toMatchObject({ status: "outcome_unknown", errorCode: "swift_tool_timeout" });
    expect(fx.written).toEqual([expect.objectContaining({
      result: { ok: false, error: { code: "swift_tool_timeout", message: "Timed out waiting for the Swift tool executor" } },
      outcome: "failed",
    })]);
    await fx.finish();
    fx.store.close();
  });
});

/** Compile-time check that the relay accepts the kernel's invocation type unchanged. */
export type RelayInvocation = AuthorizedRunToolInvocation;
