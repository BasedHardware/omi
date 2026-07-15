// Pure privacy predicates over a captured frame's window metadata. They live in
// `shared/` (not the renderer) because BOTH sides need them now: the renderer's
// Insight engine filters its OCR text with them, and the main-process proactive
// assistants must apply the same gate before a frame's *pixels* leave the device.
// `renderer/src/lib/screenRedact.ts` re-exports these, so nothing renderer-side
// had to change.

export const DEFAULT_DENYLIST: string[] = [
  '1password',
  'bitwarden',
  'keepass',
  'lastpass',
  'dashlane',
  'windows security',
  'windows hello',
  'log in',
  'login',
  'sign in',
  'password',
  'bank',
  'chase',
  'wells fargo',
  'paypal',
  'coinbase'
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
