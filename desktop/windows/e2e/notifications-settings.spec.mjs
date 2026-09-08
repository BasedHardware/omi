/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// Notifications-settings E2E: drives the REAL built app (out/main/index.js) via
// Playwright's _electron and proves the opt-in end to end — the whole point of this
// PR. Windows ships notificationFrequency=0 (Off), so every proactive toast is
// permanently silent and there was NO UI to change it. This spec proves the new
// Notifications tab is that missing lever:
//
//   1. Stock: app-settings has no frequency (0 = Off) AND the Insight assistant's
//      real isEnabled() gate reads FALSE (suppressed: frequency). This is the bug —
//      a proactive assistant that can never speak.
//   2. Raise the frequency to Maximum THROUGH THE UI slider.
//   3. app-settings.json now holds notificationFrequency: 5, AND the SAME real gate
//      now reads TRUE — a proactive toast would fire. The reachability gap is closed.
//   4. Toggling "Extract memories from your screen" writes memoryEnabled: true.
//
// The downstream flip is read through the dev-only `insight:debugIsEnabled` IPC
// (registered on unpackaged builds), so this is the real gate, not a re-derivation.
//
// WARNING — this spec POPS A REAL WINDOW on your desktop, on purpose (software GL).
//
// Run after a build:
//   pnpm exec electron-vite build && node --test e2e/notifications-settings.spec.mjs
import { describe, test } from 'node:test'
import assert from 'node:assert/strict'
import { _electron as electron } from 'playwright'
import { fileURLToPath } from 'node:url'
import { mkdtempSync, rmSync, readFileSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const mainEntry = process.env.OMI_E2E_MAIN
  ? path.resolve(process.env.OMI_E2E_MAIN)
  : path.join(root, 'out', 'main', 'index.js')

// Software GL so the window is harmless on any machine (matches the gpu spec's
// healthy control).
const SWIFTSHADER_ARGS = [
  '--use-gl=angle',
  '--use-angle=swiftshader',
  '--enable-unsafe-swiftshader',
  '--disable-gpu-shader-disk-cache'
]

const SECONDARY_HASHES = ['#/bar', '#/insight-toast', '#/capture']
const isSecondary = (u) => SECONDARY_HASHES.some((h) => u.includes(h))

// OMI_E2E_FAKE_AUTH boots the real out/ bundle straight into the signed-in,
// onboarded shell (offline fake user — see lib/dev/e2eAuth.ts + App.tsx), so
// Settings is reachable without a web login or a token.
const baseEnv = {
  ...process.env,
  OMI_E2E: '1',
  OMI_E2E_FAKE_AUTH: '1',
  OMI_AUTOMATION: '0',
  OMI_SKIP_TUNNEL: '1'
}

async function blockExternalNetwork(page) {
  await page.route('**/*', (route) => {
    const url = route.request().url()
    if (/^https?:\/\/(localhost|127\.0\.0\.1)(:|\/)/.test(url)) return route.continue()
    if (/^https?:\/\//.test(url)) return route.abort()
    return route.continue()
  })
}

async function launch() {
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-notif-e2e-'))
  const app = await electron.launch({
    args: [mainEntry, `--user-data-dir=${dir}`, ...SWIFTSHADER_ARGS],
    env: baseEnv
  })
  const cleanup = async () => {
    try {
      await app.close()
    } catch {
      /* already closed */
    }
    try {
      rmSync(dir, { recursive: true, force: true })
    } catch {
      /* best-effort */
    }
  }
  return { app, cleanup, dir }
}

async function mainPage(app) {
  await app.firstWindow()
  for (let i = 0; i < 120; i++) {
    const page = (await app.windows()).find((w) => !isSecondary(w.url()))
    if (page) {
      const ready = await page
        .evaluate(() => (document.querySelector('#root')?.childElementCount ?? 0) > 0)
        .catch(() => false)
      if (ready) return page
    }
    await new Promise((r) => setTimeout(r, 100))
  }
  throw new Error('main-window shell never mounted')
}

// Read + parse <userData>/app-settings.json (absent = the app has written nothing
// yet, i.e. every value is at its default).
function readSettings(dir) {
  const p = path.join(dir, 'app-settings.json')
  if (!existsSync(p)) return {}
  try {
    return JSON.parse(readFileSync(p, 'utf8'))
  } catch {
    return {}
  }
}

// Poll until app-settings.json satisfies `pred` (the disk write is async after the
// optimistic UI update), or throw.
async function waitForSettings(dir, pred, label) {
  for (let i = 0; i < 50; i++) {
    const s = readSettings(dir)
    if (pred(s)) return s
    await new Promise((r) => setTimeout(r, 100))
  }
  throw new Error(
    `app-settings never satisfied: ${label}\nlast: ${JSON.stringify(readSettings(dir))}`
  )
}

const insightIsEnabled = (page) => page.evaluate(() => window.omi.insightDebugIsEnabled())

describe('Notifications settings — the proactive opt-in', () => {
  test('raising the frequency through the UI unblocks a proactive assistant', async (t) => {
    const { app, cleanup, dir } = await launch()
    t.after(cleanup)

    const page = await mainPage(app)
    await blockExternalNetwork(page)
    // Fake-auth boots the signed-in shell; wait for it to mount and settle off
    // /login before touching the router.
    await page.waitForFunction(
      () => (document.querySelector('#root')?.childElementCount ?? 0) > 0,
      {
        timeout: 20000
      }
    )
    await page.waitForFunction(() => !location.hash.includes('/login'), { timeout: 30000 })
    await new Promise((r) => setTimeout(r, 500))
    // Open Settings (HashRouter).
    await page.evaluate(() => {
      window.location.hash = '#/settings'
    })
    await new Promise((r) => setTimeout(r, 1500))
    console.log('[notif] url after nav:', page.url())
    // The rail tab carries the plain label; click it to activate the panel.
    const notifTab = page.getByRole('button', { name: 'Notifications' })
    await notifTab.waitFor({ state: 'visible', timeout: 20000 })
    await notifTab.click({ force: true })

    const slider = page.getByRole('slider', { name: 'Notification frequency' })
    await slider.waitFor({ state: 'visible', timeout: 10000 })

    // 1. Stock: frequency Off on disk (absent or 0) AND the real Insight gate is off.
    const stock = readSettings(dir)
    assert.ok(
      stock.notificationFrequency === undefined || stock.notificationFrequency === 0,
      `stock frequency must be Off, got ${JSON.stringify(stock.notificationFrequency)}`
    )
    const before = await insightIsEnabled(page)
    console.log('[notif] stock insightDebugIsEnabled:', JSON.stringify(before))
    assert.equal(before.isEnabled, false, 'stock: the Insight gate is suppressed (frequency Off)')

    // 2. Raise the frequency to Maximum (level 5, no throttle) via the UI slider.
    await slider.focus()
    await page.keyboard.press('End')

    // 3. The write reached disk AND the same real gate now reads enabled.
    const raised = await waitForSettings(dir, (s) => s.notificationFrequency === 5, 'frequency=5')
    assert.equal(raised.notificationFrequency, 5, 'UI slider wrote Maximum to disk')
    const after = await insightIsEnabled(page)
    console.log('[notif] raised insightDebugIsEnabled:', JSON.stringify(after))
    assert.equal(after.isEnabled, true, 'raised: a proactive toast would now fire (gate open)')

    // 4. Toggling memory extraction writes just that flag.
    await page
      .getByRole('switch', { name: 'Extract memories from your screen' })
      .click({ force: true })
    const withMemory = await waitForSettings(
      dir,
      (s) => s.memoryEnabled === true,
      'memoryEnabled=true'
    )
    assert.equal(withMemory.memoryEnabled, true, 'memory toggle persisted memoryEnabled')
    // And the frequency it unblocked stayed put (scoped write, not a clobber).
    assert.equal(
      withMemory.notificationFrequency,
      5,
      'the memory write did not disturb the frequency'
    )
  })
})
