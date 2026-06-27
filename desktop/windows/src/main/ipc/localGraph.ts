import { ipcMain } from 'electron'
import { loadLocalGraph, upsertLocalGraph, clearLocalGraph } from './db'
import type { OnboardingGraphNode, OnboardingGraphEdge } from '../../shared/types'

export function registerLocalGraphHandlers(): void {
  ipcMain.handle('localGraph:load', async () => loadLocalGraph())
  ipcMain.handle('localGraph:upsert', async (_e, nodes: OnboardingGraphNode[], edges: OnboardingGraphEdge[]) =>
    upsertLocalGraph(nodes ?? [], edges ?? [])
  )
  ipcMain.handle('localGraph:clear', async () => clearLocalGraph())
}
