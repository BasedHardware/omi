// src/renderer/src/lib/screenRedact.ts
//
// The context predicates now live in `shared/screenPrivacy.ts` so the
// main-process proactive assistants can apply the exact same gate before a
// frame's pixels leave the device. Re-exported here so existing renderer
// callers keep importing them from this module.
export {
  DEFAULT_DENYLIST,
  isPrivateWindow,
  isDeniedContext
} from '../../../shared/screenPrivacy'

const PATTERNS: RegExp[] = [
  /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g,
  /\b(?:\d[ -]?){13,19}\b/g,
  /\b\d{3}-\d{2}-\d{4}\b/g,
  /\beyJ[A-Za-z0-9_-]{2,}\.[A-Za-z0-9_-]{3,}(?:\.[A-Za-z0-9_-]+)?\b/g,
  /\b[A-Fa-f0-9]{32,}\b/g,
  /\b[A-Za-z0-9_-]{40,}\b/g
]

export function redact(text: string): string {
  let out = text
  for (const re of PATTERNS) out = out.replace(re, '[redacted]')
  return out
}

// Redact the frame fields that get sent to the LLM — the OCR body AND the window
// title (titles often carry emails/subjects/PII). Generic so it doesn't couple to
// the RewindFrame type.
export function redactFrameFields<T extends { ocrText: string; windowTitle: string }>(f: T): T {
  return { ...f, ocrText: redact(f.ocrText), windowTitle: redact(f.windowTitle) }
}
