import { invoke } from '@tauri-apps/api/core'
import { listen, type UnlistenFn } from '@tauri-apps/api/event'
import type {
  AppUsageRecord,
  CalendarItem,
  ExportMemory,
  FileIndexDigest,
  FileIndexStatus,
  GmailItem,
  GoogleSource,
  GoogleStatus,
  InsightPayload,
  InsightRecord,
  InsightSettings,
  IndexedAppRecord,
  IndexedFileRecord,
  KgSqlResult,
  KnowledgeGraph,
  ListenMessage,
  ListenStartArgs,
  LocalConversation,
  LocalKGStatus,
  LocalKnowledgeGraph,
  MemoryExportResult,
  OnboardingGraphEdge,
  OnboardingGraphNode,
  RewindFrame,
  RewindSearchGroup,
  RewindSettings,
  ScreenFrameLite,
  ScreenSynthState,
  StickyNotesReadResult,
  UsageSettings
} from '../../../shared/types'

const conversationsChanged = 'omi://conversations-changed'
const overlayShown = 'omi://overlay-shown'
const overlayWillHide = 'omi://overlay-will-hide'
const overlaySummoned = 'omi://overlay-summoned'
const overlayError = 'omi://overlay-error'
const overlayActive = 'omi://overlay-active'
const overlayVisibility = 'omi://overlay-visibility'
const overlayVoiceCaptured = 'omi://overlay-voice-captured'
const overlayAsked = 'omi://overlay-asked'

type OverlayVisibility = { open: boolean; active: boolean }
type NotionExport = { parentPageId: string; memories: ExportMemory[] }
type FileIndexCapabilities = {
  startMenuShortcuts: { supported: boolean; reason?: string }
}
type RewindCaptureCapability = {
  supported: boolean
  reason: string
}
export type AgentRuntimeEvent = {
  type: string
  requestId?: string
  clientId?: string
  sessionId?: string
  text?: string
  terminalStatus?: string
  message?: string
  failure?: { userMessage?: string }
}

function eventListener<T>(event: string, callback: (payload: T) => void): () => void {
  let unlisten: UnlistenFn | undefined
  let closed = false
  void listen<T>(event, ({ payload }) => callback(payload)).then((next) => {
    if (closed) void next()
    else unlisten = next
  }).catch((error: unknown) => console.error(`Failed to subscribe to native event ${event}:`, error))
  return () => {
    closed = true
    unlisten?.()
  }
}
const listenMessage = 'omi://listen-message'
const rewindSettings = 'omi://rewind-settings'
const insightShown = 'omi://insight-show'

export const native = {
  agentRuntimeDispatch(payload: Record<string, unknown>): Promise<void> {
    return invoke('agent_runtime_dispatch', { payload })
  },
  agentRuntimeRequest(payload: Record<string, unknown>): Promise<AgentRuntimeEvent> {
    return invoke<AgentRuntimeEvent>('agent_runtime_request', { payload })
  },
  onAgentRuntimeEvent(callback: (event: AgentRuntimeEvent) => void): Promise<UnlistenFn> {
    return listen<AgentRuntimeEvent>('omi://agent-runtime', ({ payload }) => callback(payload))
  },
  automationCapabilities(): Promise<{ supported: boolean; reason?: string }> {
    return invoke<{ supported: boolean; reason?: string }>('automation_capabilities')
  },
  automationTargetWindow(): Promise<string | null> {
    return invoke<string | null>('automation_target_window')
  },
  automationSnapshot(windowHandle?: string): Promise<import('../../../shared/types').UiSnapshot> {
    return invoke<import('../../../shared/types').UiSnapshot>('automation_snapshot', { windowHandle })
  },
  automationConfirmRun(plan: import('../../../shared/types').AutomationPlan): Promise<{ ok: boolean; canceled?: boolean; message?: string }> {
    return invoke('automation_confirm_run', { plan })
  },
  getLocalConversation(id: string): Promise<LocalConversation | null> {
    return invoke<LocalConversation | null>('local_conversation_get', { id })
  },
  listLocalConversations(): Promise<LocalConversation[]> {
    return invoke<LocalConversation[]>('local_conversation_list')
  },
  async insertLocalConversation(conversation: LocalConversation): Promise<void> {
    await invoke('local_conversation_upsert', { conversation })
  },
  async deleteLocalConversation(id: string): Promise<void> {
    await invoke('local_conversation_delete', { id })
  },
  async updateLocalConversationTitle(id: string, title: string): Promise<void> {
    await invoke('local_conversation_update_title', { id, title })
  },
  async listenStart(args: ListenStartArgs): Promise<void> {
    await invoke('listen_start', { args })
  },
  async listenStop(sessionId: string): Promise<void> {
    await invoke('listen_stop', { sessionId })
  },
  async listenFeed(sessionId: string, pcm: Uint8Array): Promise<void> {
    await invoke('listen_feed', { sessionId, pcm })
  },
  fileIndexScan(): Promise<FileIndexStatus> {
    return invoke<FileIndexStatus>('file_index_scan')
  },
  fileIndexStatus(): Promise<FileIndexStatus> {
    return invoke<FileIndexStatus>('file_index_status')
  },
  fileIndexApps(limit?: number): Promise<IndexedAppRecord[]> {
    return invoke<IndexedAppRecord[]>('file_index_apps', { limit })
  },
  fileIndexCapabilities(): Promise<FileIndexCapabilities> {
    return invoke<FileIndexCapabilities>('file_index_capabilities')
  },
  kgFileIndexDigest(): Promise<FileIndexDigest> {
    return invoke<FileIndexDigest>('kg_file_index_digest')
  },
  async kgSaveGraph(graph: LocalKnowledgeGraph): Promise<void> {
    await invoke('kg_save_graph', { graph })
  },
  kgStatus(): Promise<LocalKGStatus> {
    return invoke<LocalKGStatus>('kg_status')
  },
  appUsageList(): Promise<AppUsageRecord[]> {
    return invoke<AppUsageRecord[]>('app_usage_list')
  },
  usageFlush(): Promise<AppUsageRecord[]> {
    return invoke<AppUsageRecord[]>('usage_flush')
  },
  usageGetSettings(): Promise<UsageSettings> {
    return invoke<UsageSettings>('usage_get_settings')
  },
  usageSetSettings(settings: UsageSettings): Promise<UsageSettings> {
    return invoke<UsageSettings>('usage_set_settings', { settings })
  },
  memoryImportParse(dump: string): Promise<string[]> {
    return invoke<string[]>('memory_import_parse', { dump })
  },
  memoryExportObsidian(memories: ExportMemory[]): Promise<MemoryExportResult> {
    return invoke<MemoryExportResult>('memory_export_obsidian', { memories })
  },
  memoryExportFile(memories: ExportMemory[]): Promise<MemoryExportResult> {
    return invoke<MemoryExportResult>('memory_export_file', { memories })
  },
  memoryExportNotion(args: NotionExport): Promise<MemoryExportResult> {
    return invoke<MemoryExportResult>('memory_export_notion', { args })
  },
  notionSetToken(token: string): Promise<void> { return invoke('notion_set_token', { token }) },
  notionClearToken(): Promise<void> { return invoke('notion_clear_token') },
  authGoogleSignIn(): Promise<string> { return invoke<string>('auth_google_sign_in') },
  googleStatus(): Promise<GoogleStatus> { return invoke<GoogleStatus>('google_status') },
  googleConnect(): Promise<GoogleStatus> { return invoke<GoogleStatus>('google_connect') },
  googleDisconnect(): Promise<GoogleStatus> { return invoke<GoogleStatus>('google_disconnect') },
  googleGmailFetchNew(): Promise<{ ok: boolean; items: GmailItem[]; error?: string }> { return invoke('google_gmail_fetch_new') },
  googleCalendarFetchNew(): Promise<{ ok: boolean; items: CalendarItem[]; error?: string }> { return invoke('google_calendar_fetch_new') },
  googleMarkProcessed(source: GoogleSource, ids: string[]): Promise<void> { return invoke('google_mark_processed', { source, ids }) },
  readStickyNotes(): Promise<StickyNotesReadResult> { return invoke<StickyNotesReadResult>('sticky_notes_read') },
  kgQueryNodes(query: string, limit?: number): Promise<LocalKnowledgeGraph> {
    return invoke<LocalKnowledgeGraph>('kg_query_nodes', { query, limit })
  },
  kgSearchFiles(query: string, fileType?: string, limit?: number): Promise<IndexedFileRecord[]> {
    return invoke<IndexedFileRecord[]>('kg_search_files', { query, fileType, limit })
  },
  kgExecuteSql(sql: string): Promise<KgSqlResult> {
    return invoke<KgSqlResult>('kg_execute_sql', { sql })
  },
  localGraphLoad(): Promise<KnowledgeGraph> {
    return invoke<KnowledgeGraph>('local_graph_load')
  },
  localGraphUpsert(
    nodes: OnboardingGraphNode[],
    edges: OnboardingGraphEdge[]
  ): Promise<KnowledgeGraph> {
    return invoke<KnowledgeGraph>('local_graph_upsert', { nodes, edges })
  },
  async localGraphClear(): Promise<void> {
    await invoke('local_graph_clear')
  },
  onListenMessage(callback: (message: ListenMessage) => void): Promise<UnlistenFn> {
    return listen<ListenMessage>(listenMessage, (event) => callback(event.payload))
  },
  onConversationsChanged(callback: () => void): () => void {
    return eventListener(conversationsChanged, callback)
  }
}

export const rewind = {
  frames(from: number, to: number): Promise<RewindFrame[]> {
    return invoke<RewindFrame[]>('rewind_frames', { from, to })
  },
  dayBounds(): Promise<{ min: number; max: number } | null> {
    return invoke<{ min: number; max: number } | null>('rewind_day_bounds')
  },
  search(query: string): Promise<RewindSearchGroup[]> {
    return invoke<RewindSearchGroup[]>('rewind_search', { query })
  },
  frameImage(imagePath: string): Promise<string> {
    return invoke<string>('rewind_frame_image', { imagePath })
  },
  getSettings(): Promise<RewindSettings> {
    return invoke<RewindSettings>('rewind_get_settings')
  },
  captureCapability(): Promise<RewindCaptureCapability> {
    return invoke<RewindCaptureCapability>('rewind_capture_capability')
  },
  requestCapturePermission(): Promise<RewindCaptureCapability> {
    return invoke<RewindCaptureCapability>('rewind_request_capture_permission')
  },
  setSettings(settings: RewindSettings): Promise<RewindSettings> {
    return invoke<RewindSettings>('rewind_set_settings', { settings })
  },
  pruneNow(): Promise<number> {
    return invoke<number>('rewind_prune_now')
  },
  onSettings(callback: (settings: RewindSettings) => void): () => void {
    return eventListener(rewindSettings, callback)
  }
}

export const screen = {
  readText(): Promise<string> {
    return invoke<string>('screen_read_text')
  }
}

export const screenSynth = {
  getState(): Promise<ScreenSynthState> { return invoke<ScreenSynthState>('screen_synth_get_state') },
  setState(patch: Partial<ScreenSynthState>): Promise<ScreenSynthState> { return invoke<ScreenSynthState>('screen_synth_set_state', { patch }) },
  framesSince(): Promise<ScreenFrameLite[]> { return invoke<ScreenFrameLite[]>('screen_synth_frames_since') },
  advanceWatermark(ts: number): Promise<void> { return invoke('screen_synth_advance_watermark', { ts }) },
  recordRun(run: { lastRunAt: number; lastCount: number }): Promise<ScreenSynthState> { return invoke<ScreenSynthState>('screen_synth_record_run', { run }) }
}

export const insights = {
  getSettings(): Promise<InsightSettings> { return invoke<InsightSettings>('insight_get_settings') },
  setSettings(patch: Partial<InsightSettings>): Promise<InsightSettings> { return invoke<InsightSettings>('insight_set_settings', { patch }) },
  add(payload: InsightPayload): Promise<number> { return invoke<number>('insight_add', { payload }) },
  recent(limit: number): Promise<InsightRecord[]> { return invoke<InsightRecord[]>('insight_recent', { limit }) },
  show(payload: InsightPayload): Promise<void> { return invoke('insight_show', { payload }) },
  dismiss(): Promise<void> { return invoke('insight_dismiss') },
  test(): Promise<void> { return invoke('insight_test') },
  onShown(callback: (payload: InsightPayload) => void): () => void { return eventListener(insightShown, callback) }
}

export const overlay = {
  hide(): Promise<void> {
    return invoke('overlay_hide')
  },
  setEnabled(enabled: boolean): Promise<void> {
    return invoke('overlay_set_enabled', { enabled })
  },
  setHeight(px: number): Promise<void> {
    return invoke('overlay_set_height', { px })
  },
  focusMain(): Promise<void> {
    return invoke('overlay_focus_main')
  },
  setAccelerator(accelerator: string): Promise<boolean> {
    return invoke<boolean>('overlay_set_accelerator', { accelerator })
  },
  suspendShortcut(): Promise<void> {
    return invoke('overlay_suspend_shortcut')
  },
  resumeShortcut(): Promise<boolean> {
    return invoke<boolean>('overlay_resume_shortcut')
  },
  notifyVoiceCaptured(): Promise<void> {
    return invoke('overlay_notify_voice_captured')
  },
  notifyAsked(): Promise<void> {
    return invoke('overlay_notify_asked')
  },
  onShown(callback: () => void): () => void {
    return eventListener(overlayShown, callback)
  },
  onWillHide(callback: () => void): () => void {
    return eventListener(overlayWillHide, callback)
  },
  onSummoned(callback: () => void): () => void {
    return eventListener(overlaySummoned, callback)
  },
  onSummonedReady(callback: () => void): Promise<UnlistenFn> {
    return listen<void>(overlaySummoned, () => callback())
  },
  onError(callback: (message: string) => void): () => void {
    return eventListener(overlayError, callback)
  },
  onActiveChange(callback: (active: boolean) => void): () => void {
    return eventListener(overlayActive, callback)
  },
  onVisibilityChange(callback: (state: OverlayVisibility) => void): () => void {
    return eventListener(overlayVisibility, callback)
  },
  onVoiceCaptured(callback: () => void): () => void {
    return eventListener(overlayVoiceCaptured, callback)
  },
  onAsked(callback: () => void): () => void {
    return eventListener(overlayAsked, callback)
  }
}
