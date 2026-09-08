import { app } from 'electron'
import { join } from 'path'
import { existsSync } from 'fs'

/**
 * Resolve the on-disk path to the bundled win-automation-helper.exe.
 * Mirrors src/main/ocr/resolveHelperPath.ts (packaged-unpacked, extraResources,
 * dev). Returns the dev path last so the bridge surfaces a clear "not found".
 */
export function resolveHelperPath(): string {
  const exe = 'win-automation-helper.exe'
  const candidates = [
    join(process.resourcesPath, 'app.asar.unpacked', 'resources', 'win-automation-helper', exe),
    join(process.resourcesPath, 'win-automation-helper', exe),
    join(app.getAppPath(), 'resources', 'win-automation-helper', exe)
  ]
  for (const c of candidates) {
    if (existsSync(c)) return c
  }
  return candidates[candidates.length - 1]
}
