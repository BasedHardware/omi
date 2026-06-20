import type {
  ObservabilityBreadcrumb,
  ObservabilityEvent,
  ObservabilityLevel
} from '../../../shared/types'
import {
  errorToObservabilityPayload,
  sanitizeObservabilityValue
} from '../../../shared/observabilityRedaction'

const MAX_BREADCRUMBS = 60

let initialized = false
const breadcrumbs: ObservabilityBreadcrumb[] = []

function sendEvent(event: ObservabilityEvent): void {
  window.omi?.observabilityCapture(sanitizeObservabilityValue(event) as ObservabilityEvent)
}

function sendBreadcrumb(breadcrumb: ObservabilityBreadcrumb): void {
  window.omi?.observabilityBreadcrumb(
    sanitizeObservabilityValue(breadcrumb) as ObservabilityBreadcrumb
  )
}

function messageFrom(error: unknown): string {
  if (error instanceof Error) return error.message
  return String(error)
}

export function addObservabilityBreadcrumb(
  name: string,
  data: Record<string, unknown> = {},
  options: { category?: string; level?: ObservabilityLevel } = {}
): void {
  const breadcrumb = sanitizeObservabilityValue({
    name,
    category: options.category ?? 'renderer',
    level: options.level ?? 'info',
    data,
    ts: Date.now()
  }) as ObservabilityBreadcrumb
  breadcrumbs.push(breadcrumb)
  if (breadcrumbs.length > MAX_BREADCRUMBS) breadcrumbs.shift()
  sendBreadcrumb(breadcrumb)
}

export function captureRendererException(
  name: string,
  error: unknown,
  data: Record<string, unknown> = {},
  level: ObservabilityLevel = 'error'
): void {
  sendEvent({
    source: 'renderer',
    kind: level === 'warning' ? 'warning' : 'exception',
    name,
    category: 'renderer',
    level,
    message: messageFrom(error),
    error: errorToObservabilityPayload(error),
    data,
    breadcrumbs: breadcrumbs.slice(),
    ts: Date.now()
  })
}

function targetInfo(target: EventTarget | null): Record<string, unknown> {
  if (!(target instanceof HTMLElement)) return {}
  return {
    tagName: target.tagName,
    id: target.id,
    className: target.className,
    source:
      target instanceof HTMLImageElement || target instanceof HTMLScriptElement
        ? target.src
        : undefined
  }
}

export function initRendererObservability(): void {
  if (initialized) return
  initialized = true
  addObservabilityBreadcrumb('renderer.observability_ready', {}, { category: 'app' })

  window.addEventListener('error', (event) => {
    const error = event.error ?? new Error(event.message || 'renderer window error')
    captureRendererException('renderer.window_error', error, {
      filename: event.filename,
      lineno: event.lineno,
      colno: event.colno,
      target: targetInfo(event.target)
    })
  })

  window.addEventListener('unhandledrejection', (event) => {
    sendEvent({
      source: 'renderer',
      kind: 'unhandled-rejection',
      name: 'renderer.unhandled_rejection',
      category: 'renderer',
      level: 'error',
      message: messageFrom(event.reason),
      error: errorToObservabilityPayload(event.reason),
      breadcrumbs: breadcrumbs.slice(),
      ts: Date.now()
    })
  })
}
