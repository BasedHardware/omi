// Gmail "session" connector (Option B) — Electron-coupled glue (main process).
//
// Windows can't harvest the system browser's Google cookies the way macOS does
// (Chrome 127+ App-Bound Encryption makes that an infostealer technique). Instead we
// own the jar: the user signs into Google ONCE inside an Omi-owned BrowserWindow on a
// PERSISTENT session partition, and we replay the same Gmail web endpoints macOS uses
// over that session (cookies auto-attach). No restricted-scope OAuth, no DPAPI.
//
// This module holds everything that touches Electron (BrowserWindow / session / net);
// the fetch/parse cascade lives in gmailSessionReader.ts + gmailSessionParse.ts and is
// unit-tested in isolation. Never log cookies or email contents here (repo PII rules).

import { BrowserWindow, net, session, type Session } from 'electron'
import {
  readRecentEmails,
  verifyConnection,
  type GmailHttpResponse,
  type GmailReaderDeps
} from './gmailSessionReader'
import { hasGoogleAuthCookies } from './gmailSessionParse'
import { installContextMenu } from '../contextMenu'
import type { GmailSessionStatus, GmailSessionFetchResult } from '../../shared/types'

// Persistent partition: cookies survive restarts, stored in Chromium's own encrypted
// cookie store under userData — we never touch DPAPI or another app's profile.
const PARTITION = 'persist:omi-gmail'

// A genuine desktop Chrome UA. Google blocks logins from "embedded" user agents
// (disallowed_useragent), so both the login window and the feed requests present as
// desktop Chrome on Windows — this is the Option B mitigation.
const CHROME_UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'

// Start at accounts.google.com (per the connector's design) and continue to Gmail once
// signed in; when the partition already holds a session this redirects straight through.
const LOGIN_URL =
  'https://accounts.google.com/ServiceLogin?continue=' +
  encodeURIComponent('https://mail.google.com/mail/')

const LOGIN_TIMEOUT_MS = 5 * 60_000
const HTTP_TIMEOUT_MS = 30_000

function getGmailSession(): Session {
  return session.fromPartition(PARTITION)
}

/** Cookie names applicable to Gmail in our partition (used to detect a signed-in session). */
async function getAuthCookieNames(): Promise<string[]> {
  try {
    const ses = getGmailSession()
    const cookies = await ses.cookies.get({ url: 'https://mail.google.com/' })
    return cookies.map((c) => c.name)
  } catch {
    return []
  }
}

/** GET a URL over the Gmail partition session (cookies auto-attach). Never throws. */
function httpGet(url: string): Promise<GmailHttpResponse> {
  return new Promise((resolve) => {
    let settled = false
    const done = (r: GmailHttpResponse): void => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve(r)
    }
    let request: Electron.ClientRequest
    try {
      request = net.request({ method: 'GET', url, session: getGmailSession(), redirect: 'follow' })
    } catch (e) {
      resolve({ status: null, body: '', error: (e as Error).message })
      return
    }
    request.setHeader('User-Agent', CHROME_UA)
    const timer = setTimeout(() => {
      try {
        request.abort()
      } catch {
        /* already finished */
      }
      done({ status: null, body: '', error: 'timeout' })
    }, HTTP_TIMEOUT_MS)

    request.on('response', (response) => {
      const chunks: Buffer[] = []
      response.on('data', (chunk: Buffer) => chunks.push(chunk))
      response.on('end', () =>
        done({ status: response.statusCode, body: Buffer.concat(chunks).toString('utf8') })
      )
      response.on('error', (err: Error) => done({ status: null, body: '', error: err.message }))
    })
    request.on('error', (err: Error) => done({ status: null, body: '', error: err.message }))
    request.end()
  })
}

const readerDeps: GmailReaderDeps = { httpGet, getAuthCookieNames }

/**
 * Open the Google login window on the persistent partition and resolve once the
 * session is authenticated (auth cookies present) or the window is closed/times out.
 * Verifying against Gmail happens separately via the reader.
 */
export function gmailSessionConnect(): Promise<GmailSessionStatus> {
  const ses = getGmailSession()
  return new Promise((resolve) => {
    let settled = false
    // Parent it to the main window (not modal — the sign-in shouldn't block the app),
    // and mirror billing/checkoutWindow.ts: fully isolated remote content, shown only
    // once ready to avoid a white flash.
    const parent = BrowserWindow.getFocusedWindow() ?? BrowserWindow.getAllWindows()[0] ?? undefined
    const win = new BrowserWindow({
      width: 520,
      height: 700,
      parent,
      show: false,
      title: 'Connect Gmail',
      autoHideMenuBar: true,
      webPreferences: {
        session: ses,
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true
      }
    })
    win.webContents.setUserAgent(CHROME_UA)
    // Right-click → Paste, so the user can paste their email/password into Google's
    // form. Chromium-role menu only; exposes nothing of the app to the remote page.
    installContextMenu(win)

    // Timers reference `settle` and vice-versa, so collect teardown in an array to
    // keep both the interval and the timeout `const` (no forward-declared `let`).
    const cleanups: Array<() => void> = []
    const settle = (status: GmailSessionStatus): void => {
      if (settled) return
      settled = true
      cleanups.forEach((fn) => fn())
      resolve(status)
    }

    const finishConnected = async (): Promise<void> => {
      if (settled) return
      // Persist the freshly minted cookies before closing so the next launch is warm.
      try {
        await ses.cookies.flushStore()
      } catch {
        /* best-effort */
      }
      settle({ connected: true, verifiedAt: Date.now() })
      if (!win.isDestroyed()) win.close()
    }

    const check = async (): Promise<void> => {
      if (settled) return
      if (hasGoogleAuthCookies(await getAuthCookieNames())) await finishConnected()
    }

    win.webContents.on('did-navigate', () => void check())
    win.webContents.on('did-navigate-in-page', () => void check())
    win.webContents.on('did-frame-navigate', () => void check())
    win.on('closed', () => settle({ connected: false, message: 'Sign-in window was closed.' }))

    const poll = setInterval(() => void check(), 1500)
    cleanups.push(() => clearInterval(poll))
    const timer = setTimeout(() => {
      settle({ connected: false, message: 'Timed out waiting for Google sign-in.' })
      if (!win.isDestroyed()) win.close()
    }, LOGIN_TIMEOUT_MS)
    cleanups.push(() => clearTimeout(timer))

    win.once('ready-to-show', () => win.show())
    void win.loadURL(LOGIN_URL, { userAgent: CHROME_UA })
  })
}

/** Lightweight status: signed in iff the partition holds Google auth cookies. */
export async function gmailSessionStatus(): Promise<GmailSessionStatus> {
  const connected = hasGoogleAuthCookies(await getAuthCookieNames())
  return connected
    ? { connected: true }
    : { connected: false, message: 'Not connected. Click Connect to sign into Gmail.' }
}

/** Fetch recent emails over the persisted session, normalized to the macOS shape. */
export async function gmailSessionFetch(
  query?: string,
  maxResults?: number
): Promise<GmailSessionFetchResult> {
  const out = await readRecentEmails(readerDeps, { query, maxResults })
  if (out.ok) return { ok: true, emails: out.emails, source: out.source }
  return { ok: false, emails: [], error: out.error }
}

/** Verify the session actually reads Gmail right now (network probe via the reader). */
export async function gmailSessionVerify(): Promise<GmailSessionStatus> {
  return verifyConnection(readerDeps)
}

/** Disconnect: clear the partition (cookies + cached data), signing the session out. */
export async function gmailSessionDisconnect(): Promise<GmailSessionStatus> {
  try {
    const ses = getGmailSession()
    await ses.clearStorageData({
      storages: ['cookies', 'localstorage', 'indexdb', 'serviceworkers']
    })
    await ses.clearCache()
  } catch {
    /* best-effort — a partial clear still drops the auth cookies */
  }
  return { connected: false, message: 'Disconnected.' }
}
