import { app } from 'electron'
import { join } from 'path'
import { existsSync } from 'fs'

/**
 * Resolve the on-disk path to the bundled win-ocr-helper.exe.
 *
 * Locations, in priority order:
 * 1. Packaged via `asarUnpack: resources/**`:
 *    `<resourcesPath>/app.asar.unpacked/resources/win-ocr-helper/win-ocr-helper.exe`
 * 2. Packaged via extraResources:
 *    `<resourcesPath>/win-ocr-helper/win-ocr-helper.exe`
 * 3. Dev (electron-vite): `<appPath>/resources/win-ocr-helper/win-ocr-helper.exe`
 */
export function resolveHelperPath(): string {
  const exe = 'win-ocr-helper.exe'
  const candidates = [
    join(process.resourcesPath, 'app.asar.unpacked', 'resources', 'win-ocr-helper', exe),
    join(process.resourcesPath, 'win-ocr-helper', exe),
    join(app.getAppPath(), 'resources', 'win-ocr-helper', exe)
  ]
  for (const c of candidates) {
    if (existsSync(c)) return c
  }
  // Return the dev path so the supervisor surfaces a clear "helper not found"
  // error rather than spawning a nonexistent path.
  return candidates[candidates.length - 1]
}
