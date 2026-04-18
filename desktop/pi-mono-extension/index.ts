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

import {
  defineTool,
  type ExtensionAPI,
  type ToolCallEvent,
  type ToolCallEventResult,
  type ToolResultEvent,
} from "@mariozechner/pi-coding-agent";
import { Type } from "@mariozechner/pi-ai";
import { appendFile, mkdir } from "node:fs/promises";
import { homedir } from "node:os";
import { createConnection, type Socket } from "node:net";
import { dirname, join, resolve } from "node:path";

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

/** Optional leading shell-quote absorber used before a DANGEROUS_TARGET.
 *  Handles bare, `"`, `'`, ANSI-C quoting (`$'...'`), and locale strings
 *  (`$"..."`), so all of `rm /etc/hosts`, `rm "/etc/hosts"`, `rm '/etc/hosts'`,
 *  `rm $'/etc/hosts'`, and `rm $"/etc/hosts"` match the same way. Closing
 *  quote is handled by TARGET_END which already accepts `'` and `"`. */
const TARGET_QUOTE = `(?:\\$['"]|['"])?`;

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

/** Bash command denylist. Allow-by-default: only block on explicit match. */
const BASH_DENY_RULES: DenyRule[] = [
  {
    // sudo / doas / pkexec / su — at start of line, after a newline, after a
    // shell operator (`;`, `&`, `|`, backtick), or as the head of a subshell
    // (`(cmd)` or `$(cmd)`). `echo "sudo is fun"` is intentionally not blocked
    // because the `"` is not a shell-command separator.
    pattern: /(?:^|[\n;&|`(]|\$\()\s*(?:sudo|doas|pkexec|su\s)/,
    reason:
      "Privilege escalation (sudo/doas/pkexec/su) is blocked by the Omi " +
      "pi-mono denylist. Perform the operation as your current user or ask " +
      "the user to run the command manually.",
  },
  {
    // `rm` targeting a root, system, or home path — ANY flag combination
    // (short `-rf` / `-fr` / `-r -f`, long `--recursive --force`, or no flags
    // at all). A single-file `rm /etc/hosts` is just as destructive as
    // `rm -rf /etc`, so the rule blocks on target, not on flag cluster.
    // `TARGET_QUOTE` absorbs an optional leading shell quote (`"`, `'`, `$'`,
    // `$"`) so `rm "/etc/hosts"`, `rm '/etc/hosts'`, `rm $'/etc/hosts'`, and
    // `rm "$HOME"` are all caught.
    pattern: new RegExp(`\\brm\\b[^\\n]*?\\s${TARGET_QUOTE}${DANGEROUS_TARGET}`),
    reason:
      "Deleting a root or system path with `rm` is blocked. Use a specific " +
      "subdirectory under the working tree, or delete the exact file by path.",
  },
  {
    // Destructive command with command/process substitution. We cannot
    // statically evaluate `$(...)`, backticks, or `<(...)` so their target
    // is unknowable to the classifier — block them outright for rm/chmod/
    // chown so `chmod 000 "$(echo /)"` and `rm $(find / -name hosts)` cannot
    // slip past the DANGEROUS_TARGET matcher. The model is instructed to
    // resolve the substitution itself and pass a literal path instead.
    pattern: /\b(?:rm|chmod|chown)\b[^\n]*?(?:\$\(|`|<\()/,
    reason:
      "Command or process substitution ($(...), `...`, <(...)) with " +
      "rm/chmod/chown is blocked — the classifier cannot statically verify " +
      "the target is safe. Resolve the substitution yourself and pass a " +
      "literal path.",
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
    // `(?:\$['"]|['"])?` absorbs an optional leading shell quote (`"`, `'`,
    // `$'`, `$"`) so `> "/etc/hosts"`, `> '/etc/hosts'`, and `> $'/etc/hosts'`
    // are all blocked just like their unquoted forms.
    pattern:
      />>?\s*(?:\$['"]|['"])?\/(?:System|Library(?!\/Caches|\/Application Support\/com\.omi)|usr(?!\/local)|etc|bin|sbin|dev\/(?:disk\d*|sd[a-z]\d*|nvme\d*(?:n\d+)?|rdisk\d*|hd[a-z]\d*))\b/,
    reason:
      "Redirecting shell output into a system path (/System, /Library, " +
      "/usr, /etc, /bin, /sbin, /dev/disk*) is blocked. Use the write tool " +
      "with a path under the project or $HOME instead.",
  },
  {
    // Redirect target uses command/process substitution. `>"$(...)"`,
    // `> \`...\``, and `> <(...)` cannot be statically verified so we block
    // them outright rather than try to evaluate the substitution.
    pattern: />>?\s*['"]?(?:\$\(|`|<\()/,
    reason:
      "Redirect target uses command or process substitution — the " +
      "classifier cannot statically verify the destination is safe. Use a " +
      "literal path under the project or $HOME.",
  },
  {
    // shutdown/reboot/halt/poweroff.
    pattern: /\b(?:shutdown|reboot|halt|poweroff)\b/,
    reason:
      "Shutting down or rebooting the host is blocked. Ask the user to " +
      "restart manually if that is really what they want.",
  },
  {
    // Destructive git: force push (with any positional args before the force
    // flag, e.g. `git push origin HEAD --force`), hard reset to a remote ref.
    pattern:
      /\bgit\s+push\b[^\n]*?\s(?:-f\b|--force\b|--force-with-lease\b)|\bgit\s+reset\s+--hard\s+(?:origin\/|upstream\/|remotes\/)/,
    reason:
      "Destructive git operation (force-push, hard reset to remote) is " +
      "blocked. Create a new commit on a feature branch instead.",
  },
  {
    // curl/wget/fetch piped directly into a shell — allow an optional path
    // prefix on the shell target (`/bin/sh`, `/usr/bin/bash`, `~/bin/zsh`).
    // Still allows writing the script to a file for review first.
    pattern:
      /\b(?:curl|wget|fetch|aria2c)\b[^\n|]*\|\s*(?:[^\s|;&<>]*\/)?(?:bash|sh|zsh|fish|dash|ksh)\b/,
    reason:
      "Piping a downloaded script straight into a shell is blocked. " +
      "Download the script to a file, review it, then run it.",
  },
  {
    // launchctl touching system domain. Covers both legacy positional syntax
    // `launchctl unload system/com.x` (system/<id>) and the newer
    // `launchctl bootstrap system /Library/LaunchDaemons/x.plist` (system as
    // its own domain token followed by a service path).
    pattern:
      /\blaunchctl\s+(?:bootout|bootstrap|kickstart|unload|load|enable|disable)\s+system\b/,
    reason:
      "Modifying system launchd services is blocked. Use `launchctl ... " +
      "gui/$(id -u)/...` for the user domain if you need a LaunchAgent.",
  },
  {
    // chmod/chown on root or system-owned trees — ANY flags (`-R -v`, long
    // form, or none) before the dangerous target. `TARGET_QUOTE` absorbs an
    // optional leading shell quote (`"`, `'`, `$'`, `$"`) so
    // `chmod 000 "/"`, `chmod 000 '/'`, `chmod 000 $'/'`, and
    // `chown root "$HOME"` are all caught.
    pattern: new RegExp(
      `\\b(?:chmod|chown)\\b[^\\n]*?\\s${TARGET_QUOTE}${DANGEROUS_TARGET}`
    ),
    reason:
      "Changing permissions or ownership of a root or system path is " +
      "blocked. Apply permissions to specific files under the project tree.",
  },
  {
    // Shell redirect into SSH or cloud credential files. Mirrors the
    // WRITE_PATH_DENY_RULES entries but catches `echo ... > ~/.ssh/id_rsa`
    // style bash-only attacks that the write/edit tool denylist does not see.
    pattern:
      />>?\s*(?:[^\s|;&<>()`]*\/)?(?:\.ssh\/(?:authorized_keys|id_[^\s/;&|'"`]+)|\.aws\/credentials|\.config\/gcloud\/application_default_credentials\.json|\.kube\/config)\b/,
    reason:
      "Redirecting shell output into SSH keys (authorized_keys, id_*) or " +
      "cloud credential files (~/.aws/credentials, gcloud ADC, ~/.kube/" +
      "config) is blocked.",
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

/** Collapse purely syntactic bash noise so multi-line or line-continued
 *  commands classify the same as their canonical single-line form. Currently
 *  this folds `\<newline>` (bash line continuation) into a single space so the
 *  redirect / target rules see `echo bad > "/etc/hosts"` whether the user
 *  wrote it on one line or split it across two. Line continuations have no
 *  semantic meaning in bash — they are purely a source-code layout tool —
 *  so this normalization cannot produce a false positive. */
function normalizeBashCommand(command: string): string {
  return command.replace(/\\\n/g, " ");
}

/** Classify a bash command. Returns null when allowed. */
export function classifyBash(command: string): DenyDecision | null {
  if (typeof command !== "string" || command.length === 0) return null;
  const normalized = normalizeBashCommand(command);
  for (const rule of BASH_DENY_RULES) {
    if (rule.pattern.test(normalized)) {
      return { blocked: true, reason: rule.reason };
    }
  }
  return null;
}

/** Classify a write/edit target path. Returns null when allowed.
 *  Resolves relative and `..` segments before matching so that
 *  `../../../../etc/hosts` is caught the same way as `/etc/hosts`. */
export function classifyFileWrite(filePath: string): DenyDecision | null {
  if (typeof filePath !== "string" || filePath.length === 0) return null;
  // Resolve to absolute to prevent ../../../etc/hosts traversal bypass
  const resolved = resolve(filePath);
  for (const rule of WRITE_PATH_DENY_RULES) {
    if (rule.pattern.test(resolved)) {
      return { blocked: true, reason: rule.reason };
    }
  }
  return null;
}

/** Classify a whole tool_call event by dispatching on toolName.
 *  When OMI_YOLO_MODE=1, all tool calls are allowed (no denylist).
 *  Yolo mode is gated by the adapter — only forwarded from dev builds. */
export function inspectToolCall(event: ToolCallEvent): DenyDecision | null {
  if (process.env.OMI_YOLO_MODE === "1") {
    process.stderr.write(`[omi-provider] YOLO bypass: ${event.toolName}\n`);
    return null;
  }
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

export interface AuditEntry {
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

/** Test-only: reset the `auditWarned` one-shot so tests can assert the
 *  stderr warning fires exactly once per process. Not called from
 *  production code. */
export function __resetAuditWarnedForTest(): void {
  auditWarned = false;
}

/** Append a single JSONL line to the audit log. Never throws; on failure,
 *  logs to stderr once per process so we don't flood on disk-full. Exported
 *  so the fail-safe (EACCES / ENOTDIR / disk-full) can be unit tested. */
export async function appendAudit(entry: AuditEntry): Promise<void> {
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
// Omi tools — forwarded to Swift via Unix socket (OMI_BRIDGE_PIPE)
// ---------------------------------------------------------------------------

let omiPipeConnection: Socket | null = null;
let omiPipeBuffer = "";
let omiCallIdCounter = 0;
const omiPendingCalls = new Map<string, { resolve: (result: string) => void }>();

function connectOmiPipe(pipePath: string): Promise<void> {
  return new Promise((resolve, reject) => {
    omiPipeConnection = createConnection(pipePath, () => {
      process.stderr.write(`[omi-tools] Connected to bridge pipe\n`);
      resolve();
    });
    omiPipeConnection.on("data", (data: Buffer) => {
      omiPipeBuffer += data.toString();
      let idx;
      while ((idx = omiPipeBuffer.indexOf("\n")) >= 0) {
        const line = omiPipeBuffer.slice(0, idx);
        omiPipeBuffer = omiPipeBuffer.slice(idx + 1);
        if (line.trim()) {
          try {
            const msg = JSON.parse(line);
            if (msg.type === "tool_result" && msg.callId) {
              const pending = omiPendingCalls.get(msg.callId);
              if (pending) {
                pending.resolve(msg.result);
                omiPendingCalls.delete(msg.callId);
              }
            }
          } catch { /* ignore malformed messages */ }
        }
      }
    });
    omiPipeConnection.on("error", (err) => {
      process.stderr.write(`[omi-tools] Pipe error: ${err.message}\n`);
      reject(err);
    });
    // Handle pipe close — resolve all pending tool calls with an error
    // so they don't hang forever if the bridge disconnects mid-call.
    omiPipeConnection.on("close", () => {
      process.stderr.write("[omi-tools] Pipe disconnected\n");
      omiPipeConnection = null;
      for (const [, pending] of omiPendingCalls) {
        pending.resolve("Error: Omi bridge disconnected");
      }
      omiPendingCalls.clear();
    });
  });
}

function callSwiftTool(name: string, input: Record<string, unknown>, signal?: AbortSignal): Promise<string> {
  if (!omiPipeConnection) return Promise.resolve("Error: not connected to Omi bridge");
  if (signal?.aborted) return Promise.resolve("Error: tool call aborted");
  const callId = `omi-ext-${++omiCallIdCounter}-${Date.now()}`;
  return new Promise<string>((resolve) => {
    const timer = setTimeout(() => {
      omiPendingCalls.delete(callId);
      resolve(`Error: tool '${name}' timed out after ${OMI_TOOL_TIMEOUT_MS / 1000}s`);
    }, OMI_TOOL_TIMEOUT_MS);
    const cleanup = () => {
      clearTimeout(timer);
      omiPendingCalls.delete(callId);
      resolve("Error: tool call aborted");
    };
    signal?.addEventListener("abort", cleanup, { once: true });
    omiPendingCalls.set(callId, {
      resolve: (result: string) => {
        clearTimeout(timer);
        signal?.removeEventListener("abort", cleanup);
        resolve(result);
      },
    });
    omiPipeConnection!.write(JSON.stringify({ type: "tool_use", callId, name, input }) + "\n");
  });
}

export const OMI_TOOL_TIMEOUT_MS = 30_000;

// ---------------------------------------------------------------------------
// Omi tool definitions — pi-mono defineTool() with TypeBox schemas
// ---------------------------------------------------------------------------

/** Factory: create a defineTool()-compliant Omi tool that forwards to Swift. */
function omiTool<T extends Parameters<typeof Type.Object>[0]>(spec: {
  name: string;
  label: string;
  description: string;
  promptSnippet: string;
  promptGuidelines?: string[];
  properties: T;
  required: (keyof T)[];
}) {
  return defineTool({
    name: spec.name,
    label: spec.label,
    description: spec.description,
    promptSnippet: spec.promptSnippet,
    promptGuidelines: spec.promptGuidelines,
    parameters: Type.Object(
      spec.properties,
      { additionalProperties: false },
    ),
    async execute(_toolCallId, params, signal) {
      const result = await callSwiftTool(spec.name, params as Record<string, unknown>, signal);
      return { content: [{ type: "text" as const, text: result }], details: undefined };
    },
  });
}

export const OMI_TOOLS = [
  omiTool({
    name: "execute_sql",
    label: "Execute SQL",
    description: "Run SQL on the user's local omi.db SQLite database. Use for app usage stats, screen time, activity counts, task lookups, aggregations. Read-only (SELECT only). Key tables: screenshots, transcription_sessions, action_items, memories, staged_tasks, focus_sessions, observations, goals, indexed_files.",
    promptSnippet: "execute_sql - Query the user's local omi.db SQLite database (SELECT only)",
    promptGuidelines: [
      "Use execute_sql for quantitative queries (counts, sums, date ranges, aggregations).",
      "Use semantic_search instead for fuzzy or conceptual queries about screen content.",
    ],
    properties: {
      query: Type.String({ description: "SQL query to execute" }),
    },
    required: ["query"],
  }),
  omiTool({
    name: "semantic_search",
    label: "Semantic Search",
    description: "Vector similarity search on the user's screen history. Use for fuzzy/conceptual queries about what the user saw on their computer.",
    promptSnippet: "semantic_search - Search screen history by meaning",
    promptGuidelines: [
      "Prefer semantic_search over execute_sql when the user asks about something they 'saw' or 'looked at'.",
    ],
    properties: {
      query: Type.String({ description: "Natural language search query" }),
      days: Type.Optional(Type.Number({ description: "Days to search back (default 7)" })),
      app_filter: Type.Optional(Type.String({ description: "Filter to a specific app" })),
    },
    required: ["query"],
  }),
  omiTool({
    name: "get_daily_recap",
    label: "Daily Recap",
    description: "Pre-formatted daily activity recap: app usage, conversations, tasks, focus, memories, observations.",
    promptSnippet: "get_daily_recap - Get a daily activity summary",
    properties: {
      days_ago: Type.Optional(Type.Number({ description: "0=today, 1=yesterday, 7=past week" })),
    },
    required: [],
  }),
  omiTool({
    name: "search_tasks",
    label: "Search Tasks",
    description: "Vector similarity search on tasks. Find tasks by meaning or topic.",
    promptSnippet: "search_tasks - Find tasks by meaning",
    properties: {
      query: Type.String({ description: "Natural language task description" }),
      include_completed: Type.Optional(Type.Boolean({ description: "Include completed tasks" })),
    },
    required: ["query"],
  }),
  omiTool({
    name: "complete_task",
    label: "Complete Task",
    description: "Toggle a task's completion status. Syncs to backend.",
    promptSnippet: "complete_task - Mark a task as complete/incomplete",
    properties: {
      task_id: Type.String({ description: "backendId from action_items" }),
    },
    required: ["task_id"],
  }),
  omiTool({
    name: "delete_task",
    label: "Delete Task",
    description: "Delete a task permanently. Syncs to backend.",
    promptSnippet: "delete_task - Delete a task permanently",
    properties: {
      task_id: Type.String({ description: "backendId from action_items" }),
    },
    required: ["task_id"],
  }),
  omiTool({
    name: "get_conversations",
    label: "Get Conversations",
    description: "Retrieve user conversations with summaries, action items, metadata. Use for time-based queries or recaps.",
    promptSnippet: "get_conversations - Retrieve conversations by date range",
    properties: {
      start_date: Type.Optional(Type.String({ description: "ISO date with timezone" })),
      end_date: Type.Optional(Type.String({ description: "ISO date with timezone" })),
      limit: Type.Optional(Type.Number({ description: "Default 20" })),
      offset: Type.Optional(Type.Number()),
      include_transcript: Type.Optional(Type.Boolean({ description: "Load speaker data" })),
    },
    required: [],
  }),
  omiTool({
    name: "search_conversations",
    label: "Search Conversations",
    description: "Semantic search across conversations. Use for specific events or topics.",
    promptSnippet: "search_conversations - Find conversations about a topic",
    properties: {
      query: Type.String({ description: "Event or topic to search for" }),
      start_date: Type.Optional(Type.String()),
      end_date: Type.Optional(Type.String()),
      limit: Type.Optional(Type.Number({ description: "Default 5, max 20" })),
      include_transcript: Type.Optional(Type.Boolean()),
    },
    required: ["query"],
  }),
  omiTool({
    name: "get_memories",
    label: "Get Memories",
    description: "Retrieve user memories — facts, preferences, habits. Use for 'what do you know about me?' type questions.",
    promptSnippet: "get_memories - Retrieve stored facts and preferences",
    properties: {
      limit: Type.Optional(Type.Number({ description: "Default 50" })),
      offset: Type.Optional(Type.Number()),
      start_date: Type.Optional(Type.String()),
      end_date: Type.Optional(Type.String()),
    },
    required: [],
  }),
  omiTool({
    name: "search_memories",
    label: "Search Memories",
    description: "Semantic search across user memories. Find memories about a topic using AI embeddings.",
    promptSnippet: "search_memories - Find memories about a topic",
    properties: {
      query: Type.String({ description: "Topic to search for" }),
      limit: Type.Optional(Type.Number({ description: "Default 5, max 20" })),
    },
    required: ["query"],
  }),
  omiTool({
    name: "get_action_items",
    label: "Get Action Items",
    description: "Retrieve user tasks from Omi backend. Filter by completion status or due date.",
    promptSnippet: "get_action_items - Retrieve tasks",
    properties: {
      limit: Type.Optional(Type.Number()),
      offset: Type.Optional(Type.Number()),
      completed: Type.Optional(Type.Boolean({ description: "true=done, false=pending" })),
      start_date: Type.Optional(Type.String()),
      end_date: Type.Optional(Type.String()),
      due_start_date: Type.Optional(Type.String()),
      due_end_date: Type.Optional(Type.String()),
    },
    required: [],
  }),
  omiTool({
    name: "create_action_item",
    label: "Create Action Item",
    description: "Create a new task. Use when user explicitly asks to add a task.",
    promptSnippet: "create_action_item - Create a new task",
    properties: {
      description: Type.String({ description: "Short task description" }),
      due_at: Type.Optional(Type.String({ description: "Due date ISO" })),
      conversation_id: Type.Optional(Type.String()),
    },
    required: ["description"],
  }),
  omiTool({
    name: "update_action_item",
    label: "Update Action Item",
    description: "Update task status, description, or due date.",
    promptSnippet: "update_action_item - Update an existing task",
    properties: {
      action_item_id: Type.String({ description: "Task ID (required)" }),
      completed: Type.Optional(Type.Boolean()),
      description: Type.Optional(Type.String()),
      due_at: Type.Optional(Type.String()),
    },
    required: ["action_item_id"],
  }),
  omiTool({
    name: "capture_screen",
    label: "Capture Screen",
    description: "Capture a screenshot of the user's current screen. Returns the file path to the saved JPEG image. Use the Read tool to view the image after capturing.",
    promptSnippet: "capture_screen - Take a screenshot of the user's current screen",
    promptGuidelines: [
      "Call capture_screen when the user asks about what's on their screen or what they're looking at.",
      "After capture_screen returns a file path, use Read to view the image.",
      "Do NOT use bash screencapture — always use this tool instead.",
    ],
    properties: {},
    required: [],
  }),
];

async function registerOmiTools(pi: ExtensionAPI): Promise<void> {
  const pipePath = process.env.OMI_BRIDGE_PIPE;
  if (!pipePath) {
    process.stderr.write("[omi-tools] OMI_BRIDGE_PIPE not set — Omi tools unavailable\n");
    return;
  }
  try {
    await connectOmiPipe(pipePath);
  } catch (err) {
    process.stderr.write(`[omi-tools] Failed to connect: ${err instanceof Error ? err.message : err}\n`);
    return;
  }
  for (const tool of OMI_TOOLS) {
    pi.registerTool(tool);
  }
  process.stderr.write(`[omi-tools] Registered ${OMI_TOOLS.length} Omi tools\n`);
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
        input: ["text", "image"],
        contextWindow: 200_000,
        maxTokens: 16_384,
        // Cost set to 0 client-side — tracked server-side by the backend
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
      },
      {
        id: "omi-opus",
        name: "Omi Opus",
        reasoning: true,
        input: ["text", "image"],
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

  // Register Omi-specific tools (execute_sql, semantic_search, etc.)
  // These forward to Swift via the OMI_BRIDGE_PIPE Unix socket.
  void registerOmiTools(pi);
}

// ---------------------------------------------------------------------------
// Test-only exports — relay internals for unit tests
// ---------------------------------------------------------------------------

/** Test-only: connect the pipe relay to a socket path. */
export const __connectOmiPipeForTest = connectOmiPipe;

/** Test-only: call a Swift tool through the pipe relay. */
export const __callSwiftToolForTest = callSwiftTool;

/** Test-only: access to pending calls map for assertions. */
export const __omiPendingCallsForTest = omiPendingCalls;

/** Test-only: reset pipe state between tests. */
export function __resetOmiPipeForTest(): void {
  if (omiPipeConnection) {
    omiPipeConnection.destroy();
    omiPipeConnection = null;
  }
  omiPipeBuffer = "";
  omiCallIdCounter = 0;
  omiPendingCalls.clear();
}
