// Manual smoke for the Gmail "session" connector (Option B).
//
// Launches the REAL built app (out/main/index.js) via Playwright's _electron and
// exercises the real IPC: window.omi.gmailSessionConnect() opens the Omi-owned login
// BrowserWindow on the persist:omi-gmail partition. We read the login window's URL,
// title, and a snippet of its text straight from the main process, screenshot it, and
// assert it reached accounts.google.com — proving the window/partition wiring WITHOUT
// completing (or needing) a Google login. Requires network to reach Google.
//
// Two modes:
//   node scripts/gmail-session-smoke.mjs           (default) open → assert URL → shot → close
//   node scripts/gmail-session-smoke.mjs --login    open and WAIT up to 5 min for you to
//                                                    sign in, then fetch recent mail and
//                                                    print the count (Chris's one-time smoke)
//
// Build first if needed: `npx electron-vite build`.
import { _electron as electron } from 'playwright'
import { fileURLToPath } from 'node:url'
import { mkdtempSync, mkdirSync, writeFileSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const mainEntry = path.join(root, 'out', 'main', 'index.js')
const shotsDir = path.join(root, '.playwright-mcp', 'gmail-session')
const LOGIN_MODE = process.argv.includes('--login')

if (!existsSync(mainEntry)) {
  console.error(`[gmail-smoke] ${mainEntry} missing — run: npx electron-vite build`)
  process.exit(1)
}

const baseEnv = {
  ...process.env,
  OMI_E2E: '1',
  OMI_E2E_FAKE_AUTH: '1',
  OMI_AUTOMATION: '0',
  OMI_SKIP_TUNNEL: '1'
}

const SECONDARY = ['#/bar', '#/insight', '#/notch', '#/capture', '#/glow']
const isSecondary = (url) => SECONDARY.some((h) => url.includes(h))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// Read every BrowserWindow's URL from the MAIN process (robust for the sandboxed
// Google window, which Playwright may not attach a page to).
const windowUrls = (app) =>
  app.evaluate(({ BrowserWindow }) =>
    BrowserWindow.getAllWindows().map((w) => {
      try {
        return w.webContents.getURL()
      } catch {
        return ''
      }
    })
  )

const googleWindowInfo = (app) =>
  app.evaluate(async ({ BrowserWindow }) => {
    const w = BrowserWindow.getAllWindows().find((win) =>
      (win.webContents.getURL() || '').includes('google.com')
    )
    if (!w) return null
    const url = w.webContents.getURL()
    const title = w.getTitle()
    const bodyText = await w.webContents
      .executeJavaScript('document.body ? document.body.innerText.slice(0, 800) : ""')
      .catch(() => '')
    const png = await w.webContents
      .capturePage()
      .then((img) => img.toDataURL())
      .catch(() => null)
    return { url, title, bodyText, png }
  })

async function mainPage(app) {
  for (let i = 0; i < 150; i++) {
    const page = (await app.windows()).find((w) => !isSecondary(w.url()))
    if (page) {
      // Evaluate the readiness predicate INSIDE the page — a function reference can't
      // cross Playwright's serialization boundary, so return a boolean, not the fn.
      const ready = await page
        .evaluate(
          () =>
            (document.querySelector('#root')?.childElementCount ?? 0) > 0 &&
            typeof window.omi?.gmailSessionConnect === 'function'
        )
        .catch(() => false)
      if (ready) return page
    }
    await sleep(100)
  }
  throw new Error('main window / window.omi.gmailSessionConnect never became ready')
}

async function main() {
  mkdirSync(shotsDir, { recursive: true })
  const userDataDir = mkdtempSync(path.join(tmpdir(), 'omi-gmail-smoke-'))
  const app = await electron.launch({
    args: [mainEntry, `--user-data-dir=${userDataDir}`],
    env: baseEnv
  })

  let pass = false
  try {
    const page = await mainPage(app)
    console.log('[gmail-smoke] main window ready; triggering gmailSessionConnect()')

    // Fire the connect flow (opens the login window). Do NOT await — it resolves only
    // on login / window-close / timeout. Stash the promise so --login can read it.
    await page.evaluate(() => {
      window.__gmailConnect = window.omi.gmailSessionConnect()
    })

    // Poll for the login window to reach accounts.google.com.
    let info = null
    for (let i = 0; i < 90; i++) {
      const urls = await windowUrls(app)
      if (urls.some((u) => u.includes('google.com'))) {
        info = await googleWindowInfo(app)
        if (info && info.url) break
      }
      await sleep(500)
    }

    if (!info) {
      console.error('[gmail-smoke] FAIL — no google.com login window appeared within ~45s')
      console.error('[gmail-smoke] open window URLs:', await windowUrls(app))
    } else {
      console.log('[gmail-smoke] login window URL  :', info.url)
      console.log('[gmail-smoke] login window title:', info.title)
      const reachedGoogle = /(^https:\/\/accounts\.google\.com)|(\.google\.com)/.test(info.url)
      const blocked =
        /couldn't sign you in|this browser or app may not be secure|disallowed_useragent/i.test(
          `${info.title}\n${info.bodyText}`
        )
      if (info.png) {
        const file = path.join(shotsDir, 'login-window.png')
        writeFileSync(file, Buffer.from(info.png.split(',')[1], 'base64'))
        console.log('[gmail-smoke] screenshot:', file)
      }
      if (blocked) {
        console.error('[gmail-smoke] WARNING — Google served an embedded-UA block page:')
        console.error(info.bodyText.slice(0, 300))
      } else {
        console.log('[gmail-smoke] no embedded-UA block detected on the sign-in page')
      }
      pass = reachedGoogle && !blocked
    }

    if (LOGIN_MODE && info) {
      console.log('\n[gmail-smoke] --login: sign into Google in the window. Waiting up to 5 min…')
      const connected = await page
        .evaluate(() => window.__gmailConnect)
        .catch(() => ({ connected: false, message: 'connect promise rejected' }))
      console.log('[gmail-smoke] connect resolved:', JSON.stringify(connected))
      if (connected && connected.connected) {
        const res = await page.evaluate(() => window.omi.gmailSessionFetch('newer_than:7d', 25))
        console.log(
          '[gmail-smoke] fetch result:',
          JSON.stringify({
            ok: res.ok,
            count: res.emails?.length,
            source: res.source,
            error: res.error
          })
        )
        pass = res.ok
      } else {
        pass = false
      }
    } else if (info) {
      // Default mode: close the login window without signing in (resolves connect to
      // not-connected) to prove teardown, then finish.
      await app.evaluate(({ BrowserWindow }) => {
        const w = BrowserWindow.getAllWindows().find((win) =>
          (win.webContents.getURL() || '').includes('google.com')
        )
        if (w && !w.isDestroyed()) w.close()
      })
      const resolved = await page.evaluate(() => window.__gmailConnect).catch(() => null)
      console.log('[gmail-smoke] connect resolved after close:', JSON.stringify(resolved))
    }
  } finally {
    // app.close() can hang on Windows after a child BrowserWindow existed; don't let
    // teardown mask a completed verification — race it against a short timeout.
    await Promise.race([app.close().catch(() => {}), sleep(8000)])
  }

  console.log(`\n[gmail-smoke] ${pass ? 'PASS' : 'FAIL'}`)
  process.exit(pass ? 0 : 1)
}

main().catch((e) => {
  console.error('[gmail-smoke] error:', e)
  process.exit(1)
})
