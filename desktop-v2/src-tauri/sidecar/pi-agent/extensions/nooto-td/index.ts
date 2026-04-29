/**
 * Pi extension: exposes the `td` CLI as an LLM-callable tool.
 *
 * Registers a single tool named `td` with a constrained allowlist of subcommands.
 * If `td` is not installed, the tool returns { ok: false, error: "td not installed" }
 * on each call rather than failing at load time.
 */

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { Type } from "@sinclair/typebox";
import { execFile } from "node:child_process";
import { accessSync, constants } from "node:fs";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TD_TIMEOUT_MS = 5_000;

// Matches Bearer tokens and long opaque strings that could be credentials.
const TOKEN_RE = /Bearer [A-Za-z0-9._-]+|[A-Za-z0-9]{32,}/g;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Mask anything that looks like a credential from extension output. */
function redactTokens(text: string): string {
  return text.replace(TOKEN_RE, "[REDACTED]");
}

/** Return true if the given absolute path is executable. */
function isExecutable(p: string): boolean {
  try {
    accessSync(p, constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

/**
 * Resolve the absolute path to the `td` binary.
 *
 * macOS GUI apps launched from Finder / Dock inherit a stripped PATH that
 * typically excludes ~/.cargo/bin.  We probe well-known install locations
 * explicitly before falling back to the raw name "td" (which works if the
 * Tauri app was launched from a terminal that has a full PATH).
 *
 * Returns { path, found } so callers know whether the path was confirmed
 * executable at load time (found=true) or is a best-effort fallback (found=false).
 */
function resolveTdPath(): { path: string; found: boolean } {
  const home = process.env.HOME ?? "";
  const candidates = [
    `${home}/.cargo/bin/td`,
    "/usr/local/bin/td",
    "/opt/homebrew/bin/td",
    "/nix/var/nix/profiles/default/bin/td",
  ];

  for (const candidate of candidates) {
    if (isExecutable(candidate)) return { path: candidate, found: true };
  }

  // Last resort: let execFile resolve via PATH at call time.
  return { path: "td", found: false };
}

/**
 * Run `td` with the given argv via execFile (no shell — args passed directly).
 * Returns stdout trimmed on success; rejects on non-zero exit or timeout.
 */
async function runTd(tdPath: string, argv: string[]): Promise<string> {
  return new Promise((resolve, reject) => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      controller.abort();
    }, TD_TIMEOUT_MS);

    execFile(tdPath, argv, { signal: controller.signal }, (err, stdout, stderr) => {
      clearTimeout(timer);

      if (err) {
        const code = (err as NodeJS.ErrnoException).code;
        if (code === "ABORT_ERR") {
          reject(new Error("td timed out"));
          return;
        }
        reject(new Error(redactTokens(stderr?.trim() || err.message)));
        return;
      }

      resolve(redactTokens(stdout));
    });
  });
}

// ---------------------------------------------------------------------------
// Subcommand dispatch
// ---------------------------------------------------------------------------

type Subcommand = "tasks.ls" | "tasks.show" | "tasks.comments" | "prs.ls" | "prs.show" | "worktree.ls";

interface TdInput {
  subcommand: Subcommand;
  ticket_id?: string;
  pr_number?: number;
}

interface TdResult {
  ok: boolean;
  data?: string;
  error?: string;
}

function buildArgv(params: TdInput): string[] | { error: string } {
  switch (params.subcommand) {
    case "tasks.ls":
      return ["tasks", "ls", "--no-interactive"];

    case "tasks.show":
      if (!params.ticket_id) return { error: "ticket_id is required for tasks.show" };
      return ["tasks", "get", params.ticket_id, "--no-interactive"];

    case "tasks.comments":
      if (!params.ticket_id) return { error: "ticket_id is required for tasks.comments" };
      return ["tasks", "get", params.ticket_id, "--comments", "--no-interactive"];

    case "prs.ls":
      return ["prs", "ls", "--no-interactive"];

    case "prs.show": {
      if (params.pr_number === undefined || params.pr_number === null) {
        return { error: "pr_number is required for prs.show" };
      }
      const n = Number(params.pr_number);
      if (!Number.isInteger(n) || n <= 0) return { error: "pr_number must be a positive integer" };
      return ["prs", "get", String(n), "--no-interactive"];
    }

    case "worktree.ls":
      // The real td subcommand is `worktrees ls` (plural) — map transparently.
      return ["worktrees", "ls"];

    default: {
      const exhaustive: never = params.subcommand;
      return { error: `unknown subcommand: ${exhaustive as string}` };
    }
  }
}

// ---------------------------------------------------------------------------
// Core execution (outside factory so independently unit-testable)
// ---------------------------------------------------------------------------

async function executeTd(tdPath: string, params: TdInput): Promise<TdResult> {
  const argvOrError = buildArgv(params);

  if ("error" in argvOrError) {
    return { ok: false, error: argvOrError.error };
  }

  try {
    const stdout = await runTd(tdPath, argvOrError);
    return { ok: true, data: stdout.trimEnd() };
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);

    if (msg.includes("ENOENT")) {
      return { ok: false, error: "td not installed — run `cargo install td-cli` or check PATH" };
    }

    return { ok: false, error: msg };
  }
}

// ---------------------------------------------------------------------------
// Extension factory
// ---------------------------------------------------------------------------

export default function registerNootoTd(pi: ExtensionAPI): void {
  const { path: tdPath, found: tdFound } = resolveTdPath();

  if (!tdFound) {
    console.warn("[nooto-td] td binary not found at known paths — tool will try PATH or return errors on each call");
  }

  pi.registerTool({
    name: "td",
    label: "td CLI",
    description:
      "Query Jira tasks, Bitbucket pull requests, and git worktrees via the `td` CLI. " +
      "Use subcommand to choose the operation and provide ticket_id or pr_number as required.",
    promptSnippet: 'td({ subcommand: "tasks.show", ticket_id: "WPNG-123" }) → Jira ticket details',
    promptGuidelines: [
      'Use "tasks.ls" to list your open Jira tickets.',
      'Use "tasks.show" with ticket_id (e.g. "WPNG-1234") to view ticket details.',
      'Use "tasks.comments" with ticket_id to include the full comment thread.',
      'Use "prs.ls" to list open Bitbucket PRs for the current repo.',
      'Use "prs.show" with pr_number to view a specific PR.',
      'Use "worktree.ls" to list active git worktrees.',
    ],
    parameters: Type.Object({
      subcommand: Type.Union(
        [
          Type.Literal("tasks.ls"),
          Type.Literal("tasks.show"),
          Type.Literal("tasks.comments"),
          Type.Literal("prs.ls"),
          Type.Literal("prs.show"),
          Type.Literal("worktree.ls"),
        ],
        { description: "Which td operation to run" },
      ),
      ticket_id: Type.Optional(
        Type.String({
          description: 'Jira ticket key, e.g. "WPNG-1234". Required for tasks.show and tasks.comments.',
        }),
      ),
      pr_number: Type.Optional(
        Type.Number({
          description: "Bitbucket PR number (integer). Required for prs.show.",
        }),
      ),
    }),

    async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
      const result = await executeTd(tdPath, params as TdInput);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(result) }],
        details: {},
      };
    },
  });
}
