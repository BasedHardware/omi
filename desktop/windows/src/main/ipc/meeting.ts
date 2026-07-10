// src/main/ipc/meeting.ts — settings + toast-action IPC for meeting detection.
import { ipcMain } from 'electron'
import { getAppSettings, setAppSettings } from '../appSettings'
import { meetingToastAction, meetingSettingsChanged } from '../meeting/meetingMonitor'
import type { MeetingSettings, MeetingToastAction } from '../../shared/types'

export function registerMeetingHandlers(): void {
  ipcMain.handle('meeting:getSettings', async () => getAppSettings().meeting)
  ipcMain.handle('meeting:setSettings', async (_e, patch: Partial<MeetingSettings>) => {
    // Merge at the meeting level (setAppSettings merges only top-level keys).
    const next = setAppSettings({ meeting: { ...getAppSettings().meeting, ...patch } }).meeting
    meetingSettingsChanged()
    return next
  })
  ipcMain.on('meeting:action', (_e, meetingId: string, action: MeetingToastAction) => {
    if (typeof meetingId !== 'string') return
    if (action !== 'start' && action !== 'stop' && action !== 'dismiss') return
    meetingToastAction(meetingId, action)
  })
}
