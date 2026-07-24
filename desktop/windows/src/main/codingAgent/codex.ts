// Codex — driven through the official ACP bridge for the OpenAI Codex CLI
// (@agentclientprotocol/codex-acp, successor to @zed-industries/codex-acp).
// Suggested command: `npx -y @agentclientprotocol/codex-acp@1.1.4` (the `-y` keeps the
// first npx fetch non-interactive so one-click Connect can't hang on a prompt).
// The bridge auths via the user's ChatGPT login (codex CLI) or an OpenAI API
// key — which is why the key env vars are forwarded for this adapter only, and
// why `openAiApiKey` (from Omi's encrypted store) is injected as OPENAI_API_KEY.

import { AcpRuntimeAdapter } from './acp'

export interface CodexRuntimeAdapterOptions {
  command?: string
  log?: (message: string) => void
  /** The user's OpenAI API key from Omi's encrypted store. Injected as
   *  OPENAI_API_KEY so the bridge's API-key auth path works without a separate
   *  `codex login`. Overrides any OPENAI_API_KEY inherited from the parent env. */
  openAiApiKey?: string
}

export class CodexRuntimeAdapter extends AcpRuntimeAdapter {
  constructor(options: CodexRuntimeAdapterOptions = {}) {
    super({
      adapterId: 'codex',
      envCommandName: 'OMI_CODEX_ADAPTER_COMMAND',
      command: options.command,
      extraEnvPassthrough: ['OPENAI_API_KEY', 'CODEX_API_KEY', 'CODEX_HOME'],
      extraEnv: options.openAiApiKey ? { OPENAI_API_KEY: options.openAiApiKey } : undefined,
      // Conservative until verified against the real bridge (see the
      // win-agents-codex-verify capability notes in interface.ts).
      supportsSessionSetModel: false,
      log: options.log
    })
  }
}
