import { app, BrowserWindow, ipcMain } from 'electron'
import { join } from 'node:path'
import { ProactivityFeedConsumer } from './feedConsumer'
import { setProactivityWakeupHandler } from '../ipc/omiListen'
import { getSessionEpoch, onSessionChange } from '../assistants/core/session'
import { hideProactivityToast } from '../insight/toastWindow'
import type { ProactivityTarget } from '../../renderer/src/lib/omiApi.generated'

export function registerProactivityConsumer(mainWindow: () => BrowserWindow | null): void {
  let pending: {
    target: ProactivityTarget
    epoch: number
    finish: (opened: boolean) => void
  } | null = null
  const consumer = new ProactivityFeedConsumer(
    join(app.getPath('userData'), 'proactivity-receipts.json'),
    (target) => {
      const win = mainWindow()
      if (!win || win.isDestroyed()) return Promise.resolve(false)
      pending?.finish(false)
      return new Promise<boolean>((resolve) => {
        const timer = setTimeout(() => finish(false), 15_000)
        const finish = (opened: boolean): void => {
          clearTimeout(timer)
          if (pending?.finish === finish) pending = null
          resolve(opened)
        }
        pending = { target, epoch: getSessionEpoch(), finish }
        if (win.isMinimized()) win.restore()
        win.show()
        win.focus()
        win.webContents.send('proactivity:navigate', target)
      })
    }
  )
  setProactivityWakeupHandler((ownerID, payload) => consumer.handleListenEvent(ownerID, payload))
  ipcMain.on('proactivity:target-rendered', (event, target: ProactivityTarget) => {
    if (
      event.sender.id !== mainWindow()?.webContents.id ||
      !pending ||
      pending.epoch !== getSessionEpoch()
    )
      return
    if (target?.kind === pending.target.kind && target.id === pending.target.id)
      pending.finish(true)
  })
  onSessionChange(() => {
    pending?.finish(false)
    hideProactivityToast()
    consumer.sessionChanged()
  })
  app.on('browser-window-focus', () => void consumer.refresh())
  const timer = setInterval(() => {
    if (BrowserWindow.getFocusedWindow()) void consumer.refresh()
  }, 600_000)
  timer.unref()
}
