// Codex — OpenAI's agent, driven through the official ACP bridge
// (@agentclientprotocol/codex-acp). Suggested launch command is
// `npx -y @agentclientprotocol/codex-acp`; the `-y` keeps the first npx fetch
// non-interactive so a one-click connect cannot hang on a prompt.
//
// The bridge authenticates either through the codex CLI's own login or an
// OpenAI API key. Those variables are forwarded by
// ADAPTER_SPECIFIC_ENV_ALLOWLIST in acp.ts, which scopes them to this adapter —
// Hermes and OpenClaw are spawned with `shell: true` and must never receive
// another agent's credentials.

import { AcpRuntimeAdapter } from "./acp.js";

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
      // Conservative until verified against the real bridge; matches the
      // modelSwitching known_limitation in the capability matrix.
      supportsSessionSetModel: false,
      log: options.log,
    });
  }
}
