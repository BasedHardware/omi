// Omi Provider Extension for pi-mono
//
// Responsibilities:
//   1. Register "omi" as an LLM provider using the OpenAI-compatible
//      completions API. All inference routes through the Rust desktop-backend
//      proxy for server-side cost tracking, model selection, and billing.
//   2. Install a "tool_call" handler that denies a small set of clearly
//      dangerous operations (privilege escalation, root-level deletes,
//      pipe-to-shell, destructive git, etc.) so tool execution is seamless
//      for normal work but cannot brick the user's machine on a single
//      hallucinated command.
//   3. Install a "tool_result" handler that appends every tool invocation
//      to a per-user audit log (~/.omi/pi-mono-audit.log) so we can review
//      what the agent actually ran.
//
// The classifier functions are exported so they can be unit-tested from
// plain Node (see index.test.ts). Pi's extension loader calls the default
// export with an ExtensionAPI instance; named exports are ignored by pi
// but picked up by the test runner.
//
// Issue #6594: Pi-mono harness with Omi API proxy for server-side cost control.

import type {
  ExtensionAPI,
  ToolCallEvent,
  ToolCallEventResult,
  ToolResultEvent,
} from "@mariozechner/pi-coding-agent";
import { appendFile, mkdir } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join } from "node:path";

// ---------------------------------------------------------------------------
// Denylist patterns
// ---------------------------------------------------------------------------

/** A single deny rule. `pattern` MUST match something clearly dangerous;
 *  `reason` is shown to the LLM so it can pick a safer alternative. */
interface DenyRule {
  pattern: RegExp;
  reason: string;
}

/** Lookahead for "end of this shell argument". Used so `/tmp` does NOT match
 *  `/` but `/` alone or `/ foo` does. */
const TARGET_END = `(?=\\s|$|[;&|'"])`;

/** Composed pattern for "a shell argument that names a root or system-owned
 *  path, or the whole user home". Used by rm / chmod / chown rules. */
const DANGEROUS_TARGET =
  `(?:` +
  // `/` alone (root)
  `\\/${TARGET_END}` +
  // `/*` glob at root
  `|\\/\\*` +
  // `/System`, `/System/foo`, `/Library`, `/usr`, `/etc`, etc.
  `|\\/(?:System|Library|usr|etc|bin|sbin|private)(?:\\/[^\\s;&|'"]*)?${TARGET_END}` +
  // bare `~` or `~/`
  `|~\\/?${TARGET_END}` +
  // bare `$HOME` or `$HOME/`
  `|\\$HOME\\/?${TARGET_END}` +
  // `${HOME}` / `${HOME}/`
  `|\\$\\{HOME\\}\\/?${TARGET_END}` +
  // nested parent traversal (common accidental root-escape)
  `|\\.\\.\\/\\.\\.` +
  `)`;

/** `rm` flag cluster that includes both `-r` (recursive) and `-f` (force),
 *  in any order. Accepts `-rf`, `-fr`, `-Rf`, `-RFv`, `-r -f`, etc. */
const RM_RF_FLAGS =
  `(?:-[a-zA-Z]*[rR][a-zA-Z]*[fF][a-zA-Z]*|-[a-zA-Z]*[fF][a-zA-Z]*[rR][a-zA-Z]*|-[rR]\\s+-[fF]|-[fF]\\s+-[rR])`;

/** Bash command denylist. Allow-by-default: only block on explicit match. */
const BASH_DENY_RULES: DenyRule[] = [
  {
    // sudo / doas / pkexec / su — at start, after a shell operator, inside
    // $(...) or backticks. `echo sudo` is intentionally not blocked.
    pattern: /(?:^|[;&|`]|\$\()\s*(?:sudo|doas|pkexec|su\s)/,
    reason:
      "Privilege escalation (sudo/doas/pkexec/su) is blocked by the Omi " +
      "pi-mono denylist. Perform the operation as your current user or ask " +
      "the user to run the command manually.",
  },
  {
    // rm -rf / rm -fr / rm -r -f targeting root, home, or OS dirs.
    pattern: new RegExp(
      `\\brm\\s+${RM_RF_FLAGS}\\b[^\\n]*?\\s${DANGEROUS_TARGET}`
    ),
    reason:
      "Recursive force-delete targeting a root or system path is blocked. " +
      "Use a specific subdirectory under the working tree, or delete the " +
      "exact file by path.",
  },
  {
    // mkfs.*, dd of=/dev/disk..., fork bomb, shred -fuv /...
    pattern:
      /\bmkfs(?:\.|\s)|\bdd\s+[^\n]*\bof=\/dev\/(?:disk|sd[a-z]|nvme|rdisk)|:\(\)\s*\{\s*:\|\s*:\s*&\s*\}\s*;\s*:|\bshred\s+[^\n]*\s\//,
    reason:
      "Low-level filesystem destruction (mkfs/dd to disk/shred/fork bomb) " +
      "is blocked.",
  },
  {
    // Shell redirect into OS paths: `> /etc/hosts`, `>> /System/...`, `> /dev/disk2`.
    // `\d*` suffixes let us match `/dev/disk2`, `/dev/sda1`, `/dev/nvme0n1`, etc.
    pattern:
      />>?\s*\/(?:System|Library(?!\/Caches|\/Application Support\/com\.omi)|usr(?!\/local)|etc|bin|sbin|dev\/(?:disk\d*|sd[a-z]\d*|nvme\d*(?:n\d+)?|rdisk\d*|hd[a-z]\d*))\b/,
    reason:
      "Redirecting shell output into a system path (/System, /Library, " +
      "/usr, /etc, /bin, /sbin, /dev/disk*) is blocked. Use the write tool " +
      "with a path under the project or $HOME instead.",
  },
  {
    // shutdown/reboot/halt/poweroff.
    pattern: /\b(?:shutdown|reboot|halt|poweroff)\b/,
    reason:
      "Shutting down or rebooting the host is blocked. Ask the user to " +
      "restart manually if that is really what they want.",
  },
  {
    // Destructive git: force push, hard reset to a remote ref.
    pattern:
      /\bgit\s+push\s+(?:-f\b|--force\b|--force-with-lease\b)|\bgit\s+reset\s+--hard\s+(?:origin\/|upstream\/|remotes\/)/,
    reason:
      "Destructive git operation (force-push, hard reset to remote) is " +
      "blocked. Create a new commit on a feature branch instead.",
  },
  {
    // curl/wget/fetch piped directly into a shell. Still allows writing the
    // script to a file for review first.
    pattern: /\b(?:curl|wget|fetch|aria2c)\b[^\n|]*\|\s*(?:bash|sh|zsh|fish|dash|ksh)\b/,
    reason:
      "Piping a downloaded script straight into a shell is blocked. " +
      "Download the script to a file, review it, then run it.",
  },
  {
    // launchctl touching system domain.
    pattern:
      /\blaunchctl\s+(?:bootout|kickstart|unload|load|enable|disable)\s+system\//,
    reason:
      "Modifying system launchd services is blocked. Use `launchctl ... " +
      "gui/$(id -u)/...` for the user domain if you need a LaunchAgent.",
  },
  {
    // chmod/chown on root or system-owned trees.
    pattern: new RegExp(
      `\\b(?:chmod|chown)\\s+(?:-R\\s+)?[^\\s\\n]+\\s${DANGEROUS_TARGET}`
    ),
    reason:
      "Recursive chmod/chown targeting a root or system path is blocked. " +
      "Apply permissions to specific files under the project tree.",
  },
];

/** Write/edit path denylist. Absolute paths under OS-owned trees and
 *  well-known credential files are blocked. */
const WRITE_PATH_DENY_RULES: DenyRule[] = [
  {
    pattern: /^\/System\//,
    reason: "Writing under /System is blocked (SIP-protected OS tree).",
  },
  {
    pattern: /^\/Library\/(?!Caches\/|Application Support\/com\.omi)/,
    reason:
      "Writing under /Library is blocked except for Omi-owned subpaths. " +
      "Use ~/Library/... for user-scoped state.",
  },
  {
    pattern: /^\/usr\/(?!local\/)/,
    reason: "Writing under /usr is blocked (system binaries/libraries).",
  },
  {
    pattern: /^\/(?:private\/)?etc\//,
    reason: "Writing under /etc is blocked (system configuration).",
  },
  {
    pattern: /^\/(?:bin|sbin)\//,
    reason: "Writing under /bin or /sbin is blocked (system binaries).",
  },
  {
    pattern: /\/\.ssh\/(?:authorized_keys|id_[^/]+)$/,
    reason:
      "Writing SSH private keys or authorized_keys is blocked. Ask the " +
      "user to manage their SSH credentials manually.",
  },
  {
    pattern:
      /\/\.aws\/credentials$|\/\.config\/gcloud\/application_default_credentials\.json$|\/\.kube\/config$/,
    reason:
      "Writing cloud credential files (AWS, gcloud, kubeconfig) is blocked.",
  },
];

// ---------------------------------------------------------------------------
// Classifier functions (pure, exported for unit tests)
// ---------------------------------------------------------------------------

export interface DenyDecision {
  blocked: true;
  reason: string;
}

/** Classify a bash command. Returns null when allowed. */
export function classifyBash(command: string): DenyDecision | null {
  if (typeof command !== "string" || command.length === 0) return null;
  for (const rule of BASH_DENY_RULES) {
    if (rule.pattern.test(command)) {
      return { blocked: true, reason: rule.reason };
    }
  }
  return null;
}

/** Classify a write/edit target path. Returns null when allowed. */
export function classifyFileWrite(path: string): DenyDecision | null {
  if (typeof path !== "string" || path.length === 0) return null;
  for (const rule of WRITE_PATH_DENY_RULES) {
    if (rule.pattern.test(path)) {
      return { blocked: true, reason: rule.reason };
    }
  }
  return null;
}

/** Classify a whole tool_call event by dispatching on toolName. */
export function inspectToolCall(event: ToolCallEvent): DenyDecision | null {
  switch (event.toolName) {
    case "bash": {
      const command = (event.input as { command?: unknown })?.command;
      return typeof command === "string" ? classifyBash(command) : null;
    }
    case "write":
    case "edit":
    case "edit-diff": {
      const path = (event.input as { path?: unknown })?.path;
      return typeof path === "string" ? classifyFileWrite(path) : null;
    }
    default:
      // read, grep, find, ls, and custom tools pass through unchanged.
      return null;
  }
}

// ---------------------------------------------------------------------------
// Audit log
// ---------------------------------------------------------------------------

interface AuditEntry {
  ts: string;
  phase: "before" | "after";
  tool: string;
  decision: "allow" | "deny" | "ok" | "error";
  reason?: string;
  summary: string;
}

/** One-line redacted summary of a tool-call input for the audit log. */
export function summarizeInput(event: ToolCallEvent): string {
  const { toolName, input } = event;
  try {
    switch (toolName) {
      case "bash": {
        const cmd = (input as { command?: string })?.command ?? "";
        return truncate(cmd, 200);
      }
      case "write":
      case "edit":
      case "edit-diff":
        return (input as { path?: string })?.path ?? "";
      case "read":
        return (input as { path?: string })?.path ?? "";
      case "grep":
        return truncate(
          `${(input as { pattern?: string })?.pattern ?? ""} @ ${
            (input as { path?: string })?.path ?? "."
          }`,
          200
        );
      case "find":
        return truncate(
          `${(input as { pattern?: string })?.pattern ?? ""} @ ${
            (input as { path?: string })?.path ?? "."
          }`,
          200
        );
      case "ls":
        return (input as { path?: string })?.path ?? "";
      default:
        return truncate(JSON.stringify(input ?? {}), 200);
    }
  } catch {
    return `<unserializable ${toolName} input>`;
  }
}

function truncate(s: string, max: number): string {
  if (s.length <= max) return s;
  return s.slice(0, max - 1) + "…";
}

/** Resolve the audit log path. Overridable via OMI_PI_AUDIT_LOG for tests. */
function auditLogPath(): string {
  return (
    process.env.OMI_PI_AUDIT_LOG ||
    join(process.env.HOME || homedir(), ".omi", "pi-mono-audit.log")
  );
}

let auditWarned = false;
/** Append a single JSONL line to the audit log. Never throws; on failure,
 *  logs to stderr once per process so we don't flood on disk-full. */
async function appendAudit(entry: AuditEntry): Promise<void> {
  const path = auditLogPath();
  const line = JSON.stringify(entry) + "\n";
  try {
    await mkdir(dirname(path), { recursive: true });
    await appendFile(path, line, "utf-8");
  } catch (err) {
    if (!auditWarned) {
      auditWarned = true;
      const msg = err instanceof Error ? err.message : String(err);
      process.stderr.write(
        `[omi-provider] audit log unavailable (${msg}); continuing without audit\n`
      );
    }
  }
}

// ---------------------------------------------------------------------------
// Extension entry point
// ---------------------------------------------------------------------------

export default function omiProvider(pi: ExtensionAPI): void {
  const baseUrl = process.env.OMI_API_BASE_URL || "https://api.omi.me/v2";
  const apiKey = process.env.OMI_API_KEY || "";

  pi.registerProvider("omi", {
    api: "openai-completions",
    baseUrl,
    apiKey,
    models: [
      {
        id: "omi-sonnet",
        name: "Omi Sonnet",
        reasoning: true,
        input: ["text"],
        contextWindow: 200_000,
        maxTokens: 16_384,
        // Cost set to 0 client-side — tracked server-side by the backend
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
      },
      {
        id: "omi-opus",
        name: "Omi Opus",
        reasoning: true,
        input: ["text"],
        contextWindow: 200_000,
        maxTokens: 16_384,
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
      },
    ],
  });

  pi.on("tool_call", async (event): Promise<ToolCallEventResult | void> => {
    let decision: DenyDecision | null = null;
    try {
      decision = inspectToolCall(event);
    } catch (err) {
      // Never let classifier bugs block execution. Fail-open for the
      // denylist and log the error through the audit channel.
      const msg = err instanceof Error ? err.message : String(err);
      void appendAudit({
        ts: new Date().toISOString(),
        phase: "before",
        tool: event.toolName,
        decision: "error",
        reason: `classifier threw: ${msg}`,
        summary: summarizeInput(event),
      });
      return undefined;
    }

    void appendAudit({
      ts: new Date().toISOString(),
      phase: "before",
      tool: event.toolName,
      decision: decision ? "deny" : "allow",
      reason: decision?.reason,
      summary: summarizeInput(event),
    });

    if (decision) {
      return { block: true, reason: decision.reason };
    }
    return undefined;
  });

  pi.on("tool_result", async (event: ToolResultEvent): Promise<void> => {
    void appendAudit({
      ts: new Date().toISOString(),
      phase: "after",
      tool: event.toolName,
      decision: event.isError ? "error" : "ok",
      summary: summarizeInput({
        type: "tool_call",
        toolName: event.toolName,
        toolCallId: event.toolCallId,
        input: event.input,
      } as ToolCallEvent),
    });
  });
}
