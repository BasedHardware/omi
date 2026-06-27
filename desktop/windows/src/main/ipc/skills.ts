import { ipcMain } from 'electron'
import type { SkillsListResult } from '../../shared/types'
import { listSkills } from '../skills/loader'

export function registerSkillsHandlers(): void {
  ipcMain.handle('skills:list', async (): Promise<SkillsListResult> => listSkills())
}
