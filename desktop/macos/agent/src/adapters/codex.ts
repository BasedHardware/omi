import { OneShotCliRuntimeAdapter } from "./one-shot-cli.js";

export interface CodexRuntimeAdapterOptions {
  /** Explicit command override. Defaults to the OMI_CODEX_ADAPTER_COMMAND env var. */
  command?: string;
  /**
   * Args placed before the prompt. Defaults to `exec --full-auto`, which runs
   * Codex non-interactively in its low-friction sandboxed auto mode (edits the
   * workspace, never blocks on an approval prompt). Override for a different
   * sandbox/approval policy.
   */
  execArgs?: string[];
  log?: (message: string) => void;
}

/**
 * Codex adapter — OpenAI Codex CLI (https://github.com/openai/codex).
 *
 * Codex is a terminal-first coding agent invoked non-interactively via
 * `codex exec "<prompt>"`. Unlike the ACP-based adapters (Claude Code, Hermes,
 * OpenClaw) it exposes no long-lived resumable session, so it runs one-shot:
 * each attempt spawns a fresh `codex exec` process, streams the final message
 * back, and exits. The prompt is passed as the trailing positional argument
 * (no prompt flag), matching Codex's CLI.
 *
 * Activation: set OMI_CODEX_ADAPTER_COMMAND to the Codex launcher (e.g. "codex").
 * The desktop app seeds this automatically when the `codex` binary is detected
 * (mirrors the OMI_HERMES/OPENCLAW_ADAPTER_COMMAND auto-discovery).
 */
export class CodexRuntimeAdapter extends OneShotCliRuntimeAdapter {
  constructor(options: CodexRuntimeAdapterOptions = {}) {
    super({
      adapterId: "codex",
      envCommandName: "OMI_CODEX_ADAPTER_COMMAND",
      command: options.command,
      fixedArgs: options.execArgs ?? ["exec", "--full-auto"],
      // No prompt flag: `codex exec` takes the prompt as a positional argument.
      log: options.log,
    });
  }
}
