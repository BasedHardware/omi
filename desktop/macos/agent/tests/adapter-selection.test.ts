import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  adapterActivationEnv,
  adapterActivationError,
  adapterIdForHarnessMode,
  adapterIsActivated,
  adapterProfile,
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
    expect(adapterIsActivated("codex", { OMI_CODEX_ADAPTER_COMMAND: "codex-adapter" })).toBe(true);
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
      "Hermes is not available. Install it from github.com/NousResearch/hermes-agent with `pip install -e '.[acp]'` (or `uvx --from 'hermes-agent[acp]'`), then run `hermes model` to configure a provider, and try again."
    );
    expect(adapterActivationError("hermes")).not.toContain("OMI_HERMES_ADAPTER_COMMAND");
    expect(adapterActivationError("openclaw")).toBe(
      "OpenClaw is not available. Install OpenClaw on your PATH, or set the OMI_OPENCLAW_ADAPTER_COMMAND environment variable to point Omi at your OpenClaw binary, then try again."
    );
    expect(adapterActivationError("codex")).toBe(
      "Codex is not available. Run `npm install -g @openai/codex` in your terminal, then run `codex` to sign in, and try again."
    );
    expect(adapterActivationError("codex")).not.toContain("OMI_CODEX_ADAPTER_COMMAND");
  });

  it("source: daemon registers Hermes/OpenClaw/Codex explicitly and does not stamp MCP env as ACP", () => {
    const indexSource = readFileSync(new URL("../src/index.ts", import.meta.url), "utf8");

    expect(indexSource).toContain("adapterIdForHarnessMode(defaultHarnessMode)");
    expect(indexSource).toContain('defaultAdapterId === "acp"');
    expect(indexSource).toContain("ensureRegisteredAdapter(registry, \"hermes\"");
    expect(indexSource).toContain("ensureRegisteredAdapter(registry, \"openclaw\"");
    expect(indexSource).toContain("ensureRegisteredAdapter(registry, \"codex\"");
    expect(indexSource).toContain('adapterActivationError("hermes")');
    expect(indexSource).toContain('adapterActivationError("openclaw")');
    expect(indexSource).toContain('adapterActivationError("codex")');
    expect(indexSource).toContain("query.ownerId = queryOwnerId");
    expect(indexSource).toContain('{ name: "OMI_ADAPTER_ID", value: context?.adapterId ?? "acp" }');
    expect(indexSource).not.toContain('{ name: "OMI_ADAPTER_ID", value: "acp" }');
  });
});
