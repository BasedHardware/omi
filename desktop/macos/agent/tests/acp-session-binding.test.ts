import { describe, expect, it } from "vitest";
import { AcpRuntimeAdapter } from "../src/adapters/acp.js";

function attemptHarness() {
  const logs: string[] = [];
  const adapter = new AcpRuntimeAdapter({
    nodeBin: "/node",
    acpEntry: "/acp-entry.mjs",
    log: (message) => logs.push(message),
  });

  let resolvePrompt: (value: unknown) => void = () => {};
  const promptResult = new Promise((resolve) => {
    resolvePrompt = resolve;
  });
  (adapter as any).request = (method: string) =>
    method === "session/prompt" ? promptResult : Promise.resolve({});

  const events: Array<any> = [];
  const context = {
    sessionId: "omi-session",
    ownerId: "owner",
    requestId: "req",
    clientId: "client",
    runId: "run",
    attemptId: "attempt",
    toolCapabilityRef: "cap",
    binding: {
      sessionId: "omi-session",
      adapterId: "acp",
      adapterNativeSessionId: "acp-session-mine",
      resumeFidelity: "full",
      cwd: "/tmp",
    },
    prompt: [{ type: "text", text: "hi" }],
    mode: "chat",
  } as any;

  const attempt = adapter.executeAttempt(context, (event) => events.push(event), new AbortController().signal);

  return {
    logs,
    events,
    attempt,
    notify: (params: Record<string, unknown>) =>
      (adapter as any).notificationHandler?.("session/update", params),
    finish: () => resolvePrompt({ usage: {}, _meta: {} }),
  };
}

const textChunk = (text: string) => ({
  sessionUpdate: "agent_message_chunk",
  content: { type: "text", text },
});

describe("AcpRuntimeAdapter session/update binding authority", () => {
  it("drops a session/update carrying another session's id", async () => {
    const harness = attemptHarness();

    harness.notify({ sessionId: "acp-session-foreign", update: textChunk("stolen") });
    harness.notify({ sessionId: "acp-session-mine", update: textChunk("mine") });
    harness.finish();

    const result = await harness.attempt;
    expect(result.text).toBe("mine");
    expect(harness.events).not.toContainEqual(expect.objectContaining({ text: "stolen" }));
    expect(harness.logs).toContainEqual(
      "Dropped session/update for acp-session-foreign on binding acp-session-mine"
    );
  });

  it("drops a session/update with no session id at all", async () => {
    const harness = attemptHarness();

    harness.notify({ update: textChunk("unbound") });
    harness.finish();

    const result = await harness.attempt;
    expect(result.text).toBe("");
    expect(harness.logs).toContainEqual(
      "Dropped session/update for undefined on binding acp-session-mine"
    );
  });
});
