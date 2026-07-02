// Agent selector — the capability broker that routes a task to the best
// available coding agent, with an ordered fallback chain, explicit-mention
// override, and install detection.
//
// This is the "Scheduler + capability broker" that docs/doc/developer/
// agent-control-plane.mdx reserves: Omi is the control plane, and the runtime
// adapters (Claude Code/acp, Codex, Hermes, OpenClaw, pi-mono) are execution
// adapters beneath it. Selection here is pure and deterministic so it is fully
// unit-testable; the LLM voice classifier upstream may pass an explicit
// category/agent which this module honors.

import { type ProductionAdapterId } from "../adapters/interface.js";

/** Agent ids as seen by the router — identical to the runtime adapter ids. */
export type AgentId = ProductionAdapterId; // "acp" | "pi-mono" | "hermes" | "openclaw" | "codex"

/** Task categories the selector reasons about. */
export type TaskCategory =
  | "codebase_edit"
  | "shell_ops"
  | "research"
  | "long_autonomous"
  | "messaging"
  | "general";

export interface AgentDescriptor {
  id: AgentId;
  displayName: string;
  /** Lowercased spoken/typed forms used to detect an explicit request. */
  aliases: string[];
}

export const AGENT_DESCRIPTORS: Record<AgentId, AgentDescriptor> = {
  acp: {
    id: "acp",
    displayName: "Claude Code",
    aliases: ["claude code", "claude-code", "claudecode", "claude", "anthropic"],
  },
  codex: {
    id: "codex",
    displayName: "Codex",
    aliases: ["codex", "openai codex", "open ai codex"],
  },
  hermes: {
    id: "hermes",
    displayName: "Hermes",
    aliases: ["hermes", "nous", "nous research"],
  },
  openclaw: {
    id: "openclaw",
    displayName: "OpenClaw",
    aliases: ["openclaw", "open claw"],
  },
  "pi-mono": {
    id: "pi-mono",
    displayName: "Omi AI",
    aliases: ["omi ai", "omi", "pi-mono", "pimono"],
  },
};

/**
 * Capability scores 0..3 per (agent, category). Higher = better fit.
 * Rationale:
 *  - Claude Code (acp) / Codex: strongest at codebase edits + shell.
 *  - Codex especially strong at shell/exec (autonomous `codex exec`).
 *  - Hermes / OpenClaw: multi-channel + long-running/scheduled autonomy + messaging.
 *  - Omi AI (pi-mono): the always-available general default.
 */
const CAPABILITY_SCORES: Record<AgentId, Record<TaskCategory, number>> = {
  acp: { codebase_edit: 3, shell_ops: 2, research: 2, long_autonomous: 2, messaging: 0, general: 3 },
  codex: { codebase_edit: 3, shell_ops: 3, research: 1, long_autonomous: 2, messaging: 0, general: 2 },
  hermes: { codebase_edit: 2, shell_ops: 2, research: 2, long_autonomous: 3, messaging: 3, general: 2 },
  openclaw: { codebase_edit: 2, shell_ops: 2, research: 2, long_autonomous: 3, messaging: 3, general: 2 },
  "pi-mono": { codebase_edit: 2, shell_ops: 2, research: 2, long_autonomous: 1, messaging: 1, general: 3 },
};

/** Deterministic tiebreak order when scores are equal and no user default applies. */
const DEFAULT_PRIORITY: AgentId[] = ["acp", "codex", "hermes", "openclaw", "pi-mono"];

export interface InstallInfo {
  displayName: string;
  docsUrl: string;
  /** Per-platform install command. */
  commands: { darwin: string; linux: string; win32: string };
  /** Executable name to probe on PATH when detecting availability. */
  detectBinary: string;
}

export const AGENT_INSTALL_INFO: Record<AgentId, InstallInfo | null> = {
  acp: {
    displayName: "Claude Code",
    docsUrl: "https://docs.anthropic.com/en/docs/claude-code",
    commands: {
      darwin: "npm install -g @anthropic-ai/claude-code",
      linux: "npm install -g @anthropic-ai/claude-code",
      win32: "npm install -g @anthropic-ai/claude-code",
    },
    detectBinary: "claude",
  },
  codex: {
    displayName: "Codex",
    docsUrl: "https://developers.openai.com/codex/cli",
    commands: {
      darwin: "npm install -g @openai/codex",
      linux: "npm install -g @openai/codex",
      win32: "npm install -g @openai/codex",
    },
    detectBinary: "codex",
  },
  hermes: {
    displayName: "Hermes",
    docsUrl: "https://hermes-agent.nousresearch.com",
    commands: {
      darwin: "curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash",
      linux: "curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash",
      win32: "iex (irm https://hermes-agent.nousresearch.com/install.ps1)",
    },
    detectBinary: "hermes",
  },
  openclaw: {
    displayName: "OpenClaw",
    docsUrl: "https://docs.openclaw.ai/install",
    commands: {
      darwin: "curl -fsSL https://openclaw.ai/install.sh | bash",
      linux: "curl -fsSL https://openclaw.ai/install.sh | bash",
      win32: "iwr -useb https://openclaw.ai/install.ps1 | iex",
    },
    detectBinary: "openclaw",
  },
  // Omi AI runs inside the desktop app — nothing to install.
  "pi-mono": null,
};

export function installCommandFor(
  agent: AgentId,
  platform: NodeJS.Platform = process.platform
): string | undefined {
  const info = AGENT_INSTALL_INFO[agent];
  if (!info) return undefined;
  if (platform === "darwin") return info.commands.darwin;
  if (platform === "win32") return info.commands.win32;
  return info.commands.linux;
}

function aliasMatches(text: string, alias: string): boolean {
  const escaped = alias.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  // Whole-phrase, boundary-aware match (tolerates surrounding punctuation/spaces).
  const re = new RegExp(`(^|[^a-z0-9])${escaped}([^a-z0-9]|$)`, "i");
  return re.test(text);
}

/**
 * Detect an agent the user explicitly named in the task. Longest alias wins so
 * "use claude code" resolves to Claude Code even though "claude" also matches.
 */
export function detectExplicitAgent(taskText: string): AgentId | undefined {
  const text = taskText.toLowerCase();
  let best: { id: AgentId; len: number } | undefined;
  for (const desc of Object.values(AGENT_DESCRIPTORS)) {
    for (const alias of desc.aliases) {
      if (aliasMatches(text, alias) && (!best || alias.length > best.len)) {
        best = { id: desc.id, len: alias.length };
      }
    }
  }
  return best?.id;
}

/** Rule-based task classifier. An upstream LLM classifier may override via SelectionInput.category. */
export function classifyTask(taskText: string): TaskCategory {
  const t = taskText.toLowerCase();
  const has = (...words: string[]): boolean => words.some((w) => t.includes(w));

  if (
    has(
      "message",
      "text ",
      "reply",
      "respond to",
      "dm ",
      "whatsapp",
      "telegram",
      "imessage",
      "signal",
      "slack",
      "discord"
    )
  )
    return "messaging";
  if (
    has(
      "overnight",
      "keep working",
      "keep going",
      "monitor",
      "every hour",
      "on a schedule",
      "scheduled",
      "while i sleep",
      "long-running",
      "autonomously",
      "in the background"
    )
  )
    return "long_autonomous";
  if (has("research", "look up", "find out", "search the web", "investigate", "gather info", "summarize the")) return "research";
  if (
    has(
      "run ",
      "shell",
      "command",
      "terminal",
      "install",
      "npm ",
      "pip ",
      "git ",
      "build ",
      "compile",
      "deploy",
      "docker"
    )
  )
    return "shell_ops";
  if (
    has(
      "code",
      "refactor",
      "implement",
      "fix the",
      "bug",
      "function",
      "class ",
      "test",
      "repo",
      "file",
      "edit ",
      "write a",
      "add a",
      "feature",
      "endpoint"
    )
  )
    return "codebase_edit";
  return "general";
}

export interface SelectionInput {
  taskText: string;
  /** Connected/installed agents (from LocalAgentProviderDetector). */
  available: AgentId[];
  /** The user's preferred default (e.g. chatBridgeMode); used only for tiebreaks. */
  userDefault?: AgentId;
  /** Optional overrides from an upstream classifier / explicit UI choice. */
  category?: TaskCategory;
  explicitAgent?: AgentId;
}

export type SelectionOutcome =
  | {
      kind: "selected";
      primary: AgentId;
      /** Ordered fallback chain including the primary as chain[0]. */
      chain: AgentId[];
      category: TaskCategory;
      explicit: boolean;
      reason: string;
    }
  | {
      kind: "needs_install";
      agent: AgentId;
      category: TaskCategory;
      installCommand?: string;
      docsUrl?: string;
      reason: string;
    };

function rankAgents(agents: AgentId[], category: TaskCategory, userDefault?: AgentId): AgentId[] {
  const unique = [...new Set(agents)];
  return unique.sort((a, b) => {
    const scoreDelta = CAPABILITY_SCORES[b][category] - CAPABILITY_SCORES[a][category];
    if (scoreDelta !== 0) return scoreDelta; // higher score first
    if (userDefault) {
      if (a === userDefault) return -1;
      if (b === userDefault) return 1;
    }
    return DEFAULT_PRIORITY.indexOf(a) - DEFAULT_PRIORITY.indexOf(b);
  });
}

/**
 * Select the best agent for a task.
 *  - Explicit mention wins; if that agent is not connected, returns needs_install
 *    (we never silently reroute an explicit request).
 *  - Otherwise ranks connected agents by capability score for the task category,
 *    returning an ordered fallback chain.
 *  - If nothing is connected, falls back to Omi AI (pi-mono), the built-in default.
 */
export function selectAgent(input: SelectionInput): SelectionOutcome {
  const category = input.category ?? classifyTask(input.taskText);
  const explicit = input.explicitAgent ?? detectExplicitAgent(input.taskText);

  if (explicit) {
    if (!input.available.includes(explicit)) {
      return {
        kind: "needs_install",
        agent: explicit,
        category,
        installCommand: installCommandFor(explicit),
        docsUrl: AGENT_INSTALL_INFO[explicit]?.docsUrl,
        reason: `${AGENT_DESCRIPTORS[explicit].displayName} was requested but is not connected.`,
      };
    }
    const rest = rankAgents(
      input.available.filter((a) => a !== explicit),
      category,
      input.userDefault
    );
    return {
      kind: "selected",
      primary: explicit,
      chain: [explicit, ...rest],
      category,
      explicit: true,
      reason: `Requested ${AGENT_DESCRIPTORS[explicit].displayName}.`,
    };
  }

  const ranked = rankAgents(input.available, category, input.userDefault);
  if (ranked.length === 0) {
    return {
      kind: "selected",
      primary: "pi-mono",
      chain: ["pi-mono"],
      category,
      explicit: false,
      reason: "No external agents connected; using Omi AI.",
    };
  }
  return {
    kind: "selected",
    primary: ranked[0],
    chain: ranked,
    category,
    explicit: false,
    reason: `Best fit for ${category}: ${AGENT_DESCRIPTORS[ranked[0]].displayName}.`,
  };
}

/**
 * Advance a fallback chain after an attempt with `failed` fails. Returns the
 * next agent to try, or undefined if the chain is exhausted.
 */
export function nextInChain(chain: AgentId[], failed: AgentId): AgentId | undefined {
  const idx = chain.indexOf(failed);
  if (idx < 0) return undefined;
  return chain[idx + 1];
}

/**
 * Whether an agent failure should trigger trying the next agent in the chain.
 * User-actionable failures (cancel, auth needed, quota) are NOT retried on another
 * agent; startup / execution / tooling failures are.
 */
export function isRetryableAgentFailure(message: string): boolean {
  const m = (message || "").toLowerCase();
  if (
    m.includes("cancel") ||
    m.includes("aborted") ||
    m.includes("auth") ||
    m.includes("unauthorized") ||
    m.includes("quota") ||
    m.includes("rate limit")
  ) {
    return false;
  }
  return true;
}

export interface FailoverPlan {
  next: AgentId;
  message: string;
}

/**
 * Decide the next agent to try after `failed` errored, with a transparent, user-facing
 * message ("Codex hit an error, trying Claude Code instead."). Returns null when the
 * error is user-actionable or the chain is exhausted.
 */
export function planFailover(chain: AgentId[], failed: AgentId, errorMessage: string): FailoverPlan | null {
  if (!isRetryableAgentFailure(errorMessage)) return null;
  const next = nextInChain(chain, failed);
  if (!next) return null;
  return {
    next,
    message: `${AGENT_DESCRIPTORS[failed].displayName} hit an error, trying ${AGENT_DESCRIPTORS[next].displayName} instead.`,
  };
}

// ---------------------------------------------------------------------------
// STT-robust agent-name resolution
//
// Nik tests Track 1 by VOICE. Speech-to-text mangles the agent names badly:
// "openclaw" -> "open claw" / "open flaw" / "open clause", "hermes" -> "her mees",
// "codex" -> "code decks" / "codecs", "claude code" -> "cloud code". A strict
// string match drops those. This resolver fuzzy-matches a short spoken token to
// the intended agent so the task still routes to what the user actually said.
// ---------------------------------------------------------------------------

/** Curated spoken variants + common STT mishears per agent (lowercased). */
export const AGENT_SPEECH_VARIANTS: Record<AgentId, string[]> = {
  acp: ["claude code", "claude", "cloud code", "clawed", "claude cody", "cloud claude", "anthropic", "cloud"],
  codex: ["codex", "code x", "codecs", "code decks", "codeex", "kodex", "code ex", "codaks", "codecks", "openai codex"],
  hermes: ["hermes", "her mees", "hermies", "hermez", "hermeez", "hermees", "hermus", "airmess", "nous"],
  openclaw: ["openclaw", "open claw", "open flaw", "open clause", "open close", "opencloud", "claw", "lobster"],
  "pi-mono": ["omi ai", "omi", "pi mono", "pimono", "oh me", "omee"],
};

export interface SpokenAgentMatch {
  agent: AgentId;
  confidence: number; // 0..1
  matched: string;
}

function levenshtein(a: string, b: string): number {
  const m = a.length;
  const n = b.length;
  if (m === 0) return n;
  if (n === 0) return m;
  let prev = Array.from({ length: n + 1 }, (_, i) => i);
  let curr = new Array<number>(n + 1);
  for (let i = 1; i <= m; i++) {
    curr[0] = i;
    for (let j = 1; j <= n; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      curr[j] = Math.min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost);
    }
    [prev, curr] = [curr, prev];
  }
  return prev[n];
}

function similarity(a: string, b: string): number {
  if (a === b) return 1;
  const maxLen = Math.max(a.length, b.length);
  if (maxLen === 0) return 1;
  if (Math.min(a.length, b.length) < 3) return 0; // too short to fuzzy-match safely
  return 1 - levenshtein(a, b) / maxLen;
}

/**
 * Resolve a (possibly mangled) spoken agent name to an agent id. Intended for the
 * short `provider` token the voice model extracts, not a whole task. Tries exact
 * variant matches first, then fuzzy matches over unigrams, bigrams, de-spaced
 * bigrams, and the whole de-spaced phrase. Returns null when nothing clears the bar.
 */
export function resolveSpokenAgent(text: string, minConfidence = 0.68): SpokenAgentMatch | null {
  const normalized = text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!normalized) return null;

  const words = normalized.split(" ");
  const candidates = new Set<string>();
  for (let i = 0; i < words.length; i++) {
    candidates.add(words[i]);
    if (i + 1 < words.length) {
      candidates.add(`${words[i]} ${words[i + 1]}`);
      candidates.add(`${words[i]}${words[i + 1]}`);
    }
  }
  candidates.add(normalized);
  candidates.add(normalized.replace(/\s+/g, ""));

  let best: SpokenAgentMatch | null = null;
  for (const [agentId, variants] of Object.entries(AGENT_SPEECH_VARIANTS) as [AgentId, string[]][]) {
    for (const variant of variants) {
      const variantDespaced = variant.replace(/\s+/g, "");
      for (const cand of candidates) {
        if (cand === variant || cand === variantDespaced) {
          if (!best || best.confidence < 1) best = { agent: agentId, confidence: 1, matched: cand };
          continue;
        }
        const sim = Math.max(similarity(cand, variant), similarity(cand.replace(/\s+/g, ""), variantDespaced));
        if (sim >= minConfidence && (!best || sim > best.confidence)) {
          best = { agent: agentId, confidence: sim, matched: cand };
        }
      }
    }
  }
  return best;
}
