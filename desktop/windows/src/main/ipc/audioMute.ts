import { ipcMain } from 'electron'
import { systemAudioMuteBridge } from '../audio/systemAudioMute'

// PTT system-audio mute IPC (Track 2 A4). Fire-and-forget `send` channels — never
// `invoke` — so the renderer's push-to-talk path is never awaited and a slow or
// absent helper can never delay a hold. The renderer gates the mute CALL on the
// pttMuteSystemAudio pref; restore is always sent (unconditional, macOS-faithful).
export function registerAudioMuteHandlers(): void {
  ipcMain.on('audio:muteSystemAudio', () => {
    void systemAudioMuteBridge.muteSystemAudio()
  })
  ipcMain.on('audio:restoreSystemAudio', () => {
    void systemAudioMuteBridge.restoreSystemAudio()
  })
}
