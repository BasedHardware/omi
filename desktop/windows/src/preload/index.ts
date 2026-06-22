import { contextBridge, ipcRenderer } from 'electron'
import { electronAPI } from '@electron-toolkit/preload'
import type {
  OmiBridgeApi,
  OmiOverlayApi,
  LocalConversation,
  CaptureChoice,
  ListenStartArgs,
  ListenMessage,
  ExportMemory,
  GoogleSource,
  KnowledgeGraph,
  OnboardingGraphNode,
  OnboardingGraphEdge,
  UsageSettings,
  RewindSettings,
  InsightPayload,
  AutomationPlan,
  StepResult
} from '../shared/types'

const omi: OmiBridgeApi = {
  getCaptureSources: () => ipcRenderer.invoke('capture:getSources'),
  remapConversationId: (fromId: string, toId: string) =>
    ipcRenderer.invoke('db:remapConversationId', fromId, toId),
  insertLocalConversation: (c: LocalConversation) =>
    ipcRenderer.invoke('db:insertLocalConversation', c),
  getLocalConversation: (id: string) => ipcRenderer.invoke('db:getLocalConversation', id),
  listLocalConversations: () => ipcRenderer.invoke('db:listLocalConversations'),
  deleteLocalConversation: (id: string) => ipcRenderer.invoke('db:deleteLocalConversation', id),
  updateLocalConversationTitle: (id: string, title: string) =>
    ipcRenderer.invoke('db:updateLocalConversationTitle', id, title),
  onRecordHotkey: (cb: (choice: CaptureChoice) => void) => {
    const listener = (_e: Electron.IpcRendererEvent, choice: CaptureChoice): void => cb(choice)
    ipcRenderer.on('recorder:hotkey', listener)
    return () => ipcRenderer.removeListener('recorder:hotkey', listener)
  },
  listenStart: (args: ListenStartArgs) => ipcRenderer.invoke('omi-listen:start', args),
  listenStop: (sessionId: string) => ipcRenderer.invoke('omi-listen:stop', sessionId),
  listenFeed: (sessionId: string, pcm: ArrayBuffer) => {
    ipcRenderer.send('omi-listen:feed', sessionId, pcm)
  },
  onListenMessage: (cb: (msg: ListenMessage) => void) => {
    const listener = (_e: Electron.IpcRendererEvent, msg: ListenMessage): void => cb(msg)
    ipcRenderer.on('omi-listen:message', listener)
    return () => ipcRenderer.removeListener('omi-listen:message', listener)
  },
  indexFilesScan: () => ipcRenderer.invoke('fileIndex:scan'),
  indexFilesStatus: () => ipcRenderer.invoke('fileIndex:status'),
  indexFilesApps: (limit?: number) => ipcRenderer.invoke('fileIndex:apps', limit),
  localGraphLoad: () => ipcRenderer.invoke('localGraph:load') as Promise<KnowledgeGraph>,
  localGraphUpsert: (nodes: OnboardingGraphNode[], edges: OnboardingGraphEdge[]) =>
    ipcRenderer.invoke('localGraph:upsert', nodes, edges) as Promise<KnowledgeGraph>,
  localGraphClear: () => ipcRenderer.invoke('localGraph:clear') as Promise<void>,
  getAppUsage: () => ipcRenderer.invoke('usage:list'),
  usageFlush: () => ipcRenderer.invoke('usage:flush'),
  usageGetSettings: () => ipcRenderer.invoke('usage:getSettings'),
  usageSetSettings: (next: UsageSettings) => ipcRenderer.invoke('usage:setSettings', next),
  memoryImportParse: (dump: string) => ipcRenderer.invoke('memoryImport:parse', dump),
  memoryExportObsidian: (memories: ExportMemory[]) =>
    ipcRenderer.invoke('memoryExport:obsidian', memories),
  memoryExportFile: (memories: ExportMemory[]) => ipcRenderer.invoke('memoryExport:file', memories),
  memoryExportNotion: (args: { token: string; parentPageId: string; memories: ExportMemory[] }) =>
    ipcRenderer.invoke('memoryExport:notion', args),
  kgFileIndexDigest: () => ipcRenderer.invoke('kg:fileIndexDigest'),
  kgSaveGraph: (graph) => ipcRenderer.invoke('kg:saveGraph', graph),
  kgStatus: () => ipcRenderer.invoke('kg:status'),
  kgQueryNodes: (q, limit?) => ipcRenderer.invoke('kg:queryNodes', q, limit),
  kgSearchFiles: (q, fileType?, limit?) => ipcRenderer.invoke('kg:searchFiles', q, fileType, limit),
  kgExecuteSql: (sql) => ipcRenderer.invoke('kg:executeSql', sql),
  readStickyNotes: () => ipcRenderer.invoke('integrations:stickyNotes:read'),
  googleConnect: () => ipcRenderer.invoke('integrations:google:connect'),
  googleDisconnect: () => ipcRenderer.invoke('integrations:google:disconnect'),
  googleStatus: () => ipcRenderer.invoke('integrations:google:status'),
  googleGmailFetchNew: () => ipcRenderer.invoke('integrations:google:gmailFetchNew'),
  googleCalendarFetchNew: () => ipcRenderer.invoke('integrations:google:calendarFetchNew'),
  googleMarkProcessed: (source: GoogleSource, ids: string[]) =>
    ipcRenderer.invoke('integrations:google:markProcessed', source, ids),
  memoriesBulkDelete: (args: { baseURL: string; token: string; ids: string[] }) =>
    ipcRenderer.invoke('memories:bulkDelete', args),
  onMemoriesDeleteProgress: (
    cb: (p: { deleted: number; failed: number; total: number; done: boolean }) => void
  ) => {
    const listener = (
      _e: Electron.IpcRendererEvent,
      p: { deleted: number; failed: number; total: number; done: boolean }
    ): void => cb(p)
    ipcRenderer.on('memories:deleteProgress', listener)
    return () => ipcRenderer.removeListener('memories:deleteProgress', listener)
  },
  rewindFrames: (from: number, to: number) => ipcRenderer.invoke('rewind:frames', from, to),
  rewindDayBounds: () => ipcRenderer.invoke('rewind:dayBounds'),
  rewindSearch: (query: string) => ipcRenderer.invoke('rewind:search', query),
  rewindFrameImage: (imagePath: string) => ipcRenderer.invoke('rewind:frameImage', imagePath),
  rewindGetSettings: () => ipcRenderer.invoke('rewind:getSettings'),
  rewindSetSettings: (next: RewindSettings) => ipcRenderer.invoke('rewind:setSettings', next),
  rewindPruneNow: () => ipcRenderer.invoke('rewind:pruneNow'),
  rewindPrimarySourceId: () => ipcRenderer.invoke('rewind:primarySourceId'),
  rewindSaveFrame: (data: Uint8Array) => ipcRenderer.invoke('rewind:saveFrame', data),
  screenReadText: () => ipcRenderer.invoke('screen:readNow'),
  screenSynthFramesSince: () => ipcRenderer.invoke('screenSynth:framesSince'),
  screenSynthGetState: () => ipcRenderer.invoke('screenSynth:getState'),
  screenSynthSetState: (patch) => ipcRenderer.invoke('screenSynth:setState', patch),
  screenSynthAdvanceWatermark: (ts) => ipcRenderer.invoke('screenSynth:advanceWatermark', ts),
  screenSynthRecordRun: (run) => ipcRenderer.invoke('screenSynth:recordRun', run),
  onRewindSettings: (cb: (s: RewindSettings) => void) => {
    const listener = (_e: unknown, s: RewindSettings): void => cb(s)
    ipcRenderer.on('rewind:settings', listener)
    return () => ipcRenderer.removeListener('rewind:settings', listener)
  },
  insightGetSettings: () => ipcRenderer.invoke('insight:getSettings'),
  insightSetSettings: (patch) => ipcRenderer.invoke('insight:setSettings', patch),
  insightAdd: (p) => ipcRenderer.invoke('insight:add', p),
  insightRecent: (limit) => ipcRenderer.invoke('insight:recent', limit),
  insightShow: (p) => ipcRenderer.send('insight:show', p),
  insightDismiss: () => ipcRenderer.send('insight:dismiss'),
  insightHoverStart: () => ipcRenderer.send('insight:hoverStart'),
  insightHoverEnd: () => ipcRenderer.send('insight:hoverEnd'),
  insightTest: () => ipcRenderer.send('insight:test'),
  onInsightShow: (cb) => {
    const listener = (_e: Electron.IpcRendererEvent, p: InsightPayload): void => cb(p)
    ipcRenderer.on('insight:payload', listener)
    return () => ipcRenderer.removeListener('insight:payload', listener)
  },
  perfFirstPaint: () => ipcRenderer.send('perf:firstPaint'),
  perfMark: (name: string) => ipcRenderer.send('perf:mark', name),
  perfAnimResult: (stats: Record<string, number>) => ipcRenderer.send('perf:animResult', stats),
  isAnimBench: process.env.OMI_ANIM_BENCH === '1',
  benchEcho: (x: number) => ipcRenderer.invoke('bench:echo', x),
  isBench: process.env.OMI_BENCH === '1',
  // Desktop automation bridge. ON by default; OMI_AUTOMATION='0' disables it.
  // The renderer checks `automationEnabled` before its planner pre-step.
  automationEnabled: process.env.OMI_AUTOMATION !== '0',
  automationSnapshot: (windowHandle?: string) =>
    ipcRenderer.invoke('automation:snapshot', windowHandle),
  automationTargetWindow: () => ipcRenderer.invoke('automation:targetWindow'),
  // NOTE: the dialog-less `automationRun` is intentionally NOT exposed to the
  // renderer. Every renderer-initiated plan must go through automationConfirmRun,
  // which gates on a native approval dialog built in main from the real plan.
  // Exposing a consent-free run primitive to web content would let any future
  // renderer-side code (XSS, hostile navigation) silently drive Windows UI input.
  automationConfirmRun: (plan: AutomationPlan) => ipcRenderer.invoke('automation:confirmRun', plan),
  onAutomationStep: (cb: (r: StepResult) => void) => {
    const listener = (_e: unknown, r: StepResult): void => cb(r)
    ipcRenderer.on('automation:step', listener)
    return () => ipcRenderer.removeListener('automation:step', listener)
  },
  notifyConversationsChanged: () => ipcRenderer.send('conversations:notify-changed'),
  onConversationsChanged: (cb: () => void) => {
    const listener = (): void => cb()
    ipcRenderer.on('conversations:changed', listener)
    return () => ipcRenderer.removeListener('conversations:changed', listener)
  }
}

const omiOverlay: OmiOverlayApi = {
  onShown: (cb: () => void) => {
    const listener = (): void => cb()
    ipcRenderer.on('overlay:shown', listener)
    return () => ipcRenderer.removeListener('overlay:shown', listener)
  },
  hide: () => ipcRenderer.send('overlay:hide'),
  setEnabled: (enabled: boolean) => ipcRenderer.send('overlay:setEnabled', enabled),
  setHeight: (px: number) => ipcRenderer.send('overlay:setHeight', px),
  focusMain: () => ipcRenderer.send('overlay:focusMain'),
  onActiveChange: (cb: (active: boolean) => void) => {
    const listener = (_e: Electron.IpcRendererEvent, active: boolean): void => cb(active)
    ipcRenderer.on('overlay:active', listener)
    return () => ipcRenderer.removeListener('overlay:active', listener)
  },
  onWillHide: (cb: () => void) => {
    const listener = (): void => cb()
    ipcRenderer.on('overlay:willHide', listener)
    return () => ipcRenderer.removeListener('overlay:willHide', listener)
  },
  onSummoned: (cb: () => void) => {
    const listener = (): void => cb()
    ipcRenderer.on('overlay:summoned', listener)
    return () => ipcRenderer.removeListener('overlay:summoned', listener)
  },
  setAccelerator: (accelerator: string) =>
    ipcRenderer.invoke('overlay:setAccelerator', accelerator),
  suspendShortcut: () => ipcRenderer.send('overlay:suspendShortcut'),
  resumeShortcut: () => ipcRenderer.invoke('overlay:resumeShortcut'),
  onVisibilityChange: (cb: (state: { open: boolean; active: boolean }) => void) => {
    const listener = (
      _e: Electron.IpcRendererEvent,
      state: { open: boolean; active: boolean }
    ): void => cb(state)
    ipcRenderer.on('overlay:visibility', listener)
    return () => ipcRenderer.removeListener('overlay:visibility', listener)
  },
  notifyVoiceCaptured: () => ipcRenderer.send('overlay:voiceCaptured'),
  onVoiceCaptured: (cb: () => void) => {
    const listener = (): void => cb()
    ipcRenderer.on('overlay:voiceCaptured', listener)
    return () => ipcRenderer.removeListener('overlay:voiceCaptured', listener)
  },
  notifyAsked: () => ipcRenderer.send('overlay:asked'),
  onAsked: (cb: () => void) => {
    const listener = (): void => cb()
    ipcRenderer.on('overlay:asked', listener)
    return () => ipcRenderer.removeListener('overlay:asked', listener)
  }
}

if (process.contextIsolated) {
  try {
    contextBridge.exposeInMainWorld('electron', electronAPI)
    contextBridge.exposeInMainWorld('omi', omi)
    contextBridge.exposeInMainWorld('omiOverlay', omiOverlay)
  } catch (error) {
    console.error(error)
  }
} else {
  // @ts-ignore (define in dts)
  window.electron = electronAPI
  // @ts-ignore (define in dts)
  window.omi = omi
  // @ts-ignore (define in dts)
  window.omiOverlay = omiOverlay
}
