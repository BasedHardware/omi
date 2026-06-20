import { app } from 'electron'
import { join } from 'path'
import { existsSync } from 'fs'

/**
 * Resolve the on-disk path to the bundled win-update-helper.exe (the native
 * Task-Dialog progress UI). Mirrors src/main/ocr/resolveHelperPath.ts:
 *  1. Packaged via `asarUnpack: resources/**`
 *  2. Packaged via extraResources
 *  3. Dev (electron-vite)
 * Returns the dev path last so the caller surfaces a clear "not found".
 */
export function resolveUpdateHelperPath(): string {
  const exe = 'win-update-helper.exe'
  const candidates = [
    join(process.resourcesPath, 'app.asar.unpacked', 'resources', 'win-update-helper', exe),
    join(process.resourcesPath, 'win-update-helper', exe),
    join(app.getAppPath(), 'resources', 'win-update-helper', exe)
  ]
  for (const c of candidates) {
    if (existsSync(c)) return c
  }
  return candidates[candidates.length - 1]
}
