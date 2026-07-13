import { contextBridge, ipcRenderer } from 'electron'
import { electronAPI } from '@electron-toolkit/preload'
import type {
  OmiBridgeApi,
  OmiOverlayApi,
  OmiBarApi,
  BarMode,
  BarShowPayload,
  BarChatState,
  LocalConversation,
  ConversationSyncPatch,
  CaptureChoice,
  ListenStartArgs,
  ListenMessage,
  CaptureCommand,
  CaptureEvent,
  ExportMemory,
  GoogleSource,
  KnowledgeGraph,
  OnboardingGraphNode,
  OnboardingGraphEdge,
  UsageSettings,
  RewindSettings,
  InsightPayload,
  MeetingToastPayload,
  WhatsNewPayload,
  AutomationPlan,
  StepResult,
  CodingAgentCommandOverrides,
  CodingAgentEvent,
  CodingAgentId,
  CodingAgentRunArgs
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
  updateLocalConversationSync: (id: string, patch: ConversationSyncPatch) =>
    ipcRenderer.invoke('db:updateLocalConversationSync', id, patch),
  claimConversationForPosting: (id: string, resetAttempts?: boolean) =>
    ipcRenderer.invoke('db:claimConversationForPosting', id, resetAttempts),
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
  listenFinalize: (sessionId: string) => ipcRenderer.send('omi-listen:finalize', sessionId),
  onListenMessage: (cb: (msg: ListenMessage) => void) => {
    const listener = (_e: Electron.IpcRendererEvent, msg: ListenMessage): void => cb(msg)
    ipcRenderer.on('omi-listen:message', listener)
    return () => ipcRenderer.removeListener('omi-listen:message', listener)
  },
  captureCommand: (cmd: CaptureCommand) => ipcRenderer.send('omi-capture:cmd', cmd),
  onCaptureCommand: (cb: (cmd: CaptureCommand, ownerId: number) => void) => {
    const listener = (
      _e: Electron.IpcRendererEvent,
      payload: { cmd: CaptureCommand; ownerId: number }
    ): void => cb(payload.cmd, payload.ownerId)
    ipcRenderer.on('omi-capture:cmd', listener)
    return () => ipcRenderer.removeListener('omi-capture:cmd', listener)
  },
  captureEmit: (event: CaptureEvent, ownerId?: number) =>
    ipcRenderer.send('omi-capture:event', { event, ownerId }),
  onCaptureEvent: (cb: (e: CaptureEvent) => void) => {
    const listener = (_e: Electron.IpcRendererEvent, ev: CaptureEvent): void => cb(ev)
    ipcRenderer.on('omi-capture:event', listener)
    return () => ipcRenderer.removeListener('omi-capture:event', listener)
  },
  allowVirtualMic: process.env.OMI_ALLOW_VIRTUAL_MIC === '1',
  e2e: process.env.OMI_E2E === '1',
  // Offline fake-auth for the shell E2E (survives production builds). Gated on a
  // dedicated flag the app never sets itself, so it can never activate in normal
  // use — and separate from OMI_E2E so the bar/meeting/lifecycle specs (which set
  // only OMI_E2E) still boot to the signed-out screen. See lib/dev/e2eAuth.
  e2eFakeAuth: process.env.OMI_E2E_FAKE_AUTH === '1',
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
  openCheckout: (url: string) => ipcRenderer.invoke('billing:openCheckout', url),
  openExternalUrl: (url: string) => ipcRenderer.invoke('billing:openExternal', url),
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
  signInWithGoogle: () => ipcRenderer.invoke('auth:google:signIn'),
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
  codingAgentList: (commandOverrides?: CodingAgentCommandOverrides) =>
    ipcRenderer.invoke('codingAgent:list', commandOverrides),
  codingAgentRun: (args: CodingAgentRunArgs) => ipcRenderer.invoke('codingAgent:run', args),
  codingAgentCancel: (taskId: string) => ipcRenderer.invoke('codingAgent:cancel', taskId),
  codingAgentTest: (agentId: CodingAgentId, commandOverrides?: CodingAgentCommandOverrides) =>
    ipcRenderer.invoke('codingAgent:test', agentId, commandOverrides),
  onCodingAgentEvent: (cb: (event: CodingAgentEvent) => void) => {
    const listener = (_e: Electron.IpcRendererEvent, event: CodingAgentEvent): void => cb(event)
    ipcRenderer.on('codingAgent:event', listener)
    return () => ipcRenderer.removeListener('codingAgent:event', listener)
  },
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
  meetingGetSettings: () => ipcRenderer.invoke('meeting:getSettings'),
  meetingGetToast: () => ipcRenderer.invoke('meeting:getToast'),
  meetingSetSettings: (patch) => ipcRenderer.invoke('meeting:setSettings', patch),
  meetingAction: (meetingId, action) => ipcRenderer.send('meeting:action', meetingId, action),
  onMeetingToast: (cb) => {
    const listener = (_e: Electron.IpcRendererEvent, p: MeetingToastPayload): void => cb(p)
    ipcRenderer.on('meeting:toast', listener)
    return () => ipcRenderer.removeListener('meeting:toast', listener)
  },
  onWhatsNewToast: (cb) => {
    const listener = (_e: Electron.IpcRendererEvent, p: WhatsNewPayload): void => cb(p)
    ipcRenderer.on('whatsnew:toast', listener)
    return () => ipcRenderer.removeListener('whatsnew:toast', listener)
  },
  whatsNewGetPending: () => ipcRenderer.invoke('whatsnew:getPending'),
  whatsNewOpenNotes: () => ipcRenderer.send('whatsnew:openNotes'),
  perfFirstPaint: () => ipcRenderer.send('perf:firstPaint'),
  perfMark: (name: string) => ipcRenderer.send('perf:mark', name),
  // Main-window chrome: whether the window was created with a Windows 11 Mica
  // background material (renderer goes translucent so the material shows).
  // Passed via additionalArguments at window construction.
  micaEnabled: process.argv.includes('--omi-mica=1'),
  perfAnimResult: (stats: Record<string, number>) => ipcRenderer.send('perf:animResult', stats),
  isAnimBench: process.env.OMI_ANIM_BENCH === '1',
  benchEcho: (x: number) => ipcRenderer.invoke('bench:echo', x),
  isBench: process.env.OMI_BENCH === '1',
  // True only in the E2E harness (OMI_E2E=1) — gates renderer-side test hooks
  // (e.g. the capture window's YAMNet classify hook). Never true in prod.
  isE2E: process.env.OMI_E2E === '1',
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
  },
  // --- Bar chat bridge (main-window side) ---
  onBarChatSend: (cb: (payload: { text: string; fromVoice: boolean }) => void) => {
    const listener = (
      _e: Electron.IpcRendererEvent,
      payload: { text: string; fromVoice: boolean }
    ): void => cb(payload)
    ipcRenderer.on('chat:barSend', listener)
    return () => ipcRenderer.removeListener('chat:barSend', listener)
  },
  onBarRequestChatState: (cb: () => void) => {
    const listener = (): void => cb()
    ipcRenderer.on('chat:barRequestState', listener)
    return () => ipcRenderer.removeListener('chat:barRequestState', listener)
  },
  publishChatState: (state: BarChatState) => ipcRenderer.send('chat:publishState', state),
  // --- Tray + lifecycle (Phase 1) ---
  trayReportState: (state) => ipcRenderer.send('tray:state', state),
  onTrayToggleListening: (cb: () => void) => {
    const listener = (): void => cb()
    ipcRenderer.on('tray:toggle-listening', listener)
    return () => ipcRenderer.removeListener('tray:toggle-listening', listener)
  },
  onTrayOpenSettings: (cb: () => void) => {
    const listener = (): void => cb()
    ipcRenderer.on('tray:open-settings', listener)
    return () => ipcRenderer.removeListener('tray:open-settings', listener)
  },
  getLoginItemSettings: () => ipcRenderer.invoke('app:get-login-item'),
  setLaunchAtLogin: (enabled: boolean) => ipcRenderer.invoke('app:set-login-item', enabled),
  quitApp: () => ipcRenderer.send('app:quit'),
  onUpdateReady: (cb: (info: { version: string }) => void) => {
    const listener = (_e: Electron.IpcRendererEvent, info: { version: string }): void => cb(info)
    ipcRenderer.on('update:ready', listener)
    return () => ipcRenderer.removeListener('update:ready', listener)
  },
  getRecordHotkey: () => ipcRenderer.invoke('shortcuts:get-record'),
  setRecordHotkey: (accelerator: string) => ipcRenderer.invoke('shortcuts:set-record', accelerator),
  getSummonHotkey: () => ipcRenderer.invoke('shortcuts:get-summon'),
  setSummonHotkey: (accelerator: string) => ipcRenderer.invoke('shortcuts:set-summon', accelerator),
  getAppVersion: () => ipcRenderer.invoke('app:get-version'),
  checkForUpdates: () => ipcRenderer.invoke('update:check'),
  getPendingUpdate: () => ipcRenderer.invoke('update:get-pending'),
  suspendShortcutCapture: () => ipcRenderer.send('shortcuts:suspend-capture'),
  resumeShortcutCapture: () => ipcRenderer.send('shortcuts:resume-capture')
}

const omiOverlay: OmiOverlayApi = {
  onShown: (cb: () => void) => {
    const listener = (): void => cb()
    ipcRenderer.on('overlay:shown', listener)
    return () => ipcRenderer.removeListener('overlay:shown', listener)
  },
  hide: () => ipcRenderer.send('overlay:hide'),
  setEnabled: (enabled: boolean) => ipcRenderer.send('overlay:setEnabled', enabled),
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

const omiBar: OmiBarApi = {
  ready: () => ipcRenderer.send('bar:ready'),
  showAck: (token: number) => ipcRenderer.send('bar:showAck', token),
  requestHide: () => ipcRenderer.send('bar:requestHide'),
  expand: () => ipcRenderer.send('bar:expand'),
  collapse: () => ipcRenderer.send('bar:collapse'),
  setInteractive: (interactive: boolean) => ipcRenderer.send('bar:setInteractive', interactive),
  keepAlive: (active: boolean) => ipcRenderer.send('bar:keepAlive', active),
  sendChat: (text: string, fromVoice: boolean) =>
    ipcRenderer.send('bar:sendChat', { text, fromVoice }),
  requestChatState: () => ipcRenderer.send('bar:requestChatState'),
  onChatState: (cb: (state: BarChatState) => void) => {
    const listener = (_e: Electron.IpcRendererEvent, state: BarChatState): void => cb(state)
    ipcRenderer.on('chat:state', listener)
    return () => ipcRenderer.removeListener('chat:state', listener)
  },
  onShow: (cb: (p: BarShowPayload) => void) => {
    const listener = (_e: Electron.IpcRendererEvent, p: BarShowPayload): void => cb(p)
    ipcRenderer.on('bar:show', listener)
    return () => ipcRenderer.removeListener('bar:show', listener)
  },
  onMode: (cb: (mode: BarMode) => void) => {
    const listener = (_e: Electron.IpcRendererEvent, mode: BarMode): void => cb(mode)
    ipcRenderer.on('bar:mode', listener)
    return () => ipcRenderer.removeListener('bar:mode', listener)
  },
  onWillHide: (cb: () => void) => {
    const listener = (): void => cb()
    ipcRenderer.on('bar:willHide', listener)
    return () => ipcRenderer.removeListener('bar:willHide', listener)
  },
  onPtt: (cb: (phase: 'down' | 'up') => void) => {
    const listener = (_e: Electron.IpcRendererEvent, phase: 'down' | 'up'): void => cb(phase)
    ipcRenderer.on('bar:ptt', listener)
    return () => ipcRenderer.removeListener('bar:ptt', listener)
  },
  getContentProtection: () => ipcRenderer.invoke('bar:getContentProtection'),
  setContentProtection: (enabled: boolean) =>
    ipcRenderer.invoke('bar:setContentProtection', enabled)
}

if (process.contextIsolated) {
  try {
    contextBridge.exposeInMainWorld('electron', electronAPI)
    contextBridge.exposeInMainWorld('omi', omi)
    contextBridge.exposeInMainWorld('omiOverlay', omiOverlay)
    contextBridge.exposeInMainWorld('omiBar', omiBar)
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
  // @ts-ignore (define in dts)
  window.omiBar = omiBar
}
