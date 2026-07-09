// Claude Code — the default, always-available adapter. Unlike the external
// adapters it needs no user-installed CLI: it spawns the bundled
// patched-acp-entry.mjs (wrapping @zed-industries/claude-agent-acp) with
// Electron's binary running as Node. The `?asset` import makes electron-vite
// copy the entry script into the build output and resolve its runtime path in
// both dev and packaged builds (same mechanism as resources/icon.png in
// main/index.ts); vitest resolves it via the asset-suffix plugin in
// vitest.config.ts.

import bundledAcpEntry from './patched-acp-entry.mjs?asset'
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
