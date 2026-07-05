import { AcpRuntimeAdapter } from "./acp.js";

export interface CodexRuntimeAdapterOptions {
  command?: string;
  log?: (message: string) => void;
}

/**
 * Codex adapter — drives OpenAI Codex through the codex-acp stdio bridge
 * (`@agentclientprotocol/codex-acp`), which speaks the same ACP JSON-RPC as
 * the other external adapters.
 *
 * codex-acp specifics that differ from Claude/Hermes:
 * - It does NOT implement the standard `session/set_model` (it uses
 *   `unstable_setSessionModel` / `setSessionConfigOption`), so we disable
 *   model-switching to avoid calling an unimplemented method.
 * - It rejects per-session MCP servers, so we send an empty MCP list.
 * - Auth + permission behaviour are controlled via the launch environment
 *   (CODEX_API_KEY/OPENAI_API_KEY, NO_BROWSER, INITIAL_AGENT_MODE) which the
 *   host seeds into `OMI_CODEX_ADAPTER_COMMAND` / the allowlisted env.
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
