import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { CodexRuntimeAdapter } from "../src/adapters/codex.js";
import type { AdapterAttemptContext, AdapterBindingHandle } from "../src/adapters/interface.js";

// NOTE: this file intentionally does NOT mock child_process. It spawns a real
// fake-codex-acp subprocess so the whole path is exercised for real: spawn with
// shell:true, the external env allowlist, stdio JSON-RPC framing, the ACP
// handshake, streaming translation, and result/usage aggregation.

const __dirname = dirname(fileURLToPath(import.meta.url));
const FAKE_CODEX_ACP = join(__dirname, "fixtures", "fake-codex-acp.mjs");

function makeContext(binding: AdapterBindingHandle): AdapterAttemptContext {
  return {
    sessionId: "omi-session",
    ownerId: "owner-runtime",
    requestId: "omi-request",
    clientId: "desktop",
    runId: "omi-run",
    attemptId: "omi-attempt",
    binding,
    prompt: "Reply exactly: CODEX_LIVE_OK",
    mode: "act",
    tools: [],
    model: "gpt-5.2[high]",
    metadata: { protocolVersion: 2 },
  };
}

describe("Codex adapter — live real subprocess (no mocks)", () => {
  beforeEach(() => {
    process.env.OMI_CODEX_ADAPTER_COMMAND = `node ${FAKE_CODEX_ACP}`;
    process.env.OPENAI_API_KEY = "sk-omi-live-test";
    process.env.NO_BROWSER = "1";
    process.env.INITIAL_AGENT_MODE = "agent-full-access";
  });
  afterEach(() => {
    delete process.env.OMI_CODEX_ADAPTER_COMMAND;
    delete process.env.OPENAI_API_KEY;
    delete process.env.NO_BROWSER;
    delete process.env.INITIAL_AGENT_MODE;
  });

  it("spawns codex-acp for real and completes a prompt end-to-end", async () => {
    const adapter = new CodexRuntimeAdapter();
    await adapter.start();

    const binding = await adapter.openBinding({
      sessionId: "omi-session",
      cwd: "/tmp/work",
      model: "gpt-5.2[high]",
    });
    expect(binding).toMatchObject({
      adapterId: "codex",
      adapterNativeSessionId: "codex-live-session",
      resumeFidelity: "none",
    });

    const result = await adapter.executeAttempt(makeContext(binding), () => {}, new AbortController().signal);

    // The fake echoes the env it actually received, proving the real subprocess
    // got OPENAI_API_KEY (auth=1) + INITIAL_AGENT_MODE + NO_BROWSER via the
    // per-adapter allowlist — the env-stripping bug-risk fix, verified live.
    expect(result.text).toBe("CODEX_LIVE_OK auth=1 agent-full-access 1");
    expect(result).toMatchObject({
      adapterSessionId: "codex-live-session",
      terminalStatus: "succeeded",
      inputTokens: 5,
      outputTokens: 6,
      cacheReadTokens: 1,
      costUsd: 0,
    });

    await adapter.stop();
  });

  it("surfaces a clear failure when codex-acp has no auth (no key, no login)", async () => {
    // No key + no stored login.
    delete process.env.OPENAI_API_KEY;
    delete process.env.CODEX_API_KEY;

    const adapter = new CodexRuntimeAdapter();
    await adapter.start();
    const binding = await adapter.openBinding({ sessionId: "omi-session", cwd: "/tmp/work" });

    // The prompt errors out; the adapter propagates it (kernel maps this to a
    // failed attempt shown on the pill). It does NOT hang or silently succeed.
    await expect(
      adapter.executeAttempt(makeContext(binding), () => {}, new AbortController().signal)
    ).rejects.toThrow(/Not authenticated|codex login|OPENAI_API_KEY/);

    await adapter.stop();
  });
});
