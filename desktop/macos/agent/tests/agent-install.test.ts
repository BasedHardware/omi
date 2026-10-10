import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  agentDisplayName,
  agentInstallGuide,
  agentUnavailableGuidance,
} from "../src/runtime/agent-install.js";

describe("agent install guidance", () => {
  it("answers a named-but-missing agent with something the user can act on", () => {
    const guidance = agentUnavailableGuidance("codex");

    expect(guidance.displayName).toBe("Codex");
    expect(guidance.message).toContain("isn't connected yet");
    expect(guidance.message).toContain("npm install -g @openai/codex");
    expect(guidance.message).toContain("codex login");
    expect(guidance.commands).toEqual(["npm install -g @openai/codex"]);
    expect(guidance.docsUrl).toBe("https://github.com/agentclientprotocol/codex-acp");
  });

  it("never leaves the user at the dead end the kernel reject produces today", () => {
    // The reject explanation is "The explicitly requested provider is not
    // registered in this runtime." Guidance must beat that on every agent.
    for (const adapterId of ["codex", "hermes", "openclaw"] as const) {
      const { message, displayName } = agentUnavailableGuidance(adapterId);
      expect(message).toContain(displayName);
      expect(message).not.toContain("not registered in this runtime");
      expect(message.length).toBeGreaterThan(40);
    }
  });

  it("falls back to prose when an agent has no install one-liner", () => {
    const guidance = agentUnavailableGuidance("hermes");

    expect(guidance.commands).toEqual([]);
    expect(guidance.message).toContain("Install the Hermes CLI from its documentation.");
    expect(guidance.message).toContain("hermes login");
  });

  it("tells built-in agents to sign in rather than to install something", () => {
    for (const adapterId of ["acp", "pi-mono"] as const) {
      expect(agentInstallGuide(adapterId)).toBeUndefined();

      const { message } = agentUnavailableGuidance(adapterId);
      expect(message).toContain("Sign in");
      expect(message).not.toContain("npm install");
    }

    expect(agentDisplayName("acp")).toBe("Claude Code");
    expect(agentDisplayName("pi-mono")).toBe("Omi AI");
  });

  // The same three agents are described in Windows Settings → Agents. Install
  // commands, launch commands, and docs links are load-bearing facts: if one
  // side is corrected and the other isn't, a user gets told to run a command
  // that no longer works. Prose (authNote) is deliberately not compared — the
  // renderer says "add your API key below", which means nothing when the answer
  // is spoken aloud, so the runtime rewords it.
  it("does not drift from the Windows agent guides", () => {
    const agentsTabPath = fileURLToPath(
      new URL(
        "../../../windows/src/renderer/src/components/settings/tabs/AgentsTab.tsx",
        import.meta.url,
      ),
    );
    if (!existsSync(agentsTabPath)) {
      // Single-platform checkout; nothing to compare against.
      return;
    }
    const agentsTabSource = readFileSync(agentsTabPath, "utf8");

    for (const adapterId of ["codex", "hermes", "openclaw"] as const) {
      const guide = agentInstallGuide(adapterId);
      expect(guide, `${adapterId} must have an install guide`).toBeDefined();

      for (const command of guide!.installCommands) {
        expect(agentsTabSource, `${adapterId} install command drifted`).toContain(command);
      }
      expect(agentsTabSource, `${adapterId} launch command drifted`).toContain(
        guide!.suggestedCommand,
      );
      expect(agentsTabSource, `${adapterId} docs url drifted`).toContain(guide!.docsUrl);
    }
  });
});
