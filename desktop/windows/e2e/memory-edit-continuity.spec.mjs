/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS Electron test harness */
// Built Electron main/preload/renderer; synthetic auth and a same-origin loopback HTTP fixture.
// Build with VITE_OMI_API_BASE=http://127.0.0.1:49601 pnpm build, then run this file with node --test
import { test } from 'node:test'
import { createServer } from 'node:http'
import assert from 'node:assert/strict'
import { _electron as electron } from 'playwright'
import { mkdtempSync, rmSync, readFileSync } from 'node:fs'
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
  await app
    .context()
    .route('**/*', (route) =>
      /^https?:/.test(route.request().url()) &&
      !/^https?:\/\/(localhost|127\.0\.0\.1)(:|\/)/.test(route.request().url())
        ? route.abort()
        : route.continue()
    )
  for (let i = 0; i < 120; i++) {
    const page = (await app.windows()).find(
      (w) => /\/index\.html(?:[?#]|$)/.test(w.url()) && !secondary.some((h) => w.url().includes(h))
    )
    if (
      page &&
      (await page
        .evaluate(() => !!document.querySelector('#root')?.childElementCount)
        .catch(() => false))
    ) {
      await page.route('**/*', (route) => {
        if (
          /^https?:/.test(route.request().url()) &&
          !/^https?:\/\/(localhost|127\.0\.0\.1)(:|\/)/.test(route.request().url())
        )
          return route.abort()
        return route.continue()
      })
      return { app, page }
    }
    await new Promise((r) => setTimeout(r, 100))
  }
  const windows = await Promise.all(
    (await app.windows()).map(async (page) => ({
      url: page.url(),
      body: await page
        .locator('body')
        .innerText()
        .catch(() => '')
    }))
  )
  await app.close()
  throw new Error(`The isolated Electron shell did not mount: ${JSON.stringify(windows)}`)
}
test('failed correction retains its draft; retry selects and persists only the canonical replacement', async (t) => {
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-memory-edit-continuity-'))
  let currentApp
  t.after(async () => {
    if (currentApp) await currentApp.close().catch(() => {})
    rmSync(dir, { recursive: true, force: true })
  })
  let attempts = 0
  let serverRows = [original]
  let offline = false
  const server = createServer((request, response) => {
    const url = new URL(request.url, 'http://127.0.0.1:49601')
    const headers = {
      'content-type': 'application/json',
      'access-control-allow-origin': '*',
      'access-control-allow-methods': 'GET,PATCH,OPTIONS',
      'access-control-allow-headers': request.headers['access-control-request-headers'] || '*'
    }
    if (url.pathname.startsWith('/v3/') && offline) {
      request.destroy()
      return
    }
    if (request.method === 'OPTIONS') {
      response.writeHead(204, headers).end()
      return
    }
    if (request.method === 'PATCH' && url.pathname === `/v3/memories/${original.id}`) {
      attempts++
      assert.equal(url.searchParams.get('value'), replacement.content)
      if (attempts === 1) {
        response.writeHead(400, headers).end(JSON.stringify({ detail: 'Synthetic save refusal' }))
        return
      }
      serverRows = [replacement]
      response.writeHead(200, headers).end(JSON.stringify({ status: 'ok', memory: replacement }))
      return
    }
    if (url.pathname === '/v3/memories') {
      response
        .writeHead(200, headers)
        .end(JSON.stringify(Number(url.searchParams.get('offset') || 0) ? [] : serverRows))
      return
    }
    const assets = path.resolve(root, 'out/renderer')
    const file = path.resolve(assets, '.' + url.pathname)
    if (file.startsWith(assets + path.sep)) {
      try {
        const types = {
          '.html': 'text/html',
          '.js': 'text/javascript',
          '.css': 'text/css',
          '.woff2': 'font/woff2',
          '.svg': 'image/svg+xml',
          '.png': 'image/png'
        }
        const bytes = readFileSync(file)
        response
          .writeHead(200, {
            'content-type': types[path.extname(file)] || 'application/octet-stream'
          })
          .end(bytes)
        return
      } catch {
        /* unknown fixture asset */
      }
    }
    response.writeHead(404, headers).end('{}')
  })
  t.after(() => new Promise((resolve) => server.close(resolve)))
  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(49601, '127.0.0.1', resolve)
  })
  let { app, page } = await launch(dir)
  currentApp = app
  // Serve unchanged built assets and the API on one origin; the production CSP
  // and webSecurity remain enabled. No test-only product bypass is introduced.
  await page.goto('http://127.0.0.1:49601/index.html')
  await page.waitForFunction(() => !!document.querySelector('#root')?.childElementCount)
  await page.evaluate((value) => localStorage.setItem('omi.lastSignedInUid', value), uid)
  await page.evaluate(() => {
    location.hash = '#/memories'
  })
  await page.getByText(original.content, { exact: true }).first().click({ timeout: 20000 })
  const dialog = page.getByRole('dialog')
  await dialog.getByTitle('Click to edit').click()
  await dialog.getByRole('textbox').fill(replacement.content)
  const refusedResponse = page.waitForResponse(
    (response) => response.request().method() === 'PATCH'
  )
  await dialog.getByRole('button', { name: 'Save', exact: true }).click()
  assert.equal((await refusedResponse).status(), 400)
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
  offline = true
  ;({ app, page } = await launch(dir))
  currentApp = app
  await page.goto('http://127.0.0.1:49601/index.html')
  await page.waitForFunction(() => !!document.querySelector('#root')?.childElementCount)
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
