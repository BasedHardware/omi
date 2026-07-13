import { BrowserWindow, ipcMain, shell } from 'electron'
import type { CheckoutOutcome } from '../../shared/types'
import { isAllowedExternalScheme } from '../externalUrl'

// Stripe checkout / customer-portal support for the Plan & Usage settings tab.
//
// macOS parity: the Swift app opens Stripe Checkout in an in-app WKWebView sheet
// and watches for the backend's success/cancel redirect to know when the flow
// finished, then re-polls the subscription. We reproduce that contract here with
// a modal Electron BrowserWindow: it loads the Stripe-hosted checkout URL and
// resolves as soon as it navigates to the backend's completion routes. The
// customer portal, by contrast, opens in the SYSTEM browser (matches Mac) — it
// is a full account-management surface, not a single-purpose modal flow.

// The backend redirects Stripe Checkout to these routes on completion. Matching
// on the path (not the full origin) keeps this robust to prod/dev API hosts.
const SUCCESS_PATH = '/v1/payments/success'
const CANCEL_PATH = '/v1/payments/cancel'

function outcomeForUrl(rawUrl: string): CheckoutOutcome | null {
  try {
    const { pathname } = new URL(rawUrl)
    if (pathname.startsWith(SUCCESS_PATH)) return 'success'
    if (pathname.startsWith(CANCEL_PATH)) return 'cancel'
  } catch {
    // Non-parseable navigations (about:blank, data: frames) are ignored.
  }
  return null
}

/**
 * Open a Stripe Checkout URL in a modal in-app window and resolve when the flow
 * completes. Resolves 'success' or 'cancel' when the backend completion route is
 * reached, or 'closed' if the user dismisses the window first. The window is
 * always destroyed before this resolves.
 *
 * Money safety: this only DISPLAYS Stripe's own hosted checkout page. No payment
 * is completed by this code — the user drives (or abandons) the Stripe form.
 */
export function openCheckoutWindow(url: string): Promise<CheckoutOutcome> {
  // Only ever load a real https Stripe/backend URL. A prompt-injected or
  // malformed URL must never be handed to a BrowserWindow.
  let parsed: URL
  try {
    parsed = new URL(url)
  } catch {
    return Promise.reject(new Error('checkout: unparseable URL'))
  }
  if (parsed.protocol !== 'https:') {
    return Promise.reject(new Error('checkout: refusing non-https URL'))
  }

  const parent = BrowserWindow.getFocusedWindow() ?? BrowserWindow.getAllWindows()[0] ?? undefined
  const win = new BrowserWindow({
    width: 480,
    height: 720,
    parent,
    modal: !!parent,
    show: false,
    title: 'Complete your purchase',
    autoHideMenuBar: true,
    webPreferences: {
      // A payment page — keep it fully isolated from app internals.
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true
    }
  })

  return new Promise<CheckoutOutcome>((resolve) => {
    let settled = false
    const finish = (outcome: CheckoutOutcome): void => {
      if (settled) return
      settled = true
      if (!win.isDestroyed()) win.destroy()
      resolve(outcome)
    }

    // A navigation to the completion route ends the flow. `will-redirect` and
    // `will-navigate` catch the 30x hop and any in-page link; `did-navigate`
    // is the backstop for a fully-loaded completion page.
    const onNavigate = (_e: unknown, navUrl: string): void => {
      const outcome = outcomeForUrl(navUrl)
      if (outcome) finish(outcome)
    }
    win.webContents.on('will-redirect', onNavigate)
    win.webContents.on('will-navigate', onNavigate)
    win.webContents.on('did-navigate', onNavigate)

    // User closed the window without completing → treat as cancelled/abandoned.
    win.on('closed', () => finish('closed'))

    win.once('ready-to-show', () => win.show())
    void win.loadURL(url)
  })
}

/** Register the billing IPC surface. Call once during main setup. */
export function registerBillingIpc(): void {
  ipcMain.handle('billing:openCheckout', (_e, url: string) => openCheckoutWindow(String(url)))
  // Customer portal opens in the system browser (Mac parity). Guard the scheme
  // the same way the main window's window-open handler does.
  ipcMain.handle('billing:openExternal', (_e, url: string) => {
    if (isAllowedExternalScheme(String(url), ['http', 'https'])) {
      void shell.openExternal(String(url))
      return true
    }
    console.warn('[main] billing: blocked external open of non-web URL')
    return false
  })
}
