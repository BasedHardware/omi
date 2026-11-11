import { app } from 'electron'
import { join } from 'path'
import { existsSync } from 'fs'

/**
 * Resolve the on-disk path to the bundled win-audio-helper.exe.
 * Mirrors src/main/automation/resolveHelperPath.ts (packaged-unpacked,
 * extraResources, dev). Returns the dev path last so the bridge surfaces a clear
 * "not found" when the helper was never built (no .NET SDK).
 */
export function resolveAudioHelperPath(): string {
  const exe = 'win-audio-helper.exe'
  const candidates = [
    join(process.resourcesPath, 'app.asar.unpacked', 'resources', 'win-audio-helper', exe),
    join(process.resourcesPath, 'win-audio-helper', exe),
    join(app.getAppPath(), 'resources', 'win-audio-helper', exe)
  ]
  for (const c of candidates) {
    if (existsSync(c)) return c
  }
  return candidates[candidates.length - 1]
}
