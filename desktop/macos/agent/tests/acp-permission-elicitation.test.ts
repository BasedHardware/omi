import { describe, expect, it, vi } from "vitest";
import { AcpRuntimeAdapter } from "../src/adapters/acp.js";
import type {
  ElicitationOutcome,
  ElicitationRequest,
  ElicitationResolver,
} from "../src/runtime/desktop-elicitation.js";

/**
 * Drives the real `handleRequest` path with a captured stdin writer, so these
 * assertions exercise production permission handling rather than its shape.
 */
function harness(options: { adapterId?: "acp" | "hermes"; resolver?: ElicitationResolver } = {}) {
  const adapter = new AcpRuntimeAdapter({
    adapterId: options.adapterId ?? "acp",
    nodeBin: "/node",
    acpEntry: "/acp-entry.mjs",
  });
  const written: Array<Record<string, unknown>> = [];
  (adapter as any).stdinWriter = (line: string) => written.push(JSON.parse(line));
  if (options.resolver) adapter.elicitationResolver = options.resolver;

  return {
    adapter,
    written,
    responses: () => written.filter((message) => "id" in message),
    request(toolKind: string, permissionOptions?: Array<Record<string, unknown>>) {
      (adapter as any).handleRequest({
        jsonrpc: "2.0",
        id: 7,
        method: "session/request_permission",
        params: {
          sessionId: "sess-1",
          toolCall: {
            toolCallId: "tool-1",
            title: "Run a command",
            kind: toolKind,
            rawInput: { command: "rm -rf build/" },
          },
          options: permissionOptions ?? [
            { optionId: "once", name: "Allow once", kind: "allow_once" },
            { optionId: "always", name: "Allow always", kind: "allow_always" },
            { optionId: "no", name: "Deny", kind: "reject_once" },
          ],
        },
      });
    },
  };
}

/** Let the queued microtasks in the permission path run to completion. */
async function settle(): Promise<void> {
  for (let i = 0; i < 5; i += 1) await Promise.resolve();
}

describe("ACP permission requests reach a person", () => {
  it("auto-resolves a one-time grant on a read-shaped tool without asking", async () => {
    const resolver = vi.fn<ElicitationResolver>();
    const h = harness({ resolver });

    h.request("read");
    await settle();

    expect(resolver).not.toHaveBeenCalled();
    expect(h.responses()).toEqual([
      { jsonrpc: "2.0", id: 7, result: { outcome: { outcome: "selected", optionId: "once" } } },
    ]);
  });

  it("asks the user before an executing tool, and echoes their chosen option", async () => {
    const seen: ElicitationRequest[] = [];
    const resolver: ElicitationResolver = async (request) => {
      seen.push(request);
      return { kind: "selected", optionId: "always" };
    };
    const h = harness({ resolver });

    h.request("execute");
    await settle();

    expect(seen).toHaveLength(1);
    expect(seen[0]).toMatchObject({
      mode: "permission",
      prompt: "Run a command",
      subject: "rm -rf build/",
      allowsFreeText: false,
    });
    expect(h.responses()).toEqual([
      { jsonrpc: "2.0", id: 7, result: { outcome: { outcome: "selected", optionId: "always" } } },
    ]);
  });

  it("asks even on a read-shaped tool when the only grant offered is permanent", async () => {
    const resolver = vi.fn<ElicitationResolver>(async () => ({
      kind: "selected" as const,
      optionId: "always",
    }));
    const h = harness({ resolver });

    h.request("read", [{ optionId: "always", name: "Allow always", kind: "allow_always" }]);
    await settle();

    expect(resolver).toHaveBeenCalledTimes(1);
  });

  it("does not answer until the user does", async () => {
    let release: ((outcome: ElicitationOutcome) => void) | null = null;
    const h = harness({ resolver: () => new Promise((resolve) => { release = resolve; }) });

    h.request("execute");
    await settle();
    expect(h.responses()).toEqual([]);

    release!({ kind: "selected", optionId: "no" });
    await settle();
    expect(h.responses()).toHaveLength(1);
  });
});

describe("ACP permission requests fail closed", () => {
  it("denies rather than approving when no resolver is installed", async () => {
    const h = harness();

    h.request("execute");
    await settle();

    expect(h.responses()).toEqual([
      { jsonrpc: "2.0", id: 7, result: { outcome: { outcome: "selected", optionId: "no" } } },
    ]);
  });

  it("cancels when no rejection option exists to select", async () => {
    const h = harness();

    h.request("execute", [{ optionId: "always", name: "Allow always", kind: "allow_always" }]);
    await settle();

    expect(h.responses()).toEqual([
      { jsonrpc: "2.0", id: 7, result: { outcome: { outcome: "cancelled" } } },
    ]);
  });

  it("denies when the resolver itself fails", async () => {
    const h = harness({ resolver: async () => { throw new Error("kernel unavailable"); } });

    h.request("execute");
    await settle();

    expect(h.responses()).toEqual([
      { jsonrpc: "2.0", id: 7, result: { outcome: { outcome: "selected", optionId: "no" } } },
    ]);
  });

  it("cancels a request that offers no usable option", async () => {
    const resolver = vi.fn<ElicitationResolver>();
    const h = harness({ resolver });

    h.request("execute", []);
    await settle();

    expect(resolver).not.toHaveBeenCalled();
    expect(h.responses()).toEqual([
      { jsonrpc: "2.0", id: 7, result: { outcome: { outcome: "cancelled" } } },
    ]);
  });

  it("never coerces free text into an option the user did not pick", async () => {
    const h = harness({ resolver: async () => ({ kind: "answered", text: "use develop" }) });

    h.request("execute");
    await settle();

    expect(h.responses()).toEqual([
      { jsonrpc: "2.0", id: 7, result: { outcome: { outcome: "cancelled" } } },
    ]);
  });
});

describe("pending ACP permission requests are answerable to cancellation", () => {
  it("answers cancelled when the turn is cancelled while the user is deciding", async () => {
    const h = harness({ resolver: () => new Promise<ElicitationOutcome>(() => {}) });

    h.request("execute");
    await settle();
    expect(h.responses()).toEqual([]);

    await h.adapter.cancelAttempt({
      sessionId: "sess-1",
      binding: { adapterNativeSessionId: "sess-1" },
    } as any);
    await settle();

    expect(h.responses()).toEqual([
      { jsonrpc: "2.0", id: 7, result: { outcome: { outcome: "cancelled" } } },
    ]);
  });

  it("releases a waiter whose subprocess has exited", async () => {
    const h = harness({ resolver: () => new Promise<ElicitationOutcome>(() => {}) });

    h.request("execute");
    await settle();

    (h.adapter as any).cancelPendingPermissions(undefined, "adapter_process_exited");
    await settle();

    expect(h.responses()).toEqual([
      { jsonrpc: "2.0", id: 7, result: { outcome: { outcome: "cancelled" } } },
    ]);
  });

  it("answers a cancelled request exactly once", async () => {
    let release: ((outcome: ElicitationOutcome) => void) | null = null;
    const h = harness({ resolver: () => new Promise((resolve) => { release = resolve; }) });

    h.request("execute");
    await settle();

    (h.adapter as any).cancelPendingPermissions("sess-1", "turn_cancelled");
    await settle();
    release!({ kind: "selected", optionId: "always" });
    await settle();

    expect(h.responses()).toEqual([
      { jsonrpc: "2.0", id: 7, result: { outcome: { outcome: "cancelled" } } },
    ]);
  });
});

describe("external adapters are no longer dead-ended", () => {
  it("asks the user instead of returning a protocol error for permanent-only options", async () => {
    const resolver = vi.fn<ElicitationResolver>(async () => ({
      kind: "selected" as const,
      optionId: "always",
    }));
    const h = harness({ adapterId: "hermes", resolver });

    h.request("execute", [{ optionId: "always", name: "Allow always", kind: "allow_always" }]);
    await settle();

    expect(resolver).toHaveBeenCalledTimes(1);
    expect(h.responses().every((message) => !("error" in message))).toBe(true);
    expect(h.responses()).toEqual([
      { jsonrpc: "2.0", id: 7, result: { outcome: { outcome: "selected", optionId: "always" } } },
    ]);
  });
});
