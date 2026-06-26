import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  adapterActivationEnv,
  adapterIdForHarnessMode,
  adapterIsActivated,
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
  });

  it("keeps activation separate from implementation", () => {
    expect(adapterActivationEnv("acp")).toBeUndefined();
    expect(adapterActivationEnv("pi-mono")).toBe("OMI_AUTH_TOKEN");
    expect(adapterActivationEnv("hermes")).toBe("OMI_HERMES_ADAPTER_COMMAND");
    expect(adapterActivationEnv("openclaw")).toBe("OMI_OPENCLAW_ADAPTER_COMMAND");

    expect(adapterIsActivated("acp", {})).toBe(true);
    expect(adapterIsActivated("hermes", {})).toBe(false);
    expect(adapterIsActivated("hermes", { OMI_HERMES_ADAPTER_COMMAND: "  " })).toBe(false);
    expect(adapterIsActivated("hermes", { OMI_HERMES_ADAPTER_COMMAND: "hermes-adapter" })).toBe(true);
    expect(adapterIsActivated("openclaw", { OMI_OPENCLAW_ADAPTER_COMMAND: "openclaw-adapter" })).toBe(true);
  });

  it("source: daemon registers Hermes/OpenClaw explicitly and does not stamp MCP env as ACP", () => {
    const indexSource = readFileSync(new URL("../src/index.ts", import.meta.url), "utf8");

    expect(indexSource).toContain("adapterIdForHarnessMode(defaultHarnessMode)");
    expect(indexSource).toContain('defaultAdapterId === "acp"');
    expect(indexSource).toContain("ensureHermesAdapter");
    expect(indexSource).toContain("ensureOpenClawAdapter");
    expect(indexSource).toContain("OMI_HERMES_ADAPTER_COMMAND");
    expect(indexSource).toContain("OMI_OPENCLAW_ADAPTER_COMMAND");
    expect(indexSource).toContain('{ name: "OMI_ADAPTER_ID", value: context?.adapterId ?? "acp" }');
    expect(indexSource).not.toContain('{ name: "OMI_ADAPTER_ID", value: "acp" }');
  });
});
