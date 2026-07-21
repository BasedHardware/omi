import { AcpRuntimeAdapter } from "./acp.js";

export interface CodexRuntimeAdapterOptions {
  command?: string;
  log?: (message: string) => void;
}

/**
 * OpenAI Codex, bridged onto Omi's ACP transport through the
 * `@zed-industries/codex-acp` adapter (the `codex-acp` binary). The `codex` CLI
 * itself has no native ACP mode, so the bridge is what actually speaks ACP over
 * stdio. Like OpenClaw it does not accept per-session MCP servers and does not
 * expose session/set_model.
 */
export class CodexRuntimeAdapter extends AcpRuntimeAdapter {
  constructor(options: CodexRuntimeAdapterOptions = {}) {
    super({
      adapterId: "codex",
      envCommandName: "OMI_CODEX_ADAPTER_COMMAND",
      command: options.command,
      sessionMcpServersMode: "empty",
      supportsSessionSetModel: false,
      log: options.log,
    });
  }
}
