// Picks a connected coding agent for a task when the user asks for "the best
// agent". This is a constraint-and-preference resolver, NOT a quality oracle:
// there is no reliable evidence any of these agents codes a generic task better
// than another, so we only claim a "best" when the task names a real, checkable
// need (a specific account, offline/local, persistent memory, read-only,
// notify-on-channel). Otherwise we fall back to the user's usual agent. Every
// pick carries a plain-language reason so the choice is never a black box.

import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export type RoutableAgentId = "acp" | "codex" | "hermes" | "openclaw";

// Neutral (alphabetical) order, used only for deterministic iteration. With the
// unique-capability constraints below a constraint never matches more than one
// agent, so this order does not privilege anyone.
const ROUTABLE_ORDER: readonly RoutableAgentId[] = ["acp", "codex", "hermes", "openclaw"];

interface AgentRoutingProfile {
  // Account/model the agent is locked to, if any.
  providerLock?: "anthropic" | "openai";
  // Can run a local/offline model (no cloud vendor required).
  offlineCapable: boolean;
  // Remembers facts/skills across sessions.
  persistentMemory: boolean;
  // Can deliver/notify over chat channels (Slack, Telegram, …).
  deliveryChannels: boolean;
}

// Verified against each agent's docs + the OpenLive registry (2026-07). acp is
// Omi's Claude Code adapter. Each flag is a capability the agent UNIQUELY has
// among these four, so a constraint that needs it names exactly one agent and
// no agent is favored by default.
const AGENT_ROUTING_PROFILES: Record<RoutableAgentId, AgentRoutingProfile> = {
  acp: { providerLock: "anthropic", offlineCapable: false, persistentMemory: false, deliveryChannels: false },
  codex: { providerLock: "openai", offlineCapable: false, persistentMemory: false, deliveryChannels: false },
  hermes: { offlineCapable: true, persistentMemory: true, deliveryChannels: false },
  openclaw: { offlineCapable: false, persistentMemory: false, deliveryChannels: true },
};

interface RoutingConstraint {
  reason: string;
  matches: (profile: AgentRoutingProfile) => boolean;
}

// Real, detectable signals in the task text. Order matters: an explicit account
// request wins over a softer need. Anything not here (plain "fix this bug",
// "refactor", a language) has NO honest signal and falls through to preference.
function detectConstraint(taskText: string): RoutingConstraint | null {
  const t = taskText.toLowerCase();
  if (/\b(?:use\s+)?(?:my\s+)?(?:claude|anthropic)\b/.test(t)) {
    return { reason: "you asked for Claude", matches: (p) => p.providerLock === "anthropic" };
  }
  if (/\b(?:use\s+)?(?:my\s+)?(?:chatgpt|openai|gpt)\b/.test(t)) {
    return { reason: "you asked for OpenAI", matches: (p) => p.providerLock === "openai" };
  }
  if (/\b(?:offline|air.?gapped|local(?:ly)?\s+model|private(?:ly)?|confidential|no\s+cloud|cheap|free|don'?t\s+(?:spend|burn))\b/.test(t)) {
    return { reason: "you asked to keep it offline/low-cost", matches: (p) => p.offlineCapable };
  }
  if (/\b(?:remember|ongoing|keep\s+track|like\s+(?:last\s+time|before))\b/.test(t)) {
    return { reason: "you want it remembered across sessions", matches: (p) => p.persistentMemory };
  }
  if (/\b(?:notify|message|text|dm|ping|send)\b[^.]*\b(?:slack|telegram|discord|whatsapp|imessage|signal)\b/.test(t)) {
    return { reason: "you asked to be notified on a chat channel", matches: (p) => p.deliveryChannels };
  }
  return null;
}

function orderedCandidates(connected: readonly string[]): RoutableAgentId[] {
  return ROUTABLE_ORDER.filter((id) => connected.includes(id));
}

// Signed-in check (verified paths, OpenLive registry 2026). A registered adapter
// is installed, but "connected" is not "signed in": an installed-but-unauthed
// agent would fail at run time. acp is Omi's managed Claude path and is always
// ready. This is what lets "best" fall back to another agent that actually works.
export function isAgentSignedIn(id: RoutableAgentId, home: string = homedir()): boolean {
  switch (id) {
    case "acp":
      return true;
    case "codex":
      return existsSync(join(home, ".codex", "auth.json"));
    case "hermes":
      return (
        existsSync(join(home, ".hermes", ".env"))
        || existsSync(join(home, ".hermes", "config.yaml"))
        || existsSync(join(home, ".hermes", "auth.json"))
      );
    case "openclaw":
      return existsSync(join(home, ".openclaw", "openclaw.json")) || existsSync(join(home, ".openclaw"));
  }
}

/// Resolve "the best agent" for a task. Returns null when no usable coding agent
/// is connected, so the caller falls back to Omi's own agent. `isReady` lets a
/// connected-but-not-signed-in agent be skipped in favor of one that works.
export function resolveBestAgent(input: {
  connected: readonly string[];
  taskText: string;
  preferred?: string;
  isReady?: (id: RoutableAgentId) => boolean;
}): { adapterId: RoutableAgentId; reason: string } | null {
  const candidates = orderedCandidates(input.connected);
  if (candidates.length === 0) return null;
  const ready = input.isReady ?? (() => true);

  const constraint = detectConstraint(input.taskText);
  if (constraint) {
    // A constraint names the one agent that can meet it. If it is not set up,
    // no other agent can substitute, so return it and let the setup-needed path
    // tell the user to finish setting it up.
    const match = candidates.find((id) => constraint.matches(AGENT_ROUTING_PROFILES[id]));
    if (match) return { adapterId: match, reason: constraint.reason };
  }

  // No real signal: use the user's usual agent if it is connected and set up.
  const preferred = candidates.find((id) => id === input.preferred);
  if (preferred) {
    if (ready(preferred)) return { adapterId: preferred, reason: "your usual agent" };
    // Preferred is connected but not signed in: fall back to another agent that is.
    const alt = candidates.find((id) => id !== preferred && ready(id));
    if (alt) return { adapterId: alt, reason: `${preferred} isn't set up, using this one instead` };
  }
  // No usable preference and no signal: let the caller use the owner's default.
  return null;
}
