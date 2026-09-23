import { app, BrowserWindow, ipcMain } from 'electron'
import { stat } from 'fs/promises'
import type { ModelDownloadProgress, ModelEntry, ModelInstallState, ModelStatus } from '../../shared/types'
import { MODEL_REGISTRY, findModel, modelFilePath, modelPartPath } from '../modelStore/registry'
import { deleteModel, downloadModel } from '../modelStore/downloader'

const controllers = new Map<string, AbortController>()

// installed if the final file exists; partial if a resumable .part is present.
async function sizeAtPath(p: string): Promise<number> {
  try {
    return (await stat(p)).size
  } catch {
    return 0
  }
}

async function probe(entry: ModelEntry): Promise<{ state: ModelInstallState; bytes: number }> {
  const ud = app.getPath('userData')
  const full = await sizeAtPath(modelFilePath(ud, entry))
  if (full > 0) return { state: 'installed', bytes: full }
  const partial = await sizeAtPath(modelPartPath(ud, entry))
  if (partial > 0) return { state: 'partial', bytes: partial }
  return { state: 'absent', bytes: 0 }
}

function broadcast(p: ModelDownloadProgress): void {
  for (const w of BrowserWindow.getAllWindows()) {
    if (!w.isDestroyed()) w.webContents.send('models:progress', p)
  }
}

export function registerModelManagerHandlers(): void {
  ipcMain.handle('models:list', () => MODEL_REGISTRY)

  ipcMain.handle('models:status', async (): Promise<ModelStatus[]> => {
    const out: ModelStatus[] = []
    for (const entry of MODEL_REGISTRY) {
      const { state, bytes } = await probe(entry)
      out.push({ entry, state, bytesOnDisk: bytes, fromCache: false })
    }
    return out
  })

  ipcMain.handle('models:download', async (_e, id: string) => {
    const entry = findModel(id)
    if (!entry) return { ok: false, error: 'unknown model' }
    if (controllers.has(id)) return { ok: false, error: 'already downloading' }
    const controller = new AbortController()
    controllers.set(id, controller)
    // The engine reports failures as progress phases; mirror the terminal phase
    // so `download` resolves a truthful ok instead of always { ok: true }.
    let terminal: ModelDownloadProgress | null = null
    const record = (p: ModelDownloadProgress): void => {
      if (p.phase === 'done' || p.phase === 'error' || p.phase === 'cancelled') terminal = p
      broadcast(p)
    }
    try {
      await downloadModel(entry, app.getPath('userData'), record, controller.signal)
      const t = terminal as ModelDownloadProgress | null
      if (t && t.phase === 'done') return { ok: true }
      if (t && t.phase === 'cancelled') return { ok: false, error: 'cancelled' }
      return { ok: false, error: (t && t.error) || 'download did not complete' }
    } catch (e) {
      return { ok: false, error: (e as Error).message }
    } finally {
      controllers.delete(id)
    }
  })

  ipcMain.handle('models:cancel', (_e, id: string) => {
    controllers.get(id)?.abort()
    controllers.delete(id)
    return true
  })

  ipcMain.handle('models:delete', async (_e, id: string) => {
    const entry = findModel(id)
    if (!entry) return { ok: false, error: 'unknown model' }
    await deleteModel(entry, app.getPath('userData'))
    return { ok: true }
  })
}
