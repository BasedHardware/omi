import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  adapterActivationEnv,
  adapterActivationError,
  adapterIdForHarnessMode,
  adapterIsActivated,
  adapterProfile,
  classifyTaskForAdapterSelection,
  selectBestAdapterForTask,
  taskTextLooksCodeRelated,
} from "../src/runtime/adapter-selection.js";

describe("adapter selection and activation", () => {
  it("maps harness modes to explicit adapter ids", () => {
    expect(adapterIdForHarnessMode(undefined)).toBe("acp");
    expect(adapterIdForHarnessMode("acp")).toBe("acp");
    expect(adapterIdForHarnessMode("piMono")).toBe("pi-mono");
    expect(adapterIdForHarnessMode("pi-mono")).toBe("pi-mono");
    expect(adapterIdForHarnessMode("hermes")).toBe("hermes");
    expect(adapterIdForHarnessMode("openclaw")).toBe("openclaw");
    expect(adapterIdForHarnessMode("openClaw")).toBe("openclaw");
    expect(adapterIdForHarnessMode("codex")).toBe("codex");
    expect(() => adapterIdForHarnessMode("unknown")).toThrow("Unknown harness mode: unknown");
  });

  it("keeps activation separate from implementation", () => {
    expect(adapterActivationEnv("acp")).toBeUndefined();
    expect(adapterActivationEnv("pi-mono")).toBe("OMI_AUTH_TOKEN");
    expect(adapterActivationEnv("hermes")).toBe("OMI_HERMES_ADAPTER_COMMAND");
    expect(adapterActivationEnv("openclaw")).toBe("OMI_OPENCLAW_ADAPTER_COMMAND");
    expect(adapterActivationEnv("codex")).toBe("OMI_CODEX_ADAPTER_COMMAND");

    expect(adapterIsActivated("acp", {})).toBe(true);
    expect(adapterIsActivated("hermes", {})).toBe(false);
    expect(adapterIsActivated("hermes", { OMI_HERMES_ADAPTER_COMMAND: "  " })).toBe(false);
    expect(adapterIsActivated("hermes", { OMI_HERMES_ADAPTER_COMMAND: "hermes-adapter" })).toBe(true);
    expect(adapterIsActivated("openclaw", { OMI_OPENCLAW_ADAPTER_COMMAND: "openclaw-adapter" })).toBe(true);
    expect(adapterIsActivated("codex", { OMI_CODEX_ADAPTER_COMMAND: "codex" })).toBe(true);
  });

  it("centralizes production adapter profiles and capabilities", () => {
    expect(adapterProfile("acp")).toMatchObject({
      adapterId: "acp",
      activationEnv: undefined,
      capabilities: { supportsTools: true },
    });
    expect(adapterProfile("hermes")).toMatchObject({
      adapterId: "hermes",
      activationEnv: "OMI_HERMES_ADAPTER_COMMAND",
      capabilities: { supportsTools: true },
    });
    expect(adapterProfile("openclaw")).toMatchObject({
      adapterId: "openclaw",
      activationEnv: "OMI_OPENCLAW_ADAPTER_COMMAND",
      capabilities: { supportsTools: false, supportsModelSwitching: false },
    });
    expect(adapterProfile("codex")).toMatchObject({
      adapterId: "codex",
      activationEnv: "OMI_CODEX_ADAPTER_COMMAND",
      capabilities: { supportsTools: false, supportsModelSwitching: false },
    });
    expect(adapterActivationError("hermes")).toBe(
      "Hermes is not available. Make sure Hermes is installed first, then try again."
    );
    expect(adapterActivationError("hermes")).not.toContain("OMI_HERMES_ADAPTER_COMMAND");
    expect(adapterActivationError("openclaw")).toBe(
      "OpenClaw is not available. Make sure OpenClaw is installed first, then try again."
    );
    expect(adapterActivationError("openclaw")).not.toContain("OMI_OPENCLAW_ADAPTER_COMMAND");
    expect(adapterActivationError("codex")).toBe(
      "Codex is not available. Install the Codex CLI, sign in, then try again."
    );
    expect(adapterActivationError("codex")).not.toContain("OMI_CODEX_ADAPTER_COMMAND");
  });

  it("detects code-like task text with simple keywords and path patterns", () => {
    expect(taskTextLooksCodeRelated("Fix the failing test in agent/src/runtime/kernel.ts")).toBe(true);
    expect(taskTextLooksCodeRelated("Can you implement a function for parsing dates?")).toBe(true);
    expect(taskTextLooksCodeRelated("Please refactor this class")).toBe(true);
    expect(taskTextLooksCodeRelated("phase2AutoSelectionCheck is failing")).toBe(true);
    expect(taskTextLooksCodeRelated("Draft a concise meeting agenda for tomorrow")).toBe(false);
    expect(taskTextLooksCodeRelated("Summarize Mission 1400 progress")).toBe(false);
  });

  it("classifies task shape before choosing among connected adapters", () => {
    expect(classifyTaskForAdapterSelection("Trace this bug across the codebase and refactor the interaction between modules")).toBe(
      "deep_codebase"
    );
    expect(classifyTaskForAdapterSelection("Run the migration script and update the CI workflow")).toBe("terminal_devops");
    expect(classifyTaskForAdapterSelection("Implement a function for parsing dates")).toBe("straightforward_code");
    expect(classifyTaskForAdapterSelection("Draft a concise meeting agenda for tomorrow")).toBe("general");
  });

  it("prefers ACP for deep codebase tasks and Codex for terminal-native tasks when connected", () => {
    expect(
      selectBestAdapterForTask({
        prompt: "Trace this bug across the codebase and refactor the interaction between modules",
        defaultAdapterId: "pi-mono",
        connectedAdapterIds: ["acp", "hermes", "openclaw", "codex"],
      }),
    ).toMatchObject({
      adapterId: "acp",
      fallbackAdapterIds: ["codex", "hermes", "openclaw"],
      reason: "deep_codebase_task_acp",
      taskKind: "deep_codebase",
      codeLike: true,
    });

    expect(
      selectBestAdapterForTask({
        prompt: "Run the migration script and update the CI dependency lockfile",
        defaultAdapterId: "pi-mono",
        connectedAdapterIds: ["acp", "hermes", "openclaw", "codex"],
      }),
    ).toMatchObject({
      adapterId: "codex",
      fallbackAdapterIds: ["acp", "hermes", "openclaw"],
      reason: "terminal_devops_task_codex",
      taskKind: "terminal_devops",
    });
  });

  it("uses only connected adapters even when the preferred adapter is unavailable", () => {
    expect(
      selectBestAdapterForTask({
        prompt: "Refactor this to be cleaner across these three files",
        defaultAdapterId: "pi-mono",
        connectedAdapterIds: ["codex"],
      }),
    ).toMatchObject({
      adapterId: "codex",
      fallbackAdapterIds: [],
      reason: "deep_codebase_task_codex",
      taskKind: "deep_codebase",
      connectedAdapterIds: ["codex"],
    });

    expect(
      selectBestAdapterForTask({
        prompt: "Run this migration script",
        defaultAdapterId: "pi-mono",
        connectedAdapterIds: ["codex"],
      }),
    ).toMatchObject({
      adapterId: "codex",
      fallbackAdapterIds: [],
      reason: "terminal_devops_task_codex",
      taskKind: "terminal_devops",
      connectedAdapterIds: ["codex"],
    });
  });

  it("auto-selects Codex for straightforward code tasks and Hermes first for general tasks", () => {
    expect(
      selectBestAdapterForTask({
        prompt: "Fix the bug in Desktop/Sources/Chat/AgentBridge.swift",
        defaultAdapterId: "pi-mono",
        connectedAdapterIds: ["acp", "hermes", "openclaw", "codex"],
      }),
    ).toMatchObject({
      adapterId: "codex",
      fallbackAdapterIds: ["acp", "hermes", "openclaw"],
      reason: "straightforward_code_task_codex",
      taskKind: "straightforward_code",
      codeLike: true,
    });

    expect(
      selectBestAdapterForTask({
        prompt: "Summarize my notes and draft a follow-up",
        defaultAdapterId: "pi-mono",
        connectedAdapterIds: ["acp", "hermes", "openclaw", "codex"],
      }),
    ).toMatchObject({
      adapterId: "hermes",
      fallbackAdapterIds: ["openclaw", "codex", "acp"],
      reason: "general_task_hermes",
      taskKind: "general",
      codeLike: false,
    });
  });

  it("falls through to the default adapter when no task-execution adapters are connected", () => {
    expect(
      selectBestAdapterForTask({
        prompt: "Fix the bug in kernel.ts",
        defaultAdapterId: "pi-mono",
        connectedAdapterIds: [],
      }),
    ).toMatchObject({
      adapterId: "pi-mono",
      fallbackAdapterIds: [],
      reason: "default_no_connected_task_adapters",
    });
  });

  it("source: daemon registers Hermes/OpenClaw/Codex explicitly and does not stamp MCP env as ACP", () => {
    const indexSource = readFileSync(new URL("../src/index.ts", import.meta.url), "utf8");

    expect(indexSource).toContain("adapterIdForHarnessMode(defaultHarnessMode)");
    expect(indexSource).toContain('defaultAdapterId === "acp"');
    expect(indexSource).toContain("ensureRegisteredAdapter(registry, \"hermes\"");
    expect(indexSource).toContain("ensureRegisteredAdapter(registry, \"openclaw\"");
    expect(indexSource).toContain("ensureRegisteredAdapter(registry, \"codex\"");
    expect(indexSource).toContain('if (defaultAdapterId === "acp" && registry.has("acp")) connected.push("acp")');
    expect(indexSource).toContain('adapterActivationError("hermes")');
    expect(indexSource).toContain('adapterActivationError("openclaw")');
    expect(indexSource).toContain('adapterActivationError("codex")');
    expect(indexSource).toContain("query.ownerId = queryOwnerId");
    expect(indexSource).toContain('{ name: "OMI_ADAPTER_ID", value: context?.adapterId ?? "acp" }');
    expect(indexSource).not.toContain('{ name: "OMI_ADAPTER_ID", value: "acp" }');
  });
});
