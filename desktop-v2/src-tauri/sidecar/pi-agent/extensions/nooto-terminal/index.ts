/**
 * Pi extension: dispatch_bash — non-blocking shell execution.
 *
 * ## Why this exists
 *
 * Pi's built-in `bash` tool blocks the entire agent turn until the spawned
 * process exits. Long-running servers (`npm run dev`, `uvicorn`, etc.) therefore
 * hang the agent indefinitely.
 *
 * `dispatch_bash` fixes this with a 5-second timeout:
 *   - If the command exits ≤ 5 s: returns full output + exit code.
 *   - If still running after 5 s: returns `still_running: true` + output so far,
 *     and the process keeps running in the background.
 *
 * ## Streaming channel
 *
 * The tool uses `child_process.spawn` internally (not `pi.exec()`, which only
 * returns output on completion). Chunks arrive via the `onUpdate` callback,
 * which Pi serialises as `tool_execution_update` events. Tauri's existing
 * stdout reader in `coding_agent.rs` forwards every Pi RPC line as
 * `coding-agent:event`, so the TerminalPane subscribes to
 * `tool_execution_update` events where `toolName === "dispatch_bash"`.
 *
 * Each chunk is also appended to:
 *   ~/.nooto/coding-agent/terminals/<terminal_id>.log
 * so the log persists even if the UI is not mounted.
 */

import type { ExtensionAPI, AgentToolResult } from "@mariozechner/pi-coding-agent";
import { Type } from "@sinclair/typebox";
import { appendFileSync, mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { resolve } from "node:path";
import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DISPATCH_TIMEOUT_MS = 5_000;
const MAX_OUTPUT_BYTES = 256_000;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function resolveLogDir(): string {
  const dir = resolve(homedir(), ".nooto", "coding-agent", "terminals");
  mkdirSync(dir, { recursive: true });
  return dir;
}

function appendLog(logPath: string, chunk: string): void {
  try {
    appendFileSync(logPath, chunk, { encoding: "utf8" });
  } catch {
    // Log write errors must not crash the tool.
  }
}

// ---------------------------------------------------------------------------
// Extension factory
// ---------------------------------------------------------------------------

export default function registerNootoTerminal(pi: ExtensionAPI): void {
  const logDir = resolveLogDir();

  pi.registerTool({
    name: "dispatch_bash",
    label: "Terminal",
    description:
      "Run a shell command in the background without blocking the agent. " +
      "Use this instead of `bash` for any command that starts a long-running " +
      "process (dev servers, watchers, build pipelines). " +
      "For long-running processes the tool returns after 5 seconds with " +
      "`still_running: true`; the process keeps running and its output streams " +
      "to the terminal pane in the UI.",
    promptSnippet:
      'dispatch_bash({ command: "npm run dev", description: "Start dev server" }) → launches non-blocking process',
    promptGuidelines: [
      "Use `dispatch_bash` for any `npm run dev`, `uvicorn`, `next dev`, or other server that never exits.",
      "Use the regular `bash` tool for short commands (< 5s) — `dispatch_bash` adds overhead.",
      "The `description` field is shown in the terminal pane header — make it human-readable.",
      "If `still_running` is true in the result, the process is still alive; inform the user and continue.",
    ],
    parameters: Type.Object({
      command: Type.String({
        description: "Full shell command to execute (passed to /bin/sh -c).",
      }),
      description: Type.String({
        description: "Short human-readable label shown in the terminal pane header (e.g. 'Start dev server').",
      }),
      cwd: Type.Optional(
        Type.String({
          description: "Working directory for the command. Defaults to the session's project root.",
        }),
      ),
    }),

    async execute(_toolCallId, params, signal, onUpdate, ctx) {
      const terminal_id = randomUUID();
      const logPath = resolve(logDir, `${terminal_id}.log`);
      const workingDir = params.cwd ? resolve(params.cwd) : (ctx.cwd ?? process.cwd());

      let outputBuffer = "";
      let bytesAccumulated = 0;
      let truncated = false;

      const handleChunk = (chunk: string): void => {
        if (!truncated) {
          const remaining = MAX_OUTPUT_BYTES - bytesAccumulated;
          if (chunk.length > remaining) {
            outputBuffer += chunk.slice(0, remaining) + "\n[output truncated]";
            bytesAccumulated = MAX_OUTPUT_BYTES;
            truncated = true;
          } else {
            outputBuffer += chunk;
            bytesAccumulated += chunk.length;
          }
        }

        appendLog(logPath, chunk);

        onUpdate?.({
          content: [
            {
              type: "text" as const,
              text: JSON.stringify({
                terminal_id,
                description: params.description,
                output_so_far: outputBuffer,
                still_running: true,
              }),
            },
          ],
        });
      };

      // Spawn via /bin/sh so shell builtins, pipes, and aliases work.
      // Inherit the parent environment (no explicit env needed — undefined = inherit).
      const child = spawn("/bin/sh", ["-c", params.command], {
        cwd: workingDir,
        stdio: ["ignore", "pipe", "pipe"],
      });

      const result = await new Promise<AgentToolResult>((resolvePromise) => {
        let settled = false;
        let exitCode: number | null = null;
        let timer: ReturnType<typeof setTimeout> | null = null;

        const settle = (stillRunning: boolean): void => {
          if (settled) return;
          settled = true;
          if (timer !== null) clearTimeout(timer);

          const payload = stillRunning
            ? { terminal_id, description: params.description, still_running: true, output_so_far: outputBuffer, truncated, log_path: logPath }
            : { terminal_id, description: params.description, still_running: false, exit_code: exitCode ?? 0, output: outputBuffer, truncated, log_path: logPath };

          resolvePromise({
            content: [{ type: "text" as const, text: JSON.stringify(payload) }],
            details: payload,
          });
        };

        child.stdout?.on("data", (data: Buffer) => handleChunk(data.toString("utf8")));
        child.stderr?.on("data", (data: Buffer) => handleChunk(data.toString("utf8")));

        child.on("close", (code) => {
          exitCode = code ?? 0;
          appendLog(logPath, `\n[process exited with code ${exitCode}]\n`);
          settle(false);
        });

        child.on("error", (err) => {
          appendLog(logPath, `\n[spawn error: ${err.message}]\n`);
          outputBuffer += `\n[spawn error: ${err.message}]`;
          exitCode = 1;
          settle(false);
        });

        // Return still_running=true after 5 s; child keeps running.
        timer = setTimeout(() => settle(true), DISPATCH_TIMEOUT_MS);

        // Kill and unblock if the agent turn is aborted.
        signal?.addEventListener("abort", () => {
          if (!settled) child.kill("SIGTERM");
          settle(false);
        });
      });

      return result;
    },
  });
}
