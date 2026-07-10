// Shared driver plumbing for the orb harness: vite-build the standalone page,
// serve dist/ over loopback http (Chromium blocks ES modules on file://), and
// launch a system Chromium (chrome → msedge fallback; no Playwright browser
// download needed) pointed at it. Every consumer drives window.orb via
// page.evaluate with EXPLICIT times — deterministic frames only.
import { build } from 'vite'
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..')
const harnessRoot = path.join(root, 'orb-harness')
const dist = path.join(harnessRoot, 'dist')
export const outDir = path.join(root, '.orb-out')

const MIME = {
  '.html': 'text/html',
  '.js': 'application/javascript',
  '.css': 'text/css',
  '.map': 'application/json'
}

export async function buildHarness({ force = true } = {}) {
  // Rebuild by default — a stale dist silently checks old shader code (bit us
  // once). Set ORB_HARNESS_CACHE=1 to reuse an existing build.
  if ((!force || process.env.ORB_HARNESS_CACHE === '1') && existsSync(path.join(dist, 'index.html')))
    return
  await build({
    configFile: false,
    root: harnessRoot,
    base: './',
    logLevel: 'warn',
    build: { outDir: dist, emptyOutDir: true }
  })
}

export function serveDist() {
  const server = createServer(async (req, res) => {
    try {
      const url = new URL(req.url, 'http://localhost')
      let p = url.pathname === '/' ? '/index.html' : url.pathname
      const file = path.join(dist, path.normalize(p).replace(/^([/\\])+/, ''))
      if (!file.startsWith(dist)) throw new Error('forbidden')
      const body = await readFile(file)
      res.writeHead(200, { 'content-type': MIME[path.extname(file)] ?? 'application/octet-stream' })
      res.end(body)
    } catch {
      res.writeHead(404)
      res.end('not found')
    }
  })
  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => {
      resolve({ server, url: `http://127.0.0.1:${server.address().port}` })
    })
  })
}

export async function launchBrowser() {
  const errors = []
  for (const channel of ['chrome', 'msedge']) {
    try {
      return await chromium.launch({
        channel,
        headless: true,
        // Software WebGL is fine (and deterministic) for a 96px canvas.
        args: ['--enable-unsafe-swiftshader']
      })
    } catch (e) {
      errors.push(`${channel}: ${e.message?.split('\n')[0]}`)
    }
  }
  throw new Error(`no system Chromium found (${errors.join('; ')})`)
}

/** One-call setup: build, serve, launch, open the harness page. */
export async function openHarness(query = '') {
  await buildHarness()
  const { server, url } = await serveDist()
  const browser = await launchBrowser()
  const page = await browser.newPage({ viewport: { width: 480, height: 480 } })
  page.on('pageerror', (e) => console.error('[harness pageerror]', e.message))
  await page.goto(`${url}/index.html${query}`)
  await page.waitForFunction(() => !!window.orb)
  const close = async () => {
    await browser.close()
    server.close()
  }
  return { page, browser, server, close }
}

/** Render one deterministic frame and return { width, height, data:Uint8Array }. */
export async function renderPixels(page, spec) {
  const res = await page.evaluate((s) => {
    window.orb.renderAt(s)
    return window.orb.pixels()
  }, spec)
  return { width: res.width, height: res.height, data: Buffer.from(res.data, 'base64') }
}
