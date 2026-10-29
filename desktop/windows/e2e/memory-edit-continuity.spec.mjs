/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS Electron test harness */
// Built Electron main/preload/renderer; synthetic auth and intercepted HTTP only.
// Run after electron-vite build: node --test e2e/memory-edit-continuity.spec.mjs
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { _electron as electron } from 'playwright'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const uid = 'memory-edit-continuity-qa'
const snapshotKey = `omi.cache.memories.${uid}`
const original = {
  id: 'continuity-original',
  uid,
  content: 'CONTINUITY original memory',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z'
}
const replacement = {
  ...original,
  id: 'continuity-canonical',
  content: 'CONTINUITY retained correction'
}
const env = {
  ...process.env,
  OMI_E2E: '1',
  OMI_E2E_FAKE_AUTH: '1',
  OMI_AUTOMATION: '0',
  OMI_SKIP_TUNNEL: '1'
}
const secondary = ['#/bar', '#/insight', '#/notch', '#/capture', '#/glow']
async function launch(dir) {
  const app = await electron.launch({
    args: [path.join(root, 'out/main/index.js'), `--user-data-dir=${dir}`],
    env
  })
  for (let i = 0; i < 120; i++) {
    const page = (await app.windows()).find((w) => !secondary.some((h) => w.url().includes(h)))
    if (
      page &&
      (await page
        .evaluate(() => !!document.querySelector('#root')?.childElementCount)
        .catch(() => false))
    ) {
      await page.route('**/*', (route) => {
        if (/^https?:/.test(route.request().url())) return route.abort()
        return route.continue()
      })
      return { app, page }
    }
    await new Promise((r) => setTimeout(r, 100))
  }
  const windows = await Promise.all((await app.windows()).map(async (page) => ({
    url: page.url(), body: await page.locator('body').innerText().catch(() => '')
  })))
  await app.close()
  throw new Error(`The isolated Electron shell did not mount: ${JSON.stringify(windows)}`)
}
const json = (route, status, body) =>
  route.fulfill({
    status,
    contentType: 'application/json',
    headers: { 'access-control-allow-origin': '*' },
    body: JSON.stringify(body)
  })

test('failed correction retains its draft; retry selects and persists only the canonical replacement', async (t) => {
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-memory-edit-continuity-'))
  let currentApp
  t.after(async () => {
    if (currentApp) await currentApp.close().catch(() => {})
    rmSync(dir, { recursive: true, force: true })
  })
  let { app, page } = await launch(dir)
  currentApp = app
  await page.evaluate((value) => localStorage.setItem('omi.lastSignedInUid', value), uid)
  let attempts = 0
  await page.route('**/v3/memories**', async (route) => {
    const request = route.request()
    if (request.method() === 'PATCH') {
      attempts++
      assert.equal(new URL(request.url()).searchParams.get('value'), replacement.content)
      return attempts === 1
        ? json(route, 400, { detail: 'Synthetic save refusal' })
        : json(route, 200, { status: 'ok', memory: replacement })
    }
    const offset = Number(new URL(request.url()).searchParams.get('offset') || 0)
    return json(route, 200, offset ? [] : [original])
  })
  await page.evaluate(() => {
    location.hash = '#/memories'
  })
  await page.getByText(original.content, { exact: true }).first().click({ timeout: 20000 })
  const dialog = page.getByRole('dialog')
  await dialog.getByTitle('Click to edit').click()
  await dialog.getByRole('textbox').fill(replacement.content)
  await dialog.getByRole('button', { name: 'Save', exact: true }).click()
  await page.getByText('Could not update memory', { exact: true }).waitFor()
  assert.equal(await dialog.getByRole('textbox').inputValue(), replacement.content)
  await dialog.getByRole('button', { name: 'Save', exact: true }).click()
  await dialog.getByText(replacement.content, { exact: true }).waitFor()
  assert.equal(attempts, 2)
  let rows = JSON.parse(await page.evaluate((key) => localStorage.getItem(key), snapshotKey))
  assert.deepEqual(
    rows.map((row) => row.id),
    [replacement.id]
  )
  await app.close()
  currentApp = undefined
  ;({ app, page } = await launch(dir))
  currentApp = app
  await page.evaluate(() => {
    location.hash = '#/memories'
  })
  await page.getByText(replacement.content, { exact: true }).first().waitFor({ timeout: 20000 })
  rows = JSON.parse(await page.evaluate((key) => localStorage.getItem(key), snapshotKey))
  assert.deepEqual(
    rows.map((row) => row.id),
    [replacement.id]
  )
  assert.equal(await page.getByText(original.content, { exact: true }).count(), 0)
})
