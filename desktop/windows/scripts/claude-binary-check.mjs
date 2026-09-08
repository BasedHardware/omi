// Pure helpers for check-agent-deps.mjs: verify the Claude Code EXECUTABLE is
// actually installed, not just the JS packages around it.
//
// The failure mode this closes (hit live in PR #9304 review on a flaky
// network): @anthropic-ai/claude-agent-sdk-win32-x64 — which contains
// claude.exe (~235 MB), the binary the Claude Agent SDK spawns for every agent
// turn; the SDK ships no JS fallback — is an optionalDependency, so a failed
// download leaves `pnpm install` exiting 0. import.meta.resolve() checks can't
// catch it either: the platform package is binary-only with no resolvable JS
// entry. The result is an app where the ACP `initialize` handshake succeeds
// but the first real agent task has nothing to spawn.
//
// Kept side-effect-free (exported functions only) so it is unit-testable;
// check-agent-deps.mjs owns the process-level reporting/exit.

import { existsSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

// claude.exe is ~235 MB; anything far below that is a truncated download.
export const DEFAULT_MIN_BYTES = 50 * 1024 * 1024

const BINARY_PACKAGE = '@anthropic-ai/claude-agent-sdk-win32-x64'

/** Locate claude.exe in either the flattened or the pnpm virtual-store layout. */
export function findClaudeBinary(root) {
  const direct = join(root, 'node_modules', ...BINARY_PACKAGE.split('/'), 'claude.exe')
  if (existsSync(direct)) return direct

  const pnpmDir = join(root, 'node_modules', '.pnpm')
  if (existsSync(pnpmDir)) {
    const prefix = BINARY_PACKAGE.replace('/', '+') + '@'
    for (const entry of readdirSync(pnpmDir)) {
      if (!entry.startsWith(prefix)) continue
      // NOTE: a failed optional download can leave an EMPTY matching directory
      // behind in the virtual store — requiring claude.exe itself (not the
      // directory) is what makes this check catch that case.
      const candidate = join(
        pnpmDir,
        entry,
        'node_modules',
        ...BINARY_PACKAGE.split('/'),
        'claude.exe'
      )
      if (existsSync(candidate)) return candidate
    }
  }
  return null
}

/**
 * Verify the Claude Code binary is present and plausibly complete. Only
 * meaningful when installing for Windows; other platforms get their binary
 * from their own platform package and skip here.
 */
export function checkClaudeBinary(root, platform = process.platform, minBytes = DEFAULT_MIN_BYTES) {
  if (platform !== 'win32') {
    return { ok: true, skipped: true }
  }
  const binary = findClaudeBinary(root)
  if (!binary) {
    return {
      ok: false,
      reason:
        `${BINARY_PACKAGE} is not installed (claude.exe not found). It is an ` +
        'optionalDependency, so a failed ~247 MB download does NOT fail `pnpm install` — ' +
        'but without it the bundled Claude Code agent answers the ACP handshake and then ' +
        'cannot run any task. Re-run `pnpm install` on a reliable network.'
    }
  }
  const size = statSync(binary).size
  if (size < minBytes) {
    return {
      ok: false,
      reason:
        `claude.exe at ${binary} is only ${size} bytes — looks like a truncated ` +
        'download. Remove it and re-run `pnpm install`.'
    }
  }
  return { ok: true, binary, size }
}
