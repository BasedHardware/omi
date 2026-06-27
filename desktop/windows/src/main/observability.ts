import { app, ipcMain } from 'electron'
import { appendFileSync, mkdirSync } from 'fs'
import { dirname, join } from 'path'
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

let initialized = false
let ipcRegistered = false
let sinkPath: string | null = null
const breadcrumbs: ObservabilityBreadcrumb[] = []

type BreadcrumbOptions = {
  category?: string
  level?: ObservabilityLevel
  source?: ObservabilitySource
  persist?: boolean
}

function eventSinkPath(): string {
  if (!sinkPath) sinkPath = join(app.getPath('userData'), OBSERVABILITY_FILE)
  return sinkPath
}

function writeEvent(event: Record<string, unknown>): void {
  try {
    const path = eventSinkPath()
    mkdirSync(dirname(path), { recursive: true })
    appendFileSync(path, `${JSON.stringify(event)}\n`, 'utf8')
  } catch (error) {
    console.warn('[observability] failed to write event:', sanitizeObservabilityValue(error))
  }
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
  fallbackSource: ObservabilitySource = 'main'
): void {
  writeEvent(normalizedEvent(event, fallbackSource))
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
  captureObservabilityEvent({
    source: 'main',
    kind: level === 'warning' ? 'warning' : 'exception',
    name,
    level,
    message: error instanceof Error ? error.message : String(error),
    error: errorToObservabilityPayload(error),
    data
  })
}

function registerProcessHandlers(): void {
  process.on('uncaughtExceptionMonitor', (error, origin) => {
    captureMainException('main.uncaught_exception', error, { origin }, 'fatal')
  })
  process.on('unhandledRejection', (reason) => {
    captureObservabilityEvent({
      source: 'main',
      kind: 'unhandled-rejection',
      name: 'main.unhandled_rejection',
      level: 'error',
      message: reason instanceof Error ? reason.message : String(reason),
      error: errorToObservabilityPayload(reason)
    })
  })
  process.on('warning', (warning) => {
    captureMainException('main.process_warning', warning, { warningName: warning.name }, 'warning')
  })
}

function registerElectronCrashHandlers(): void {
  app.on('render-process-gone', (_event, webContents, details) => {
    captureObservabilityEvent({
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
    })
  })
  app.on('child-process-gone', (_event, details) => {
    captureObservabilityEvent({
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
    })
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
  ipcMain.on('observability:capture', (_event, rawEvent: unknown) => {
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
  ipcMain.on('observability:breadcrumb', (_event, rawBreadcrumb: unknown) => {
    const breadcrumb = safeRecord(rawBreadcrumb) as Partial<ObservabilityBreadcrumb>
    const data = safeRecord(breadcrumb.data)
    addObservabilityBreadcrumb(safeName(breadcrumb.name, 'renderer.breadcrumb'), data, {
      category: typeof breadcrumb.category === 'string' ? breadcrumb.category : 'renderer',
      level: normalizeLevel(breadcrumb.level, 'info'),
      source: 'renderer'
    })
  })
}
