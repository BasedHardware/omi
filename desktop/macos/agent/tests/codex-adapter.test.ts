import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { CodexRuntimeAdapter } from "../src/adapters/codex.js";

describe("CodexRuntimeAdapter", () => {
  // Save/restore the env we mutate so this test can't leak into others in the worker.
  let savedCodexCommand: string | undefined;
  beforeEach(() => {
    savedCodexCommand = process.env.OMI_CODEX_ADAPTER_COMMAND;
  });
  afterEach(() => {
    if (savedCodexCommand === undefined) {
      delete process.env.OMI_CODEX_ADAPTER_COMMAND;
    } else {
      process.env.OMI_CODEX_ADAPTER_COMMAND = savedCodexCommand;
    }
  });

  it("registers as the codex adapter with one-shot exec capabilities", () => {
    const adapter = new CodexRuntimeAdapter({ command: "codex" });
    expect(adapter.adapterId).toBe("codex");
    // Codex exec is stateless per attempt: no resumable native session, no per-session model switch, no Omi tool relay.
    expect(adapter.capabilities.supportsNativeResume).toBe(false);
    expect(adapter.capabilities.resumeFidelity).toBe("none");
    expect(adapter.capabilities.supportsTools).toBe(false);
    expect(adapter.capabilities.supportsModelSwitching).toBe(false);
    // But an active `codex exec` subprocess is cancellable.
    expect(adapter.capabilities.supportsCancellation).toBe(true);
  });

  it("opens a binding whose native session id is not conflated with the Omi session id", async () => {
    const adapter = new CodexRuntimeAdapter({ command: "codex" });
    const binding = await adapter.openBinding({ sessionId: "omi-session-1", cwd: "/tmp" });
    expect(binding.adapterId).toBe("codex");
    expect(binding.adapterNativeSessionId).not.toBe("omi-session-1");
    expect(binding.adapterNativeSessionId).toContain("codex");
  });

  it("reports a clear error when no command is configured", async () => {
    const adapter = new CodexRuntimeAdapter(); // no command, and OMI_CODEX_ADAPTER_COMMAND unset in test env
    delete process.env.OMI_CODEX_ADAPTER_COMMAND;
    await expect(adapter.start()).rejects.toThrow("OMI_CODEX_ADAPTER_COMMAND");
  });
});
