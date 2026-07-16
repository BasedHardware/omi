// Claude Code — the default, always-available adapter. Unlike the external
// adapters it needs no user-installed CLI: it spawns the bundled
// claude-acp-entry.mjs (running @agentclientprotocol/claude-agent-acp) with
// Electron's binary running as Node. The `?asset` import makes electron-vite
// copy the entry script into the build output and resolve its runtime path in
// both dev and packaged builds (same mechanism as resources/icon.png in
// main/index.ts); vitest resolves it via the asset-suffix plugin in
// vitest.config.ts.
//
// Sign-in: the spawned bridge (and the SDK it runs) reads OAuth credentials from
// `<CLAUDE_CONFIG_DIR>/.credentials.json`. Startup pins CLAUDE_CONFIG_DIR to an
// Omi-owned, ISOLATED dir (see ./agentConfigDir.ts) so the agent never touches
// the user's real ~/.claude. The default-adapter spawn in acp.ts inherits the
// parent environment (`{...process.env}`), so that pinned dir flows through
// unchanged — and claudeOAuth.ts writes the credentials file to the same
// resolved dir, so writer and reader always agree. No extra env wiring here;
// see ../ipc/codingAgent.ts for the flow.

import bundledAcpEntry from './claude-acp-entry.mjs?asset'
import { AcpRuntimeAdapter } from './acp'

export interface ClaudeCodeRuntimeAdapterOptions {
  log?: (message: string) => void
  /** Test seam: override the bundled entry path. */
  acpEntry?: string
}

export class ClaudeCodeRuntimeAdapter extends AcpRuntimeAdapter {
  constructor(options: ClaudeCodeRuntimeAdapterOptions = {}) {
    super({
      adapterId: 'acp',
      acpEntry: options.acpEntry ?? bundledAcpEntry,
      log: options.log
    })
  }
}
