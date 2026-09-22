import { app, BrowserWindow, ipcMain } from 'electron'
import { stat } from 'fs/promises'
import type { ModelDownloadProgress, ModelInstallState, ModelStatus } from '../../shared/types'
import { MODEL_REGISTRY, findModel, modelFilePath } from '../modelStore/registry'
import { deleteModel, downloadModel } from '../modelStore/downloader'

const controllers = new Map<string, AbortController>()

async function stateOf(id: string): Promise<ModelInstallState> {
  const entry = findModel(id)
  if (!entry) return 'absent'
  try {
    await stat(modelFilePath(app.getPath('userData'), entry))
    return 'installed'
  } catch {
    return 'absent'
  }
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
      const state = await stateOf(entry.id)
      let bytesOnDisk = 0
      if (state === 'installed') {
        try {
          bytesOnDisk = (await stat(modelFilePath(app.getPath('userData'), entry))).size
        } catch {
          /* ignore */
        }
      }
      out.push({ entry, state, bytesOnDisk, fromCache: false })
    }
    return out
  })

  ipcMain.handle('models:download', async (_e, id: string) => {
    const entry = findModel(id)
    if (!entry) return { ok: false, error: 'unknown model' }
    if (controllers.has(id)) return { ok: false, error: 'already downloading' }
    const controller = new AbortController()
    controllers.set(id, controller)
    try {
      await downloadModel(entry, app.getPath('userData'), broadcast, controller.signal)
      return { ok: true }
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
