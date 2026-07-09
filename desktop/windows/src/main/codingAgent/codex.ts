// Codex — driven through the official ACP bridge for the OpenAI Codex CLI
// (@agentclientprotocol/codex-acp, successor to @zed-industries/codex-acp).
// Suggested command: `npx @agentclientprotocol/codex-acp`. The bridge auths
// via the user's ChatGPT login (codex CLI) or an API key, which is why the
// key env vars are forwarded for this adapter only.

import { AcpRuntimeAdapter } from './acp'

export interface CodexRuntimeAdapterOptions {
  command?: string
  log?: (message: string) => void
}

export class CodexRuntimeAdapter extends AcpRuntimeAdapter {
  constructor(options: CodexRuntimeAdapterOptions = {}) {
    super({
      adapterId: 'codex',
      envCommandName: 'OMI_CODEX_ADAPTER_COMMAND',
      command: options.command,
      extraEnvPassthrough: ['OPENAI_API_KEY', 'CODEX_API_KEY', 'CODEX_HOME'],
      // Conservative until verified against the real bridge (see the
      // win-agents-codex-verify capability notes in interface.ts).
      supportsSessionSetModel: false,
      log: options.log
    })
  }
}
