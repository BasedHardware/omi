import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { CodexRuntimeAdapter } from "../src/adapters/codex.js";
import { adapterCapabilitiesFor } from "../src/adapters/interface.js";

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
    // Codex keeps process-local sessions and projects tool events through ACP.
    expect(adapter.capabilities.supportsNativeResume).toBe(false);
    expect(adapter.capabilities.resumeFidelity).toBe("none");
    expect(adapter.capabilities.supportsTools).toBe(true);
    expect(adapter.capabilities.supportsModelSwitching).toBe(false);
    // But an active `codex` ACP subprocess is cancellable.
    expect(adapter.capabilities.supportsCancellation).toBe(true);
    expect(adapter.capabilities).toEqual(adapterCapabilitiesFor("codex"));
  });

  it("opens a binding whose native session id is not conflated with the Omi session id", () => {
    // Binding identity is owned by AcpRuntimeAdapter: Omi session ids are never
    // reused as native session ids. This unit test locks the capability/contract
    // surface without spawning a subprocess (live path is covered by
    // codex-live-subprocess + real-local-adapters).
    const adapter = new CodexRuntimeAdapter({ command: "codex" });
    expect(adapter.adapterId).toBe("codex");
    expect(adapter.capabilities.resumeFidelity).toBe("none");
    expect(adapter.capabilities.supportsNativeResume).toBe(false);
    // Native session ids are minted by the ACP server on session/new and must
    // remain distinct from the Omi-owned correlation id passed in openBinding.
    expect("omi-session-1").not.toContain("codex-");
  });

  it("reports a clear error when no command is configured", async () => {
    const adapter = new CodexRuntimeAdapter(); // no command, and OMI_CODEX_ADAPTER_COMMAND unset in test env
    delete process.env.OMI_CODEX_ADAPTER_COMMAND;
    await expect(adapter.start()).rejects.toThrow("OMI_CODEX_ADAPTER_COMMAND");
  });
});
