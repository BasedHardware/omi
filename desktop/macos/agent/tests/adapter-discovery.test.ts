import { chmodSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  adapterCommandForExecutable,
  discoverAdapterCommand,
} from "../src/runtime/adapter-discovery.js";

describe("adapter discovery", () => {
  let home: string;

  beforeEach(() => {
    home = mkdtempSync(join(tmpdir(), "adapter-discovery-"));
  });

  afterEach(() => {
    rmSync(home, { recursive: true, force: true });
  });

  function installExecutable(relativeDir: string, name: string): string {
    const dir = join(home, relativeDir);
    mkdirSync(dir, { recursive: true });
    const path = join(dir, name);
    writeFileSync(path, "#!/bin/sh\nexit 0\n");
    chmodSync(path, 0o755);
    return path;
  }

  it("returns the existing env command without searching", () => {
    const env = { HOME: home, PATH: "", OMI_HERMES_ADAPTER_COMMAND: "'/usr/bin/hermes' acp" };
    expect(discoverAdapterCommand("hermes", env)).toBe("'/usr/bin/hermes' acp");
  });

  it("returns undefined when the executable is missing", () => {
    const env = { HOME: home, PATH: "" };
    expect(discoverAdapterCommand("hermes", env)).toBeUndefined();
    expect(env.OMI_HERMES_ADAPTER_COMMAND).toBeUndefined();
  });

  it("discovers a freshly installed hermes and seeds the env command", () => {
    const hermes = installExecutable(".local/bin", "hermes");
    const env: NodeJS.ProcessEnv = { HOME: home, PATH: "" };
    expect(discoverAdapterCommand("hermes", env)).toBe(`'${hermes}' acp`);
    expect(env.OMI_HERMES_ADAPTER_COMMAND).toBe(`'${hermes}' acp`);
  });

  it("discovers codex on PATH without an acp suffix", () => {
    const codex = installExecutable("bin", "codex");
    const env: NodeJS.ProcessEnv = { HOME: home, PATH: join(home, "bin") };
    expect(discoverAdapterCommand("codex", env)).toBe(`'${codex}'`);
  });

  it("prefers a sibling node binary for openclaw", () => {
    const openclaw = installExecutable(".openclaw/bin", "openclaw");
    const node = installExecutable(".openclaw/bin", "node");
    expect(adapterCommandForExecutable("openclaw", openclaw)).toBe(`'${node}' '${openclaw}' acp`);
  });

  it("falls back to direct openclaw invocation without a sibling node", () => {
    const openclaw = installExecutable(".openclaw/bin", "openclaw");
    expect(adapterCommandForExecutable("openclaw", openclaw)).toBe(`'${openclaw}' acp`);
  });
});
