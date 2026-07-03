import { AcpRuntimeAdapter } from "./acp.js";

/**
 * Codex adapter. Follows the same ACP-subclass pattern as Hermes/OpenClaw:
 * it drives a local Codex agent that speaks ACP over the command named by
 * `OMI_CODEX_ADAPTER_COMMAND`.
 *
 * For the Track-1 demo this can point at a mock ACP command (see the agent
 * README) so the "route to codex" path is reproducible without a real Codex
 * install. Detection stays credential-safe: availability is decided by the env
 * var / PATH probe in the detectors, never by reading Codex auth files.
 */
export interface CodexRuntimeAdapterOptions {
  command?: string;
  log?: (message: string) => void;
}

export class CodexRuntimeAdapter extends AcpRuntimeAdapter {
  constructor(options: CodexRuntimeAdapterOptions = {}) {
    super({
      adapterId: "codex",
      envCommandName: "OMI_CODEX_ADAPTER_COMMAND",
      command: options.command,
      log: options.log,
    });
  }
}
