import { AcpRuntimeAdapter } from "./acp.js";

export interface CodexRuntimeAdapterOptions {
  command?: string;
  log?: (message: string) => void;
}

/**
 * Codex CLI has no native ACP mode; ACP reaches Codex through the
 * `@agentclientprotocol/codex-acp` bridge, which runs the Codex app-server
 * and translates ACP. Swift discovers the user-installed `codex-acp` binary
 * and points OMI_CODEX_ADAPTER_COMMAND at it.
 */
export class CodexRuntimeAdapter extends AcpRuntimeAdapter {
  constructor(options: CodexRuntimeAdapterOptions = {}) {
    super({
      adapterId: "codex",
      envCommandName: "OMI_CODEX_ADAPTER_COMMAND",
      command: options.command,
      // Codex does not accept Omi's Claude model aliases; model choice stays
      // with the Codex config, same as OpenClaw.
      supportsSessionSetModel: false,
      log: options.log,
    });
  }
}
