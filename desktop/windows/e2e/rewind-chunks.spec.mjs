// The real WebCodecs round trip, in a real Electron renderer.
//
// Everything else about compaction is unit-tested in plain node: the container's
// bytes, the grouping, the SQL, the write/verify/claim ordering, the cursor's
// state machine. What none of that can cover is whether an actual H.264 encoder
// and decoder, driven by the production modules, turn frames into a small chunk
// and give the same frames back. That claim is the entire reason this feature
// exists, and this is the only place it can be made honestly.
//
// The hooks it drives (`window.__omiRewindChunkE2E`) call the PRODUCTION
// `encodeFramesToChunk` and `ChunkFrameReader`, not a copy — see
// src/renderer/src/rewind/chunkE2EHooks.ts.
import test from 'node:test'
import assert from 'node:assert/strict'
import path from 'node:path'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { fileURLToPath } from 'node:url'
import { _electron as electron } from 'playwright'

const here = path.dirname(fileURLToPath(import.meta.url))
const mainEntry = path.join(here, '..', 'out', 'main', 'index.js')

const WIDTH = 1280
const HEIGHT = 720
const FRAMES = 60

/**
 * The first window with the chunk hooks installed.
 *
 * Any window will do — the hooks are installed by both the main renderer and
 * the capture window — so this takes whichever is ready first rather than
 * waiting on the capture window, which only opens while capture is running.
 */
// eslint-disable-next-line @typescript-eslint/explicit-function-return-type -- plain .mjs; the repo's other e2e specs are the same shape
async function captureWindow(app) {
  const deadline = Date.now() + 60_000
  for (;;) {
    for (const win of app.windows()) {
      const installed = await win
        .evaluate(() => Boolean(window.__omiRewindChunkE2E))
        .catch(() => false)
      if (installed) return win
    }
    if (Date.now() > deadline) throw new Error('timed out waiting for the capture window')
    await new Promise((r) => setTimeout(r, 250))
  }
}

test('encodes real frames into a chunk and reads every one of them back', async (t) => {
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-e2e-chunks-'))
  const app = await electron.launch({
    args: [mainEntry, `--user-data-dir=${dir}`],
    env: { ...process.env, OMI_E2E: '1', OMI_AUTOMATION: '0', OMI_SKIP_TUNNEL: '1' }
  })
  t.after(async () => {
    try {
      await app.close()
    } catch {
      /* already closed */
    }
    rmSync(dir, { recursive: true, force: true })
  })

  const win = await captureWindow(app)

  const codec = await win.evaluate(
    ([w, h]) => window.__omiRewindChunkE2E.codecFor(w, h),
    [WIDTH, HEIGHT]
  )
  // A machine with no usable encoder is a supported state — it just never
  // compacts — but the harness machine is not allowed to be one silently.
  assert.ok(codec, 'expected this machine to support at least one chunk codec')

  const result = await win.evaluate(
    ([n, w, h]) => window.__omiRewindChunkE2E.roundTrip(n, w, h),
    [FRAMES, WIDTH, HEIGHT]
  )

  // --- Every frame came back. ---
  // The property the compactor bets the JPEGs on. A chunk that returned 59 of
  // 60 frames would have cost the user the sixtieth permanently.
  assert.equal(result.framesBack, FRAMES, 'every frame must decode back out of the chunk')

  // --- It is dramatically smaller. ---
  // The generated frames are deliberately adversarial: dense high-entropy text
  // with a full line changing every frame, which is far worse for both JPEG and
  // inter-frame prediction than a real screen. This run measures about 6.4x
  // against the 51x measured on real capture output (see
  // main/rewind/chunks/ARCHITECTURE.md). The floor is set well below what the
  // adversarial case achieves, so it asserts "inter-frame compression is
  // working" without pinning a number that varies with the encoder build.
  const ratio = result.jpegBytes / result.chunkBytes
  assert.ok(
    ratio > 3,
    `expected the chunk to be far smaller than the JPEGs, got ${ratio.toFixed(1)}x ` +
      `(${result.jpegBytes} -> ${result.chunkBytes} bytes)`
  )

  // --- The pixels survived. ---
  // Mean absolute per-channel difference against the source JPEG, worst frame.
  // Lossy at both ends (source is JPEG, chunk is H.264), so this is a real
  // tolerance, not an equality: it catches a decode that returns the wrong
  // frame, a black frame, or drifting garbage, which is what it is for.
  assert.ok(
    result.maxMeanDiff < 12,
    `decoded frames drifted too far from their sources (worst mean diff ${result.maxMeanDiff})`
  )

  console.log(
    `[rewind-chunks] ${codec}: ${FRAMES} frames, ` +
      `${(result.jpegBytes / 1024).toFixed(0)} KB of JPEGs -> ` +
      `${(result.chunkBytes / 1024).toFixed(0)} KB chunk (${ratio.toFixed(1)}x), ` +
      `worst mean pixel diff ${result.maxMeanDiff.toFixed(2)}`
  )
})
