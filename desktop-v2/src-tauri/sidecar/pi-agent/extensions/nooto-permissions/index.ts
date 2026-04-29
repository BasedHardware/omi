/**
 * Pi extension: permission gate + session journal.
 *
 * Rules enforced before any tool executes:
 *
 *   read / grep / find / ls  — always allowed, never journalled.
 *
 *   write / edit             — auto-approved when the resolved absolute path
 *                              starts with the session root (process.cwd() at
 *                              extension-init time). Hard-rejected otherwise.
 *
 *   bash                     — rejected when the command matches any destructive
 *                              pattern (see DESTRUCTIVE_RE below). Allowed
 *                              otherwise.
 *
 * Every allowed write / edit / bash call is journalled post-execution by
 * appending a single JSON line to:
 *   <session-root>/.nooto-coding-agent/journal.jsonl
 *
 * Journal row shape:
 *   {
 *     "ts":            ISO-8601 timestamp,
 *     "tool":          "bash" | "write" | "edit",
 *     "input":         the full tool input object,
 *     "resultPreview": first 200 chars of the tool's text output
 *   }
 */

import type { ExtensionAPI, ToolCallEventResult } from "@mariozechner/pi-coding-agent";
import { isToolCallEventType } from "@mariozechner/pi-coding-agent";
import { appendFileSync, mkdirSync } from "node:fs";
import { isAbsolute, resolve } from "node:path";

// ---------------------------------------------------------------------------
// Destructive bash pattern
// ---------------------------------------------------------------------------

/**
 * Combined regex: any command matching this is rejected before execution.
 * Tested against the full command string (case-sensitive).
 *
 * Patterns covered:
 *   - rm -rf / rm -fr (and multi-flag combos)
 *   - rm --recursive (GNU long form)
 *   - git push -f / --force / --force-with-lease
 *   - git reset --hard
 *   - redirect to absolute path outside /tmp  (e.g. `> /etc/passwd`)
 *   - dd if=  (disk imaging)
 *   - mkfs.*  (filesystem creation)
 *   - :(){:|:&};:  (fork bomb)
 */
const DESTRUCTIVE_RE = new RegExp(
  [
    String.raw`\brm\s+(-\S*r\S*f|-\S*f\S*r)\b`,
    String.raw`\brm\s+--[a-z-]*recursive`,
    String.raw`\bgit\s+push\b.*\s(-f|--force)\b`,
    String.raw`\bgit\s+push\b.*\s--force-with-lease\b`,
    String.raw`\bgit\s+reset\s+--hard\b`,
    String.raw`>\s*\/(?!tmp\/|tmp$)[^\s]`,
    String.raw`\bdd\s+if=`,
    String.raw`\bmkfs\.`,
    String.raw`:\(\)\s*\{.*:\|:.*&.*\}`,
    String.raw`:\s*\(\s*\)\s*\{`,
  ].join("|"),
);

// ---------------------------------------------------------------------------
// Long-running server pattern
// ---------------------------------------------------------------------------

/**
 * Commands that start a long-running dev server / watcher and never return on
 * their own. The bash tool blocks until exit, so these hang the whole agent
 * turn. Reject up front and tell the model to use a non-blocking alternative.
 */
const LONG_RUNNING_RE = new RegExp(
  [
    String.raw`\b(?:npm|pnpm|yarn|bun|deno)\s+(?:run\s+)?(?:dev|start|serve|watch)\b`,
    String.raw`\b(?:next|vite|nuxt|astro|remix|gatsby|webpack)\s+dev\b`,
    String.raw`\bnodemon\b`,
    String.raw`\btsx\s+watch\b`,
    String.raw`\btsc\s+--watch\b`,
    String.raw`\bvitest(?!\s+run\b)\b`, // `vitest` alone is watch mode; `vitest run` is fine
    String.raw`\bjest\s+--watch`,
    String.raw`\bflask\s+run\b`,
    String.raw`\buvicorn\s+`,
    String.raw`\bpython\s+-m\s+http\.server\b`,
    String.raw`\bhttp-server\b`,
    String.raw`\brails\s+(?:s|server)\b`,
  ].join("|"),
);

// ---------------------------------------------------------------------------
// Journal helpers
// ---------------------------------------------------------------------------

type JournalEntry = {
  ts: string;
  tool: "bash" | "write" | "edit";
  input: Record<string, unknown>;
  resultPreview: string;
};

/**
 * Append a single JSON line to the journal file.
 * Synchronous O_APPEND is atomic for writes smaller than PIPE_BUF.
 */
function appendJournal(journalPath: string, entry: JournalEntry): void {
  try {
    appendFileSync(journalPath, JSON.stringify(entry) + "\n", { encoding: "utf8" });
  } catch {
    // Journal write errors must never crash the agent session.
  }
}

// ---------------------------------------------------------------------------
// Extension factory
// ---------------------------------------------------------------------------

export default function registerNootoPermissions(pi: ExtensionAPI): void {
  // Capture session root at extension-init time (before any cwd change).
  const sessionRoot = resolve(process.cwd());

  const journalDir = resolve(sessionRoot, ".nooto-coding-agent");
  const journalPath = resolve(journalDir, "journal.jsonl");

  // Ensure the journal directory exists (best-effort; non-fatal if it fails).
  try {
    mkdirSync(journalDir, { recursive: true });
  } catch {
    // appendJournal will silently swallow write errors too.
  }

  // ---------------------------------------------------------------------------
  // tool_call — pre-execution gate (no journalling here; see tool_result below)
  // ---------------------------------------------------------------------------

  pi.on("tool_call", async (event, _ctx): Promise<ToolCallEventResult | void> => {
    if (isToolCallEventType("bash", event)) {
      const command = event.input.command ?? "";
      const destructive = DESTRUCTIVE_RE.exec(command);
      if (destructive) {
        return { block: true, reason: `destructive pattern matched: ${destructive[0]}` };
      }
      const longRunning = LONG_RUNNING_RE.exec(command);
      if (longRunning) {
        return {
          block: true,
          reason:
            `'${longRunning[0]}' starts a long-running server that never returns — the bash tool would hang indefinitely. ` +
            `Use the \`dispatch_bash\` tool instead: it runs the command in the background and streams output to the UI terminal pane. ` +
            `To inspect scripts first, try 'cat package.json' or 'npm run' (no args) to list available scripts.`,
        };
      }
      return;
    }

    if (isToolCallEventType("write", event) || isToolCallEventType("edit", event)) {
      return checkPath(event.input.path, sessionRoot);
    }

    // read / grep / find / ls — always allow.
  });

  // ---------------------------------------------------------------------------
  // tool_result — post-execution journal
  // ---------------------------------------------------------------------------

  pi.on("tool_result", async (event, _ctx) => {
    const tool = event.toolName;
    if (tool !== "bash" && tool !== "write" && tool !== "edit") return;

    const preview = event.content
      .filter((c): c is { type: "text"; text: string } => c.type === "text")
      .map((c) => c.text)
      .join("\n")
      .slice(0, 200);

    appendJournal(journalPath, {
      ts: new Date().toISOString(),
      tool: tool as "bash" | "write" | "edit",
      input: event.input as Record<string, unknown>,
      resultPreview: preview,
    });
  });
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function checkPath(filePath: string, sessionRoot: string): ToolCallEventResult | void {
  const abs = isAbsolute(filePath) ? filePath : resolve(sessionRoot, filePath);
  if (!abs.startsWith(sessionRoot + "/") && abs !== sessionRoot) {
    return { block: true, reason: `path outside session root: ${abs}` };
  }
}
