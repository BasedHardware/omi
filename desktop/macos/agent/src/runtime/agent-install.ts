// Install guidance for agents the user named but hasn't connected.
//
// When an utterance names an agent that isn't registered, the kernel returns a
// `provider_unavailable` reject whose explanation reads "The explicitly
// requested provider is not registered in this runtime." That is accurate and
// useless: the user asked for Codex and gets a dead end.
//
// The guidance itself already existed — it was just unreachable. Windows
// Settings → Agents (`EXTERNAL_AGENT_GUIDES` in AgentsTab.tsx) has the install
// commands, docs links, and sign-in notes; nothing in the runtime could see
// them, so they never reached the one moment the user actually needed them.
// This module puts that table where the kernel can answer with it.
//
// The Windows renderer copy stays authoritative for its own UI; the parity test
// in tests/agent-install.test.ts fails if the two drift.

import type { MentionableAgentId } from "./agent-mention.js";

export interface AgentInstallGuide {
  readonly adapterId: MentionableAgentId;
  /** Name as spoken back to the user. */
  readonly displayName: string;
  /** Real shell commands to install the CLI. Empty when there is no one-liner. */
  readonly installCommands: readonly string[];
  /** Prose pointer used when there is no install command (e.g. Hermes). */
  readonly installNote?: string;
  /** Launch command Omi saves once the CLI is present. */
  readonly suggestedCommand: string;
  readonly docsUrl: string;
  /** How to sign in afterwards. Omi does not automate these logins. */
  readonly authNote: string;
}

/**
 * Only the externally installed agents appear here. `acp` (Claude Code) ships
 * built in and `pi-mono` is the managed cloud engine — neither is something the
 * user installs, so an "install it" answer would be wrong for both.
 */
const AGENT_INSTALL_GUIDES: Partial<Record<MentionableAgentId, AgentInstallGuide>> = {
  openclaw: {
    adapterId: "openclaw",
    displayName: "OpenClaw",
    installCommands: ["npm install -g openclaw@latest"],
    suggestedCommand: "openclaw acp",
    docsUrl: "https://docs.openclaw.ai/install",
    authNote: "After installing, sign in: run `openclaw onboard` in a terminal.",
  },
  hermes: {
    adapterId: "hermes",
    displayName: "Hermes",
    installCommands: [],
    installNote: "Install the Hermes CLI from its documentation.",
    suggestedCommand: "hermes acp",
    docsUrl: "https://hermes-agent.nousresearch.com/docs",
    authNote: "After installing, sign in: run `hermes login` in a terminal.",
  },
  codex: {
    adapterId: "codex",
    displayName: "Codex",
    installCommands: ["npm install -g @openai/codex"],
    suggestedCommand: "npx -y @agentclientprotocol/codex-acp",
    docsUrl: "https://github.com/agentclientprotocol/codex-acp",
    authNote: "Sign in with `codex login`, or add your OpenAI API key in Settings → Agents.",
  },
};

/** Display names for agents that are never user-installed. */
const BUILT_IN_DISPLAY_NAMES: Partial<Record<MentionableAgentId, string>> = {
  acp: "Claude Code",
  "pi-mono": "Omi AI",
};

export function agentDisplayName(adapterId: MentionableAgentId): string {
  return (
    AGENT_INSTALL_GUIDES[adapterId]?.displayName ??
    BUILT_IN_DISPLAY_NAMES[adapterId] ??
    adapterId
  );
}

/** The install guide for an agent, or undefined when it isn't user-installed. */
export function agentInstallGuide(
  adapterId: MentionableAgentId,
): AgentInstallGuide | undefined {
  return AGENT_INSTALL_GUIDES[adapterId];
}

export interface AgentUnavailableGuidance {
  readonly adapterId: MentionableAgentId;
  readonly displayName: string;
  /** One short paragraph, safe to speak aloud or render in the bar. */
  readonly message: string;
  /** Commands the surface can offer as copy buttons, in run order. */
  readonly commands: readonly string[];
  readonly docsUrl?: string;
}

/**
 * What to tell a user who asked for an agent that isn't connected.
 *
 * Built-in agents get a sign-in answer rather than an install answer, because
 * telling someone to `npm install` Claude Code would send them nowhere.
 */
export function agentUnavailableGuidance(
  adapterId: MentionableAgentId,
): AgentUnavailableGuidance {
  const displayName = agentDisplayName(adapterId);
  const guide = agentInstallGuide(adapterId);

  if (!guide) {
    return {
      adapterId,
      displayName,
      message: `${displayName} isn't available right now. Sign in and try again.`,
      commands: [],
    };
  }

  const install = guide.installCommands.length
    ? `Install it with \`${guide.installCommands.join("` then `")}\`.`
    : `${guide.installNote ?? `Install the ${displayName} CLI first.`}`;

  return {
    adapterId,
    displayName,
    message: `${displayName} isn't connected yet. ${install} ${guide.authNote} Then ask me again and I'll route this to ${displayName}.`,
    commands: [...guide.installCommands],
    docsUrl: guide.docsUrl,
  };
}
