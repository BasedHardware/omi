// Agent activity indicator.
//
// While Cortex's agent is taking actions on the user's machine it works in the
// BACKGROUND (it never steals focus), and signals what it's doing by glowing the
// screen edges in Cortex blue. This is a transparent, click-through, always-on-top
// full-screen window so the glow shows over whatever app the agent is driving,
// without intercepting any of the user's clicks or keystrokes.
import { BrowserWindow, screen } from 'electron'

const ACCENT = '#2f6bff'

// Inline page: a blue glowing inset border with a gentle pulse. Body is fully
// transparent and ignores pointer events.
const OVERLAY_HTML = `data:text/html;charset=utf-8,${encodeURIComponent(`
<!doctype html><html><head><meta charset="utf-8"><style>
  html,body{margin:0;height:100%;background:transparent;overflow:hidden;pointer-events:none}
  .edge{position:fixed;inset:0;border:3px solid ${ACCENT};border-radius:10px;
    box-shadow:inset 0 0 24px 4px ${ACCENT}99, 0 0 18px 2px ${ACCENT}66;
    animation:pulse 1.6s ease-in-out infinite}
  @keyframes pulse{0%,100%{opacity:.55}50%{opacity:1}}
</style></head><body><div class="edge"></div></body></html>
`)}`

let overlay: BrowserWindow | null = null
let active = false

function ensureOverlay(): BrowserWindow {
  if (overlay && !overlay.isDestroyed()) return overlay
  const { bounds } = screen.getPrimaryDisplay()
  overlay = new BrowserWindow({
    x: bounds.x,
    y: bounds.y,
    width: bounds.width,
    height: bounds.height,
    frame: false,
    transparent: true,
    resizable: false,
    movable: false,
    minimizable: false,
    maximizable: false,
    skipTaskbar: true,
    focusable: false,
    show: false,
    alwaysOnTop: true,
    hasShadow: false,
    // Don't activate/steal focus when shown.
    webPreferences: { contextIsolation: true }
  })
  overlay.setIgnoreMouseEvents(true, { forward: true })
  overlay.setAlwaysOnTop(true, 'screen-saver')
  overlay.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })
  void overlay.loadURL(OVERLAY_HTML)
  return overlay
}

/** Whether the agent is currently performing actions. */
export function isAgentActive(): boolean {
  return active
}

/**
 * Toggle the agent-activity state: show/hide the blue edge glow and broadcast
 * `agent:active` to every renderer (so in-app surfaces can react too).
 */
export function setAgentActive(next: boolean): void {
  if (next === active) return
  active = next
  try {
    const win = ensureOverlay()
    if (next) {
      win.showInactive() // show without taking focus → stays in the background
    } else {
      win.hide()
    }
  } catch {
    /* overlay best-effort; never block the agent on UI */
  }
  for (const w of BrowserWindow.getAllWindows()) {
    if (overlay && w.id === overlay.id) continue
    w.webContents.send('agent:active', next)
  }
}

/** Run an async agent task with the edge glow shown for its duration. */
export async function withAgentActive<T>(fn: () => Promise<T>): Promise<T> {
  setAgentActive(true)
  try {
    return await fn()
  } finally {
    setAgentActive(false)
  }
}
