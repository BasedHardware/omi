declare module 'electron-updater' {
  type UpdateInfo = { version: string }
  type ProgressInfo = { percent: number }

  interface AutoUpdater {
    autoDownload: boolean
    autoInstallOnAppQuit: boolean
    setFeedURL: (options: { provider: 'generic'; url: string }) => void
    on(event: 'checking-for-update', listener: () => void): void
    on(event: 'update-available', listener: (info: UpdateInfo) => void): void
    on(event: 'update-not-available', listener: (info: UpdateInfo) => void): void
    on(event: 'download-progress', listener: (progress: ProgressInfo) => void): void
    on(event: 'update-downloaded', listener: (info: UpdateInfo) => void): void
    on(event: 'error', listener: (error: Error) => void): void
    checkForUpdatesAndNotify: () => Promise<unknown>
  }

  export const autoUpdater: AutoUpdater
}
