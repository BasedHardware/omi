import { app, ipcMain } from 'electron'
import { appendFileSync, mkdirSync, renameSync, rmSync, statSync } from 'fs'
import { appendFile, mkdir, rename, rm, stat } from 'fs/promises'
import { dirname, join } from 'path'
import type { IpcMainEvent } from 'electron'
import type {
  ObservabilityBreadcrumb,
  ObservabilityEvent,
  ObservabilityLevel,
  ObservabilitySource
} from '../shared/types'
import {
  errorToObservabilityPayload,
  sanitizeObservabilityValue
} from '../shared/observabilityRedaction'

const MAX_BREADCRUMBS = 60
const OBSERVABILITY_FILE = 'observability.jsonl'
const MAX_OBSERVABILITY_FILE_BYTES = 2 * 1024 * 1024
const MAX_OBSERVABILITY_EVENT_BYTES = 256 * 1024
const OBSERVABILITY_IPC_WINDOW_MS = 60_000
const OBSERVABILITY_IPC_MAX_PER_WINDOW = 60

let initialized = false
let ipcRegistered = false
let sinkPath: string | null = null
let writeChain: Promise<void> = Promise.resolve()
const breadcrumbs: ObservabilityBreadcrumb[] = []
const ipcBuckets = new Map<number, { windowStart: number; count: number }>()

type BreadcrumbOptions = {
  category?: string
  level?: ObservabilityLevel
  source?: ObservabilitySource
  persist?: boolean
}

type WriteOptions = {
  sync?: boolean
}

function eventSinkPath(): string {
  if (!sinkPath) sinkPath = join(app.getPath('userData'), OBSERVABILITY_FILE)
  return sinkPath
}

async function rotateSinkIfNeeded(path: string, incomingBytes: number): Promise<void> {
  let currentSize = 0
  try {
    currentSize = (await stat(path)).size
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
  }
  if (currentSize + incomingBytes <= MAX_OBSERVABILITY_FILE_BYTES) return

  const rotated = `${path}.1`
  await rm(rotated, { force: true })
  try {
    await rename(path, rotated)
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
  }
}

async function appendEventLine(line: string): Promise<void> {
  const path = eventSinkPath()
  await mkdir(dirname(path), { recursive: true })
  await rotateSinkIfNeeded(path, Buffer.byteLength(line, 'utf8'))
  await appendFile(path, line, 'utf8')
}

function rotateSinkIfNeededSync(path: string, incomingBytes: number): void {
  let currentSize = 0
  try {
    currentSize = statSync(path).size
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
  }
  if (currentSize + incomingBytes <= MAX_OBSERVABILITY_FILE_BYTES) return

  const rotated = `${path}.1`
  rmSync(rotated, { force: true })
  try {
    renameSync(path, rotated)
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
  }
}

function appendEventLineSync(line: string): void {
  const path = eventSinkPath()
  mkdirSync(dirname(path), { recursive: true })
  rotateSinkIfNeededSync(path, Buffer.byteLength(line, 'utf8'))
  appendFileSync(path, line, 'utf8')
}

function oversizedEventLine(event: Record<string, unknown>, bytes: number): string {
  return `${JSON.stringify({
    source: event.source,
    kind: 'observability-drop',
    name: 'observability.event_too_large',
    level: 'warning',
    message: 'Observability event exceeded the per-event size limit and was not persisted in full.',
    data: {
      originalName: event.name,
      originalKind: event.kind,
      originalBytes: bytes,
      maxBytes: MAX_OBSERVABILITY_EVENT_BYTES
    },
    ts: Date.now()
  })}\n`
}

function serializeEventLine(event: Record<string, unknown>): string {
  const line = `${JSON.stringify(event)}\n`
  const bytes = Buffer.byteLength(line, 'utf8')
  if (bytes <= MAX_OBSERVABILITY_EVENT_BYTES) return line
  return oversizedEventLine(event, bytes)
}

function writeEvent(event: Record<string, unknown>, options: WriteOptions = {}): void {
  const line = serializeEventLine(event)
  if (options.sync) {
    try {
      appendEventLineSync(line)
    } catch (error) {
      console.warn('[observability] failed to write event:', sanitizeObservabilityValue(error))
    }
    return
  }

  writeChain = writeChain
    .then(() => appendEventLine(line))
    .catch((error) => {
      console.warn('[observability] failed to write event:', sanitizeObservabilityValue(error))
    })
}

function trustedRendererUrl(url: string | undefined): boolean {
  if (!url) return false
  try {
    const parsed = new URL(url)
    if (parsed.protocol === 'file:' || parsed.protocol === 'app:') return true
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return false
    return (
      parsed.hostname === 'localhost' ||
      parsed.hostname === '127.0.0.1' ||
      parsed.hostname === '[::1]'
    )
  } catch {
    return false
  }
}

function isTrustedObservabilitySender(event: IpcMainEvent): boolean {
  const frameUrl = event.senderFrame?.url
  if (trustedRendererUrl(frameUrl)) return true
  return trustedRendererUrl(event.sender.getURL())
}

function allowObservabilityIpc(event: IpcMainEvent): boolean {
  if (!isTrustedObservabilitySender(event)) return false

  const id = event.sender.id
  const now = Date.now()
  const bucket = ipcBuckets.get(id)
  if (!bucket || now - bucket.windowStart >= OBSERVABILITY_IPC_WINDOW_MS) {
    ipcBuckets.set(id, { windowStart: now, count: 1 })
    return true
  }
  if (bucket.count >= OBSERVABILITY_IPC_MAX_PER_WINDOW) return false
  bucket.count += 1
  return true
}

function safeRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
  return value as Record<string, unknown>
}

function safeName(value: unknown, fallback: string): string {
  if (typeof value !== 'string') return fallback
  const trimmed = value.trim()
  return trimmed || fallback
}

function normalizeLevel(value: unknown, fallback: ObservabilityLevel): ObservabilityLevel {
  return value === 'debug' ||
    value === 'info' ||
    value === 'warning' ||
    value === 'error' ||
    value === 'fatal'
    ? value
    : fallback
}

function normalizedEvent(
  event: ObservabilityEvent,
  fallbackSource: ObservabilitySource
): Record<string, unknown> {
  const kind = event.kind || 'error'
  const payload = {
    source: event.source ?? fallbackSource,
    kind,
    name: safeName(event.name, `${fallbackSource}.${kind}`),
    category: typeof event.category === 'string' ? event.category : undefined,
    level: normalizeLevel(event.level, kind === 'breadcrumb' ? 'info' : 'error'),
    message: typeof event.message === 'string' ? event.message : undefined,
    error: event.error,
    data: safeRecord(event.data),
    breadcrumbs: kind === 'breadcrumb' ? undefined : (event.breadcrumbs ?? breadcrumbs.slice()),
    ts: typeof event.ts === 'number' ? event.ts : Date.now()
  }
  return sanitizeObservabilityValue(payload) as Record<string, unknown>
}

export function captureObservabilityEvent(
  event: ObservabilityEvent,
  fallbackSource: ObservabilitySource = 'main',
  options: WriteOptions = {}
): void {
  writeEvent(normalizedEvent(event, fallbackSource), options)
}

export function addObservabilityBreadcrumb(
  name: string,
  data: Record<string, unknown> = {},
  options: BreadcrumbOptions = {}
): void {
  const breadcrumb = sanitizeObservabilityValue({
    name,
    category: options.category,
    level: options.level ?? 'info',
    data,
    ts: Date.now()
  }) as ObservabilityBreadcrumb
  breadcrumbs.push(breadcrumb)
  if (breadcrumbs.length > MAX_BREADCRUMBS) breadcrumbs.shift()
  if (options.persist !== false) {
    captureObservabilityEvent(
      {
        source: options.source ?? 'main',
        kind: 'breadcrumb',
        name: breadcrumb.name,
        category: breadcrumb.category,
        level: breadcrumb.level,
        data: breadcrumb.data,
        ts: breadcrumb.ts
      },
      options.source ?? 'main'
    )
  }
}

export function captureMainException(
  name: string,
  error: unknown,
  data: Record<string, unknown> = {},
  level: ObservabilityLevel = 'error'
): void {
  captureObservabilityEvent(
    {
      source: 'main',
      kind: level === 'warning' ? 'warning' : 'exception',
      name,
      level,
      message: error instanceof Error ? error.message : String(error),
      error: errorToObservabilityPayload(error),
      data
    },
    'main',
    { sync: level === 'fatal' }
  )
}

function registerProcessHandlers(): void {
  process.on('uncaughtExceptionMonitor', (error, origin) => {
    captureMainException('main.uncaught_exception', error, { origin }, 'fatal')
  })
  process.on('unhandledRejection', (reason) => {
    captureObservabilityEvent(
      {
        source: 'main',
        kind: 'unhandled-rejection',
        name: 'main.unhandled_rejection',
        level: 'error',
        message: reason instanceof Error ? reason.message : String(reason),
        error: errorToObservabilityPayload(reason)
      },
      'main',
      { sync: true }
    )
  })
  process.on('warning', (warning) => {
    captureMainException('main.process_warning', warning, { warningName: warning.name }, 'warning')
  })
}

function registerElectronCrashHandlers(): void {
  app.on('render-process-gone', (_event, webContents, details) => {
    captureObservabilityEvent(
      {
        source: 'main',
        kind: 'crash',
        name: 'renderer.process_gone',
        level: 'fatal',
        message: details.reason,
        data: {
          reason: details.reason,
          exitCode: details.exitCode,
          url: webContents.getURL()
        }
      },
      'main',
      { sync: true }
    )
  })
  app.on('child-process-gone', (_event, details) => {
    captureObservabilityEvent(
      {
        source: 'main',
        kind: 'crash',
        name: 'electron.child_process_gone',
        level: 'fatal',
        message: details.reason,
        data: {
          type: details.type,
          reason: details.reason,
          exitCode: details.exitCode,
          name: details.name,
          serviceName: details.serviceName
        }
      },
      'main',
      { sync: true }
    )
  })
}

export function initMainObservability(): void {
  if (initialized) return
  initialized = true
  registerProcessHandlers()
  registerElectronCrashHandlers()
  addObservabilityBreadcrumb('app.observability_ready', {}, { category: 'app', persist: false })
}

export function registerObservabilityIpc(): void {
  if (ipcRegistered) return
  ipcRegistered = true
  ipcMain.on('observability:capture', (ipcEvent, rawEvent: unknown) => {
    if (!allowObservabilityIpc(ipcEvent)) return
    const event = safeRecord(rawEvent) as Partial<ObservabilityEvent>
    captureObservabilityEvent(
      {
        kind: event.kind ?? 'error',
        name: safeName(event.name, 'renderer.error'),
        category: typeof event.category === 'string' ? event.category : undefined,
        level: event.level,
        message: typeof event.message === 'string' ? event.message : undefined,
        error: event.error,
        data: safeRecord(event.data),
        breadcrumbs: Array.isArray(event.breadcrumbs) ? event.breadcrumbs : undefined,
        ts: typeof event.ts === 'number' ? event.ts : undefined,
        source: 'renderer'
      },
      'renderer'
    )
  })
  ipcMain.on('observability:breadcrumb', (ipcEvent, rawBreadcrumb: unknown) => {
    if (!allowObservabilityIpc(ipcEvent)) return
    const breadcrumb = safeRecord(rawBreadcrumb) as Partial<ObservabilityBreadcrumb>
    const data = safeRecord(breadcrumb.data)
    addObservabilityBreadcrumb(safeName(breadcrumb.name, 'renderer.breadcrumb'), data, {
      category: typeof breadcrumb.category === 'string' ? breadcrumb.category : 'renderer',
      level: normalizeLevel(breadcrumb.level, 'info'),
      source: 'renderer'
    })
  })
}

export function flushObservabilityWritesForTests(): Promise<void> {
  return writeChain
}

export function resetObservabilityForTests(): void {
  initialized = false
  ipcRegistered = false
  sinkPath = null
  writeChain = Promise.resolve()
  breadcrumbs.length = 0
  ipcBuckets.clear()
}
