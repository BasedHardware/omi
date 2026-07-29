#!/usr/bin/env node
/**
 * End-to-end verification of the G2 app against the EvenHub simulator.
 *
 * Drives the simulator's automation HTTP API to assert the app actually
 * renders and responds to touchpad input:
 *   1. the start-up page container is created
 *   2. the glasses framebuffer is non-blank
 *   3. two taps advance the counter 1 -> 2
 *   4. a double-tap requests the system exit dialog
 *   5. no uncaught errors were logged
 *
 * Requires the Vite dev server on :5173 and the simulator's platform binary.
 * Needs a GUI (the simulator opens a window), so this is a local check and is
 * deliberately not wired into CI.
 *
 * Usage: npm run dev   (separate terminal)
 *        npm run verify
 */
import { spawn } from 'node:child_process'
import { inflateSync } from 'node:zlib'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)

const DEV_URL = process.env.DEV_URL ?? 'http://localhost:5173'
const PORT = Number(process.env.AUTOMATION_PORT ?? 9898)
const API = `http://127.0.0.1:${PORT}`

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

async function litPixels() {
  const r = await fetch(`${API}/api/screenshot/glasses`)
  if (!r.ok) throw new Error(`screenshot ${r.status}`)
  const png = decodePng(Buffer.from(await r.arrayBuffer()))
  let lit = 0
  // Background is alpha=0, lit text is alpha=255. Never convert to RGB — both
  // are pure green and become indistinguishable.
  for (let i = 3; i < png.data.length; i += 4) {
    if (png.data[i] > 0) lit++
  }
  return { lit, width: png.width, height: png.height }
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

async function waitForMessage(needle, timeoutMs, label) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    await drainConsole()
    if (sawMessage(needle)) {
      pass(label)
      return true
    }
    await sleep(300)
  }
  fail(`${label} — never saw "${needle}" within ${timeoutMs}ms`)
  return false
}

// --------------------------------------------------------------------- main

async function main() {
  console.log(`\nEvenHub G2 simulator verification`)
  console.log(`  dev server:     ${DEV_URL}`)
  console.log(`  automation API: ${API}\n`)

  // Fail fast with a clear message rather than a confusing simulator error.
  try {
    const r = await fetch(DEV_URL)
    if (!r.ok) throw new Error(`status ${r.status}`)
  } catch (e) {
    console.error(`Dev server not reachable at ${DEV_URL} (${e.message}).`)
    console.error(`Start it first:  npm run dev`)
    process.exit(2)
  }

  // A leftover simulator holding the automation port would answer every request
  // here and silently produce a green run against a stale instance. Refuse to
  // start instead.
  if (await ping()) {
    console.error(`Something is already serving the automation API on ${API}.`)
    console.error(`That is almost certainly a leftover simulator. Kill it first:`)
    console.error(`  pkill -f evenhub-simulator`)
    process.exit(2)
  }

  const launcher = require.resolve('@evenrealities/evenhub-simulator/bin/index.js')
  // detached:true puts the launcher and the platform binary it exec's into
  // their own process group, so cleanup can kill both. Killing just the Node
  // launcher leaves the simulator running and holding the port.
  const sim = spawn(process.execPath, [launcher, DEV_URL, '--automation-port', String(PORT)], {
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: true,
  })
  let simErr = ''
  sim.stderr.on('data', (d) => (simErr += d.toString()))
  sim.on('exit', (code) => {
    if (code !== 0 && code !== null) {
      console.error(`\nSimulator exited early (code ${code}):\n${simErr}`)
    }
  })

  let cleanedUp = false
  const cleanup = () => {
    if (cleanedUp) return
    cleanedUp = true
    try {
      process.kill(-sim.pid, 'SIGTERM') // negative pid = the whole group
    } catch {
      /* already gone */
    }
  }
  process.on('exit', cleanup)
  process.on('SIGINT', () => { cleanup(); process.exit(130) })

  try {
    // 1. Simulator up
    const deadline = Date.now() + 30_000
    let up = false
    while (Date.now() < deadline) {
      if (await ping()) { up = true; break }
      await sleep(500)
    }
    if (!up) {
      console.error(`Simulator automation API never came up on ${API}.\n${simErr}`)
      process.exit(2)
    }
    pass('simulator automation API is up')

    // 2. App booted and created its page container. Poll before clearing —
    //    startup logs are emitted once and would be lost.
    await waitForMessage('[app] bridge ready', 20_000, 'SDK bridge connected')
    await waitForMessage('[app] page created: success', 20_000, 'start-up page container created')

    // 3. Something is actually on the display
    const { lit, width, height } = await litPixels()
    if (width !== 576 || height !== 288) {
      fail(`framebuffer is ${width}x${height}, expected 576x288`)
    } else {
      pass(`framebuffer is ${width}x${height}`)
    }
    if (lit > 200) {
      pass(`display is rendering (${lit} lit pixels)`)
    } else {
      fail(`display looks blank (only ${lit} lit pixels)`)
    }

    // 4. Taps advance the counter
    await input('click')
    await sleep(600)
    await waitForMessage('[app] count=1', 5_000, 'first tap -> count=1')

    await input('click')
    await sleep(600)
    await waitForMessage('[app] count=2', 5_000, 'second tap -> count=2')

    const afterTaps = await litPixels()
    if (afterTaps.lit > 200) {
      pass(`display still rendering after taps (${afterTaps.lit} lit pixels)`)
    } else {
      fail(`display went blank after taps (${afterTaps.lit} lit pixels)`)
    }

    // 5. Double-tap requests exit
    await input('double_click')
    await sleep(600)
    await waitForMessage('[app] exit requested', 5_000, 'double-tap -> exit requested')

    // 6. No crashes anywhere in the run
    await drainConsole()
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
  } finally {
    cleanup()
  }

  console.log(
    failures === 0
      ? `\nAll checks passed.\n`
      : `\n${failures} check${failures === 1 ? '' : 's'} failed.\n`,
  )
  process.exit(failures === 0 ? 0 : 1)
}

main().catch((e) => {
  console.error(`\nVerification crashed: ${e.stack ?? e}`)
  process.exit(2)
})
