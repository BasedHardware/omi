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
} from "@earendil-works/pi-coding-agent";
import { Type } from "@earendil-works/pi-ai";
import { appendFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { createConnection, type Socket } from "node:net";
import { dirname, join, resolve } from "node:path";
import { isSafeSkillName, loadSkillInstructions } from "../agent/src/runtime/node-tools.ts";
import {
  buildToolAvailabilitySnapshot,
  toolNamesForAdapter,
  toolsForAdapter,
  type OmiToolInputSchema,
  type OmiToolManifestEntry,
} from "../agent/src/runtime/omi-tool-manifest.ts";

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
const omiPendingCalls = new Map<string, { connection: Socket; resolve: (result: string) => void }>();

function connectOmiPipe(pipePath: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const connection = createConnection(pipePath, () => {
      process.stderr.write(`[omi-tools] Connected to bridge pipe\n`);
      resolve();
    });
    omiPipeConnection = connection;
    connection.on("data", (data: Buffer) => {
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
    connection.on("error", (err) => {
      process.stderr.write(`[omi-tools] Pipe error: ${err.message}\n`);
      reject(err);
    });
    // Handle pipe close — resolve all pending tool calls with an error
    // so they don't hang forever if the bridge disconnects mid-call.
    connection.on("close", () => {
      process.stderr.write("[omi-tools] Pipe disconnected\n");
      if (omiPipeConnection === connection) {
        omiPipeConnection = null;
        for (const [callId, pending] of omiPendingCalls) {
          if (pending.connection === connection) {
            pending.resolve("Error: Omi bridge disconnected");
            omiPendingCalls.delete(callId);
          }
        }
      }
    });
  });
}

async function callSwiftTool(name: string, input: Record<string, unknown>, signal?: AbortSignal, timeoutMs = OMI_TOOL_TIMEOUT_MS): Promise<string> {
  const connection: Socket | null = omiPipeConnection;
  if (!connection) return Promise.resolve("Error: not connected to Omi bridge");
  if (signal?.aborted) return Promise.resolve("Error: tool call aborted");
  const callId = `omi-ext-${++omiCallIdCounter}-${Date.now()}`;
  const correlation = await omiRelayCorrelation();
  if (correlation.disableSwiftBackedTools === true) {
    return Promise.resolve("Error: Swift-backed Omi tools are disabled for this control-created run");
  }
  if (signal?.aborted) return Promise.resolve("Error: tool call aborted");
  if (omiPipeConnection !== connection) return Promise.resolve("Error: Omi bridge disconnected");
  return new Promise<string>((resolve) => {
    const timer = setTimeout(() => {
      omiPendingCalls.delete(callId);
      resolve(`Error: tool '${name}' timed out after ${timeoutMs / 1000}s`);
    }, timeoutMs);
    const cleanup = () => {
      clearTimeout(timer);
      omiPendingCalls.delete(callId);
      resolve("Error: tool call aborted");
    };
    signal?.addEventListener("abort", cleanup, { once: true });
    omiPendingCalls.set(callId, {
      connection,
      resolve: (result: string) => {
        clearTimeout(timer);
        signal?.removeEventListener("abort", cleanup);
        resolve(result);
      },
    });
    connection.write(JSON.stringify({
      type: "tool_use",
      callId,
      name,
      input,
      ...correlation,
    }) + "\n");
  });
}

async function omiRelayCorrelation(): Promise<Record<string, string | number | boolean>> {
  const correlation: Record<string, string | number | boolean> = {};
  if (process.env.OMI_ADAPTER_ID) correlation.adapterId = process.env.OMI_ADAPTER_ID;
  if (process.env.OMI_REQUEST_ID) correlation.requestId = process.env.OMI_REQUEST_ID;
  if (process.env.OMI_CLIENT_ID) correlation.clientId = process.env.OMI_CLIENT_ID;
  if (process.env.OMI_SESSION_ID) correlation.sessionId = process.env.OMI_SESSION_ID;
  if (process.env.OMI_RUN_ID) correlation.runId = process.env.OMI_RUN_ID;
  if (process.env.OMI_ATTEMPT_ID) correlation.attemptId = process.env.OMI_ATTEMPT_ID;
  if (process.env.OMI_ADAPTER_SESSION_ID) correlation.adapterSessionId = process.env.OMI_ADAPTER_SESSION_ID;
  correlation.protocolVersion = 2;
  Object.assign(correlation, await omiContextFileCorrelation());
  return correlation;
}

async function omiContextFileCorrelation(): Promise<Record<string, string | number | boolean>> {
  const path = process.env.OMI_CONTEXT_FILE;
  if (!path) return {};
  try {
    const parsed = JSON.parse(await readFile(path, "utf8")) as Record<string, unknown>;
    const correlation: Record<string, string | number | boolean> = {};
    for (const key of [
      "adapterId",
      "requestId",
      "clientId",
      "sessionId",
      "runId",
      "attemptId",
      "adapterSessionId",
    ]) {
      const value = parsed[key];
      if (typeof value === "string" && value.length > 0) correlation[key] = value;
    }
    correlation.protocolVersion = 2;
    if (parsed.disableSwiftBackedTools === true) correlation.disableSwiftBackedTools = true;
    return correlation;
  } catch {
    return {};
  }
}

export const OMI_TOOL_TIMEOUT_MS = 30_000;
export const OMI_LONG_CONTROL_TOOL_TIMEOUT_MS = 10 * 60_000;

export { isSafeSkillName };

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
  timeoutMs?: number;
}) {
  const parameters = Type.Object(
    spec.properties,
    { additionalProperties: false },
  );
  const tool = defineTool({
    name: spec.name,
    label: spec.label,
    description: spec.description,
    promptSnippet: spec.promptSnippet,
    promptGuidelines: spec.promptGuidelines,
    parameters,
    async execute(_toolCallId, params, signal) {
      const result = await callSwiftTool(spec.name, params as Record<string, unknown>, signal, spec.timeoutMs);
      return { content: [{ type: "text" as const, text: result }], details: undefined };
    },
  });
  Object.defineProperty(tool, "__omiTimeoutMsForTest", {
    value: spec.timeoutMs ?? OMI_TOOL_TIMEOUT_MS,
    enumerable: false,
  });
  return tool;
}

function typeBoxSchemaForJsonSchema(schema: Record<string, unknown>): unknown {
  const options: Record<string, unknown> = {};
  if (typeof schema.description === "string") options.description = schema.description;
  if (Array.isArray(schema.enum)) options.enum = schema.enum;
  switch (schema.type) {
    case "string":
      return Type.String(options);
    case "number":
    case "integer":
      return Type.Number(options);
    case "boolean":
      return Type.Boolean(options);
    case "array": {
      const itemSchema = schema.items && typeof schema.items === "object"
        ? typeBoxSchemaForJsonSchema(schema.items as Record<string, unknown>)
        : Type.Unknown();
      return Type.Array(itemSchema as never, options);
    }
    case "object": {
      const properties = typeof schema.properties === "object" && schema.properties
        ? typeBoxPropertiesForInputSchema({
            type: "object",
            properties: schema.properties as Record<string, unknown>,
            required: Array.isArray(schema.required) ? schema.required as string[] : [],
            additionalProperties: schema.additionalProperties === true,
          })
        : {};
      return Type.Object(properties, { ...options, additionalProperties: schema.additionalProperties === true });
    }
    default:
      return Type.Unknown(options);
  }
}

function typeBoxPropertiesForInputSchema(tool: OmiToolInputSchema): Parameters<typeof Type.Object>[0] {
  const required = new Set(tool.required ?? []);
  return Object.fromEntries(
    Object.entries(tool.properties).map(([name, property]) => {
      const schema = typeBoxSchemaForJsonSchema(property as Record<string, unknown>);
      return [name, required.has(name) ? schema : Type.Optional(schema as never)];
    })
  ) as Parameters<typeof Type.Object>[0];
}

function omiManifestTool(tool: OmiToolManifestEntry) {
  return omiTool({
    name: tool.name,
    label: tool.label,
    description: tool.description,
    promptSnippet: tool.promptSnippet,
    promptGuidelines: tool.promptGuidelines,
    properties: typeBoxPropertiesForInputSchema(tool.inputSchema),
    required: (tool.inputSchema.required ?? []) as never[],
    timeoutMs: tool.timeoutClass === "long" ? OMI_LONG_CONTROL_TOOL_TIMEOUT_MS : OMI_TOOL_TIMEOUT_MS,
  });
}

function loadSkillTool() {
  return defineTool({
    name: "load_skill",
    label: "Load Skill",
    description: "Load the full instructions for a named skill listed in available_skills.",
    promptSnippet: "load_skill - Load the full SKILL.md instructions for an available skill",
    parameters: Type.Object({
      name: Type.String({ description: "Skill name exactly as listed in available_skills" }),
    }, { additionalProperties: false }),
    async execute(_toolCallId, params) {
      const name = String((params as { name?: unknown }).name ?? "").trim();
      if (!isSafeSkillName(name)) {
        return {
          content: [{
            type: "text" as const,
            text: "Invalid skill name. Use the exact skill name listed in available_skills.",
          }],
          details: undefined,
        };
      }
      return {
        content: [{
          type: "text" as const,
          text: await loadSkillInstructions(name),
        }],
        details: undefined,
      };
    },
  });
}

const executionRole = process.env.OMI_EXECUTION_ROLE === "leaf" ? "leaf" : "coordinator";
const projectionContext = { executionRole } as const;

export function omiToolsForExecutionRole(role: "coordinator" | "leaf") {
  return toolsForAdapter("pi-mono", { executionRole: role }).map((tool) => (
    tool.executor.kind === "nodeTool" ? loadSkillTool() : omiManifestTool(tool)
  ));
}

export const OMI_TOOLS = omiToolsForExecutionRole(executionRole);

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
  const snapshot = buildToolAvailabilitySnapshot("pi-mono", projectionContext);
  if (process.env.OMI_TOOL_AVAILABILITY_SNAPSHOT_PATH) {
    try {
      await writeFile(process.env.OMI_TOOL_AVAILABILITY_SNAPSHOT_PATH, `${JSON.stringify(snapshot, null, 2)}\n`);
    } catch (err) {
      process.stderr.write(
        `[omi-tools] Failed to write tool availability snapshot: ${err instanceof Error ? err.message : err}\n`,
      );
    }
  }
  process.stderr.write(
    `[omi-tools] adapter=pi-mono advertisedToolCount=${snapshot.advertisedToolCount} advertisedTools=${snapshot.advertisedToolNames.join(",")}\n`,
  );
}

export async function __registerOmiToolsForTest(pi: ExtensionAPI): Promise<void> {
  await registerOmiTools(pi);
}

// ---------------------------------------------------------------------------
// Extension entry point
// ---------------------------------------------------------------------------

export default function omiProvider(pi: ExtensionAPI): void {
  const baseUrl = process.env.OMI_API_BASE_URL || "https://api.omi.me/v2";
  const apiKey = process.env.OMI_API_KEY || "";

  // BYOK: the Swift app sets OMI_BYOK_* env vars (all four, or none) when the user
  // is on the free plan with their own provider keys. Attach them as X-BYOK-*
  // headers on every request to the omi backend so it (a) applies the request-level
  // all-four-keys paywall exemption and (b) routes inference through the user's own
  // Anthropic key instead of Omi's server key. We only attach the complete set —
  // the backend's has_all_byok_keys() requires all four to be present.
  const byokMap: Array<[string, string]> = [
    ["OMI_BYOK_OPENAI", "X-BYOK-OpenAI"],
    ["OMI_BYOK_ANTHROPIC", "X-BYOK-Anthropic"],
    ["OMI_BYOK_GEMINI", "X-BYOK-Gemini"],
    ["OMI_BYOK_DEEPGRAM", "X-BYOK-Deepgram"],
  ];
  const byokHeaders: Record<string, string> = {};
  for (const [envName, headerName] of byokMap) {
    const value = process.env[envName];
    if (value && value.length > 0) byokHeaders[headerName] = value;
  }
  const byokActive = Object.keys(byokHeaders).length === byokMap.length;
  if (byokActive) {
    process.stderr.write(`[omi-provider] BYOK active — attaching ${byokMap.length} X-BYOK headers\n`);
  }

  pi.registerProvider("omi", {
    api: "openai-completions",
    baseUrl,
    apiKey,
    ...(byokActive ? { headers: byokHeaders } : {}),
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
export const __omiRelayCorrelationForTest = omiRelayCorrelation;

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
