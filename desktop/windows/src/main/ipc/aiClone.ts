// AI-clone IPC: the renderer configures the main-process responder and renders
// its state. Events (state changes, token-expired) broadcast to every window so
// the badge and inbox stay live from both the main window and the overlay.
import { ipcMain, BrowserWindow } from 'electron'
import { AiCloneService } from '../aiClone/service'
import type { AiCloneAuth, AiCloneChatMode, AiCloneEvent } from '../../shared/types'

export function registerAiCloneHandlers(): void {
  const service = new AiCloneService((e: AiCloneEvent) => {
    for (const w of BrowserWindow.getAllWindows()) {
      if (!w.isDestroyed()) w.webContents.send('ai-clone:event', e)
    }
  })

  ipcMain.handle('ai-clone:getState', async () => service.getState())
  ipcMain.handle('ai-clone:connect', async (_e, beeperToken: string) =>
    service.connect(beeperToken)
  )
  ipcMain.handle('ai-clone:disconnect', async () => service.disconnect())
  ipcMain.handle('ai-clone:setEnabled', async (_e, enabled: boolean, auth?: AiCloneAuth) =>
    service.setEnabled(enabled, auth)
  )
  ipcMain.handle('ai-clone:listChats', async () => service.listChats())
  ipcMain.handle('ai-clone:setChatMode', async (_e, chatId: string, mode: AiCloneChatMode) =>
    service.setChatMode(chatId, mode)
  )
  ipcMain.handle('ai-clone:approveDraft', async (_e, draftId: string, editedText?: string) =>
    service.approveDraft(draftId, editedText)
  )
  ipcMain.handle('ai-clone:discardDraft', async (_e, draftId: string) =>
    service.discardDraft(draftId)
  )
  ipcMain.on('ai-clone:provideAuthToken', (_e, auth: AiCloneAuth) =>
    service.provideAuthToken(auth)
  )
}
