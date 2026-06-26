import { app } from 'electron'
import { join } from 'path'

// Runtime resources the main process reads from disk (OCR sidecar script, tray
// icon). In packaged builds these ship via electron-builder `extraResources`,
// landing directly under process.resourcesPath. In dev they live in the
// project's resources/ dir.
//
// NOTE: do NOT point this at files inside the asar, they must be real files
// on disk (PowerShell can't read from asar, and nativeImage needs a real path).
export function resourcePath(name: string): string {
  return app.isPackaged ? join(process.resourcesPath, name) : join(app.getAppPath(), 'resources', name)
}
