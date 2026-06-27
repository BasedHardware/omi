// src/renderer/src/lib/screenRedact.ts
export const DEFAULT_DENYLIST: string[] = [
  '1password', 'bitwarden', 'keepass', 'lastpass', 'dashlane',
  'windows security', 'windows hello', 'log in', 'login', 'sign in',
  'password', 'bank', 'chase', 'wells fargo', 'paypal', 'coinbase'
]

const PRIVATE_MARKERS = ['incognito', 'inprivate', 'private browsing']

export function isPrivateWindow(windowTitle: string): boolean {
  const t = windowTitle.toLowerCase()
  return PRIVATE_MARKERS.some((m) => t.includes(m))
}

export function isDeniedContext(ctx: {
  app: string
  windowTitle: string
  processName: string
}): boolean {
  const hay = `${ctx.app} ${ctx.windowTitle} ${ctx.processName}`.toLowerCase()
  return DEFAULT_DENYLIST.some((n) => hay.includes(n))
}

// Credit-card-like run: 13-19 digits with optional space/hyphen separators.
const CARD = /\b(?:\d[ -]?){13,19}\b/g

const PATTERNS: RegExp[] = [
  /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g,
  /\b\d{3}-\d{2}-\d{4}\b/g,
  /\beyJ[A-Za-z0-9_-]{2,}\.[A-Za-z0-9_-]{3,}(?:\.[A-Za-z0-9_-]+)?\b/g,
  /\b[A-Fa-f0-9]{32,}\b/g,
  /\b[A-Za-z0-9_-]{40,}\b/g
]

// A digit string passes the Luhn checksum. Real card numbers do; order numbers,
// 13-digit epoch-ms timestamps and ISBNs almost never do.
function luhnValid(digits: string): boolean {
  let sum = 0
  let alt = false
  for (let i = digits.length - 1; i >= 0; i--) {
    let d = digits.charCodeAt(i) - 48
    if (alt) {
      d *= 2
      if (d > 9) d -= 9
    }
    sum += d
    alt = !alt
  }
  return sum % 10 === 0
}

export function redact(text: string): string {
  let out = text
  // Redact a card-shaped run only when it passes Luhn, so a 13-19 digit order
  // number or timestamp the model needs is not destroyed.
  out = out.replace(CARD, (m) => (luhnValid(m.replace(/\D/g, '')) ? '[redacted]' : m))
  for (const re of PATTERNS) out = out.replace(re, '[redacted]')
  return out
}

// Redact the frame fields that get sent to the LLM — the OCR body AND the window
// title (titles often carry emails/subjects/PII). Generic so it doesn't couple to
// the RewindFrame type.
export function redactFrameFields<T extends { ocrText: string; windowTitle: string }>(f: T): T {
  return { ...f, ocrText: redact(f.ocrText), windowTitle: redact(f.windowTitle) }
}
