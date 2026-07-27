#!/usr/bin/env node
/**
 * End-to-end verification of the omi G2 app against the EvenHub simulator.
 *
 * Hermetic: it starts its own mock bridge (`scripts/mock-bridge.mjs`) and the
 * simulator, so it needs no backend, credentials, or network. The only external
 * requirement is the Vite dev server, plus a GUI — the simulator opens a window,
 * which is why this is a local check and is deliberately not wired into CI.
 *
 * Asserts:
 *   1. simulator automation API comes up
 *   2. the SDK bridge connects and the start-up page is created
 *   3. the app's WebSocket bridge connects
 *   4. the home list renders — framebuffer non-blank at 576x288
 *   5. scroll moves the home selection
 *   6. tap opens a view and its data loads
 *   7. double-tap returns home
 *   8. a chat answer streams in and repaints the body in place, not by rebuild
 *   9. paging works inside a multi-page answer
 *  10. a server push renders as a banner
 *  11. every menu row opens: Memories, Action items, Today, Capture
 *  12. losing the bridge shows up as offline and starts a retry
 *  13. the app never reloaded mid-run, and nothing threw
 *
 * Usage: npm run dev   (separate terminal)
 *        npm run verify
 *        npm run verify -- --dump    # print every console line at the end
 */
import { spawn } from 'node:child_process'
import { createHash } from 'node:crypto'
import { createConnection } from 'node:net'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { inflateSync } from 'node:zlib'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const HERE = dirname(fileURLToPath(import.meta.url))

const DEV_URL = process.env.DEV_URL ?? 'http://localhost:5273'
const AUTOMATION_PORT = Number(process.env.AUTOMATION_PORT ?? 9899)
const BRIDGE_PORT = Number(process.env.BRIDGE_PORT ?? 18765)
const API = `http://127.0.0.1:${AUTOMATION_PORT}`
const BRIDGE_HTTP = `http://127.0.0.1:${BRIDGE_PORT}`
// The app reads its bridge endpoint from `?bridge=`, so the test drives a
// throwaway port instead of whatever the developer has running on the default.
const APP_URL = `${DEV_URL}/?bridge=ws://127.0.0.1:${BRIDGE_PORT}/app`

const DUMP = process.argv.includes('--dump')

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

let failures = 0
const pass = (msg) => console.log(`  PASS  ${msg}`)
const fail = (msg) => {
  failures++
  console.log(`  FAIL  ${msg}`)
}

// ---------------------------------------------------------------- PNG decode

/**
 * Minimal non-interlaced 8-bit RGBA PNG decoder — enough to count lit pixels
 * in the simulator framebuffer without pulling in an image library.
 * Returns { width, height, data } where data is unfiltered RGBA bytes.
 */
function decodePng(buf) {
  const sig = [137, 80, 78, 71, 13, 10, 26, 10]
  for (let i = 0; i < 8; i++) {
    if (buf[i] !== sig[i]) throw new Error('not a PNG')
  }

  let pos = 8
  let width = 0
  let height = 0
  let bitDepth = 0
  let colorType = 0
  let interlace = 0
  const idat = []

  while (pos < buf.length) {
    const len = buf.readUInt32BE(pos)
    const type = buf.toString('ascii', pos + 4, pos + 8)
    const data = buf.subarray(pos + 8, pos + 8 + len)
    pos += 12 + len // length + type + data + crc

    if (type === 'IHDR') {
      width = data.readUInt32BE(0)
      height = data.readUInt32BE(4)
      bitDepth = data[8]
      colorType = data[9]
      interlace = data[12]
    } else if (type === 'IDAT') {
      idat.push(data)
    } else if (type === 'IEND') {
      break
    }
  }

  if (bitDepth !== 8) throw new Error(`unsupported bit depth ${bitDepth}`)
  if (colorType !== 6) throw new Error(`expected RGBA (colorType 6), got ${colorType}`)
  if (interlace !== 0) throw new Error('interlaced PNG not supported')

  const raw = inflateSync(Buffer.concat(idat))
  const bpp = 4
  const stride = width * bpp
  const out = Buffer.alloc(height * stride)

  const paeth = (a, b, c) => {
    const p = a + b - c
    const pa = Math.abs(p - a)
    const pb = Math.abs(p - b)
    const pc = Math.abs(p - c)
    if (pa <= pb && pa <= pc) return a
    return pb <= pc ? b : c
  }

  let rp = 0
  for (let y = 0; y < height; y++) {
    const filter = raw[rp++]
    const row = y * stride
    const prev = row - stride

    for (let x = 0; x < stride; x++) {
      const f = raw[rp + x]
      const a = x >= bpp ? out[row + x - bpp] : 0
      const b = y > 0 ? out[prev + x] : 0
      const c = x >= bpp && y > 0 ? out[prev + x - bpp] : 0

      let val
      switch (filter) {
        case 0: val = f; break
        case 1: val = f + a; break
        case 2: val = f + b; break
        case 3: val = f + ((a + b) >> 1); break
        case 4: val = f + paeth(a, b, c); break
        default: throw new Error(`bad filter type ${filter} on row ${y}`)
      }
      out[row + x] = val & 0xff
    }
    rp += stride
  }

  return { width, height, data: out }
}

// ------------------------------------------------------------------ API glue

async function ping() {
  try {
    const r = await fetch(`${API}/api/ping`)
    return r.ok
  } catch {
    return false
  }
}

async function console_(sinceId) {
  const url = sinceId === undefined ? `${API}/api/console` : `${API}/api/console?since_id=${sinceId}`
  const r = await fetch(url)
  if (!r.ok) throw new Error(`console ${r.status}`)
  return (await r.json()).entries ?? []
}

async function input(action) {
  const r = await fetch(`${API}/api/input`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action }),
  })
  if (!r.ok) throw new Error(`input ${action} -> ${r.status}`)
}

/**
 * Grab the glasses framebuffer. `lit` proves something is drawn at all; `hash`
 * proves the drawing *changed* — the list highlight moves without changing the
 * lit-pixel count, so a count alone cannot see a selection move.
 */
async function framebuffer() {
  const r = await fetch(`${API}/api/screenshot/glasses`)
  if (!r.ok) throw new Error(`screenshot ${r.status}`)
  const png = decodePng(Buffer.from(await r.arrayBuffer()))
  let lit = 0
  // Background is alpha=0, lit text is alpha=255. Never convert to RGB — both
  // are pure green and become indistinguishable.
  for (let i = 3; i < png.data.length; i += 4) {
    if (png.data[i] > 0) lit++
  }
  const hash = createHash('sha1').update(png.data).digest('hex').slice(0, 12)
  return { lit, hash, width: png.width, height: png.height }
}

/** True when something already holds `port` — a leftover process would answer
 *  every request and silently produce a green run against a stale instance. */
function portInUse(port) {
  return new Promise((resolve) => {
    const socket = createConnection({ port, host: '127.0.0.1' })
    socket.once('connect', () => {
      socket.destroy()
      resolve(true)
    })
    socket.once('error', () => resolve(false))
    setTimeout(() => {
      socket.destroy()
      resolve(false)
    }, 1_000)
  })
}

/** All console text seen so far, accumulated across polls. */
const seen = []
let lastId = -1
async function drainConsole() {
  const entries = lastId < 0 ? await console_() : await console_(lastId)
  for (const e of entries) {
    seen.push(e)
    if (e.id > lastId) lastId = e.id
  }
  return entries
}

const sawMessage = (needle) => seen.some((e) => (e.message ?? '').includes(needle))
const countMessage = (needle) => seen.filter((e) => (e.message ?? '').includes(needle)).length

async function waitForMessage(needle, timeoutMs, label) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    await drainConsole()
    if (sawMessage(needle)) {
      pass(label)
      return true
    }
    await sleep(250)
  }
  fail(`${label} — never saw "${needle}" within ${timeoutMs}ms`)
  return false
}

/** Like `waitForMessage`, but only counts lines logged after this point, so a
 *  repeated message (e.g. returning to a view a second time) is unambiguous.
 *  Drains first, or already-emitted lines still sitting on the simulator would
 *  land after the mark and satisfy the next wait for free. */
async function mark() {
  await drainConsole()
  return seen.length
}
async function waitForMessageSince(since, needle, timeoutMs, label) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    await drainConsole()
    if (seen.slice(since).some((e) => (e.message ?? '').includes(needle))) {
      pass(label)
      return true
    }
    await sleep(250)
  }
  fail(`${label} — never saw "${needle}" within ${timeoutMs}ms`)
  return false
}

/** Scroll to `row` from the top of the menu and tap it. Only valid from a
 *  freshly rebuilt home page, where the highlight starts on row 0. */
async function openRow(row, label) {
  const since = await mark()
  for (let i = 0; i < row; i++) {
    await input('down')
    await sleep(250)
  }
  await input('click')
  await sleep(400)
  await waitForMessageSince(since, `[app] home index=${row} (${label})`, 8_000, `row ${row} is "${label}"`)
  return since
}

// --------------------------------------------------------------------- main

async function main() {
  console.log(`\nomi G2 simulator verification`)
  console.log(`  app URL:        ${APP_URL}`)
  console.log(`  automation API: ${API}`)
  console.log(`  mock bridge:    ws://127.0.0.1:${BRIDGE_PORT}/app\n`)

  // Fail fast with a clear message rather than a confusing simulator error.
  try {
    const r = await fetch(DEV_URL)
    if (!r.ok) throw new Error(`status ${r.status}`)
  } catch (e) {
    console.error(`Dev server not reachable at ${DEV_URL} (${e.message}).`)
    console.error(`Start it first:  npm run dev`)
    process.exit(2)
  }

  if (await ping()) {
    console.error(`Something is already serving the automation API on ${API}.`)
    console.error(`That is almost certainly a leftover simulator. Kill it first:`)
    console.error(`  pkill -f evenhub-simulator`)
    process.exit(2)
  }
  if (await portInUse(AUTOMATION_PORT)) {
    console.error(`Port ${AUTOMATION_PORT} is already in use by something that is not the simulator.`)
    console.error(`Free it, or re-run with AUTOMATION_PORT=<other>.`)
    process.exit(2)
  }
  if (await portInUse(BRIDGE_PORT)) {
    console.error(`Port ${BRIDGE_PORT} is already in use — a stale mock bridge would serve`)
    console.error(`fixtures this run never wrote. Free it, or re-run with BRIDGE_PORT=<other>.`)
    process.exit(2)
  }

  const children = []
  let cleanedUp = false
  const cleanup = () => {
    if (cleanedUp) return
    cleanedUp = true
    for (const child of children) {
      try {
        // Negative pid = the whole process group. The simulator launcher execs
        // a platform binary; killing only the Node launcher leaves the
        // simulator running and holding the port.
        process.kill(-child.pid, 'SIGTERM')
      } catch {
        /* already gone */
      }
    }
  }
  process.on('exit', cleanup)
  process.on('SIGINT', () => {
    cleanup()
    process.exit(130)
  })

  // ---- mock bridge
  const bridgeProc = spawn(process.execPath, [join(HERE, 'mock-bridge.mjs'), '--port', String(BRIDGE_PORT)], {
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: true,
  })
  children.push(bridgeProc)
  let bridgeLog = ''
  bridgeProc.stdout.on('data', (d) => (bridgeLog += d.toString()))
  bridgeProc.stderr.on('data', (d) => (bridgeLog += d.toString()))

  {
    const deadline = Date.now() + 10_000
    let up = false
    while (Date.now() < deadline) {
      try {
        const r = await fetch(`${BRIDGE_HTTP}/control/health`)
        if (r.ok) {
          up = true
          break
        }
      } catch {
        /* not listening yet */
      }
      await sleep(200)
    }
    if (!up) {
      console.error(`Mock bridge never came up on ${BRIDGE_HTTP}.\n${bridgeLog}`)
      cleanup()
      process.exit(2)
    }
    pass('mock bridge is up')
  }

  // ---- simulator
  const launcher = require.resolve('@evenrealities/evenhub-simulator/bin/index.js')
  const sim = spawn(process.execPath, [launcher, APP_URL, '--automation-port', String(AUTOMATION_PORT)], {
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: true,
  })
  children.push(sim)
  let simErr = ''
  sim.stderr.on('data', (d) => (simErr += d.toString()))
  sim.on('exit', (code) => {
    if (code !== 0 && code !== null) {
      console.error(`\nSimulator exited early (code ${code}):\n${simErr}`)
    }
  })

  try {
    // 1. Simulator up
    const deadline = Date.now() + 30_000
    let up = false
    while (Date.now() < deadline) {
      if (await ping()) {
        up = true
        break
      }
      await sleep(500)
    }
    if (!up) {
      console.error(`Simulator automation API never came up on ${API}.\n${simErr}`)
      process.exit(2)
    }
    pass('simulator automation API is up')

    // 2. App booted. Poll before clearing — startup logs are emitted once and
    //    would be lost.
    await waitForMessage('[app] bridge ready', 20_000, 'SDK bridge connected')
    await waitForMessage('[app] page ready', 20_000, 'start-up page container created')
    await waitForMessage('[bridge] online', 20_000, 'app connected to the omi bridge')

    // The simulator's WebView sometimes reloads itself once shortly after
    // start-up, which resets the app to its initial view. Let that settle
    // before touching anything, or every later assertion is measuring a
    // half-restarted app.
    let boots = countMessage('[app] bridge ready')
    for (let attempt = 0; attempt < 3; attempt++) {
      await sleep(2_500)
      await drainConsole()
      const now = countMessage('[app] bridge ready')
      if (now === boots) break
      console.log(`  note  simulator reloaded the app (boot ${now}); waiting for it to settle`)
      boots = now
    }
    const bootsAtStart = countMessage('[app] bridge ready')
    if (countMessage('[app] ready') === bootsAtStart) {
      pass(`app finished start-up and is stable (boot ${bootsAtStart})`)
    } else {
      fail(`app is mid-restart: ${bootsAtStart} boot(s) but ${countMessage('[app] ready')} completed`)
    }

    // 3. The home list is actually on the display
    const home = await framebuffer()
    if (home.width !== 576 || home.height !== 288) {
      fail(`framebuffer is ${home.width}x${home.height}, expected 576x288`)
    } else {
      pass(`framebuffer is ${home.width}x${home.height}`)
    }
    if (home.lit > 200) {
      pass(`home list renders (${home.lit} lit pixels)`)
    } else {
      fail(`home list looks blank (only ${home.lit} lit pixels)`)
    }

    // 4. Scroll moves the selection. The OS list owns its highlight and emits
    //    no event while scrolling — it only reports the row on the click that
    //    follows — so the move is asserted on the framebuffer, and the row it
    //    landed on is asserted from the click below.
    await input('down')
    await sleep(500)
    const afterScroll = await framebuffer()
    if (afterScroll.hash !== home.hash) {
      pass(`scroll down moves the home highlight (${home.hash} -> ${afterScroll.hash})`)
    } else {
      fail(`scroll down left the display byte-identical (${home.hash}) — the highlight did not move`)
    }

    // 5. Tap opens the view it moved to, and its data loads
    await input('click')
    await sleep(400)
    await waitForMessage('[app] home index=1 (Memories)', 8_000, 'the tapped row is "Memories" (row 1)')
    await waitForMessage('[app] view=memories', 8_000, 'tap opens the Memories view')
    await waitForMessage('[app] memories loaded', 8_000, 'memories arrive from the bridge')
    const memories = await framebuffer()
    if (memories.lit > 200) {
      pass(`memories view renders (${memories.lit} lit pixels)`)
    } else {
      fail(`memories view looks blank (${memories.lit} lit pixels)`)
    }
    if (memories.hash !== afterScroll.hash) {
      pass('display changed between home and memories')
    } else {
      fail(`display is byte-identical to home (${memories.hash}) — the view never redrew`)
    }

    // 6. Double-tap returns
    let since = await mark()
    await input('double_click')
    await sleep(600)
    await waitForMessageSince(since, '[app] view=home', 8_000, 'double-tap returns to home')
    const backHome = await framebuffer()
    if (backHome.hash === home.hash) {
      pass('home is restored with the highlight back on row 0')
    } else {
      fail(`home came back different from how it started (${home.hash} -> ${backHome.hash})`)
    }

    // 7. Chat: tap row 0 and watch the answer stream in
    since = await mark()
    const layoutsBefore = seen.filter((e) => (e.message ?? '').includes('[app] layout=detail')).length
    await input('click')
    await sleep(400)
    await waitForMessageSince(since, '[app] home index=0 (Ask Omi)', 8_000, 'the tapped row is "Ask Omi" (row 0)')
    await waitForMessageSince(since, '[app] view=chat', 8_000, 'tap opens the chat view')
    await waitForMessageSince(since, '[app] chat delta', 10_000, 'chat answer streams in')
    await waitForMessageSince(since, '[app] rendered chat body', 10_000, 'streaming repaints the chat body')
    await waitForMessageSince(since, '[app] chat done', 20_000, 'chat stream completes')

    const chat = await framebuffer()
    if (chat.lit > 200) {
      pass(`chat view renders the answer (${chat.lit} lit pixels)`)
    } else {
      fail(`chat view looks blank (${chat.lit} lit pixels)`)
    }

    // The streaming repaints must be in-place `textContainerUpgrade` calls, not
    // page rebuilds: exactly one rebuild for entering the view, and no more.
    const layoutsAfter = seen.filter((e) => (e.message ?? '').includes('[app] layout=detail')).length
    const repaints = seen.slice(since).filter((e) => (e.message ?? '').includes('[app] rendered chat body')).length
    if (layoutsAfter - layoutsBefore === 1 && repaints > 1) {
      pass(`answer streamed with ${repaints} in-place updates and 1 page rebuild`)
    } else {
      fail(`expected 1 rebuild and >1 in-place update, got ${layoutsAfter - layoutsBefore} and ${repaints}`)
    }

    // 8. The answer is longer than one page, so scrolling must page it
    const pageLine = seen
      .map((e) => e.message ?? '')
      .reverse()
      .find((m) => m.includes('[app] chat done ('))
    const pageCount = Number(/(\d+) page\(s\)/.exec(pageLine ?? '')?.[1] ?? 0)
    if (pageCount > 1) {
      pass(`answer paginated into ${pageCount} pages`)
      since = await mark()
      await input('up')
      await sleep(600)
      await waitForMessageSince(since, '[app] page=1/', 5_000, 'scroll up pages back through the answer')
    } else {
      fail(`answer did not paginate (${pageCount} page) — cannot exercise paging`)
    }

    // 9. A server push renders as a banner
    since = await mark()
    const pushed = await fetch(`${BRIDGE_HTTP}/control/push`, { method: 'POST', body: 'Standup starts in 5 minutes' })
    if (!pushed.ok) throw new Error(`push control -> ${pushed.status}`)
    await waitForMessageSince(since, '[app] push banner: Standup starts in 5 minutes', 8_000, 'server push renders as a banner')

    // 10. Back home
    since = await mark()
    await input('double_click')
    await sleep(600)
    await waitForMessageSince(since, '[app] view=home', 8_000, 'double-tap from chat returns to home')

    // 11. The remaining menu rows. Returning home puts the highlight back on
    //     row 0 (asserted above), so N scrolls lands on row N.
    since = await openRow(2, 'Action items')
    await waitForMessageSince(since, '[app] view=actions', 8_000, 'tap opens the Action items view')
    await waitForMessageSince(since, '[app] action items loaded', 8_000, 'action items arrive from the bridge')

    since = await mark()
    await input('double_click')
    await sleep(600)
    await waitForMessageSince(since, '[app] view=home', 8_000, 'double-tap returns from Action items')

    since = await openRow(3, 'Today')
    await waitForMessageSince(since, '[app] view=today', 8_000, 'tap opens the Today view')
    await waitForMessageSince(since, '[app] today loaded', 8_000, "today's summary arrives from the bridge")

    since = await mark()
    await input('double_click')
    await sleep(600)
    await waitForMessageSince(since, '[app] view=home', 8_000, 'double-tap returns from Today')

    // 12. Capture toggles the glasses mic and relabels its own row in place.
    const beforeToggle = await framebuffer()
    since = await openRow(4, 'Capture: off')
    await waitForMessageSince(since, '[app] capture=on', 8_000, 'tap turns glasses capture on')
    await sleep(800)
    const afterToggle = await framebuffer()
    if (afterToggle.hash !== beforeToggle.hash) {
      pass('the Capture row relabels itself on the display')
    } else {
      fail(`menu is byte-identical after the toggle (${beforeToggle.hash}) — the label never changed`)
    }

    // 13. Bridge offline is visible, not a hang: drop the bridge and check the
    //     app notices and starts retrying.
    since = await mark()
    bridgeProc.kill('SIGTERM')
    await waitForMessageSince(since, '[bridge] offline', 10_000, 'app detects the bridge going away')
    await waitForMessageSince(since, '[bridge] connecting to', 12_000, 'app retries the bridge with backoff')

    // A reload mid-run resets app state, so earlier failures would be fallout
    // from that rather than real defects. Call it out on its own line.
    await drainConsole()
    if (countMessage('[app] bridge ready') === bootsAtStart) {
      pass('app never reloaded mid-run')
    } else {
      fail(
        `app reloaded ${countMessage('[app] bridge ready') - bootsAtStart} time(s) mid-run — ` +
          `any failure above may be fallout from the reset`,
      )
    }

    const bad = seen.filter((e) => {
      const m = e.message ?? ''
      return m.startsWith('[uncaught]') || m.startsWith('[unhandledrejection]') || e.level === 'error'
    })
    if (bad.length === 0) {
      pass('no uncaught errors or failed fetches')
    } else {
      fail(`${bad.length} error entr${bad.length === 1 ? 'y' : 'ies'}:`)
      for (const e of bad.slice(0, 10)) console.log(`          [${e.level}] ${e.message}`)
    }

    if (DUMP) {
      console.log('\n--- console dump ---')
      for (const e of seen) console.log(`  [${e.level}] ${e.message}`)
      console.log('--- mock bridge ---')
      console.log(bridgeLog.trim())
    }
  } finally {
    cleanup()
  }

  console.log(failures === 0 ? `\nAll checks passed.\n` : `\n${failures} check${failures === 1 ? '' : 's'} failed.\n`)
  process.exit(failures === 0 ? 0 : 1)
}

main().catch((e) => {
  console.error(`\nVerification crashed: ${e.stack ?? e}`)
  process.exit(2)
})
