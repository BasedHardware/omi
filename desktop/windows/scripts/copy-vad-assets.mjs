// Stage the @ricky0123/vad-web runtime assets into the renderer's public dir so
// they're served at /vad/ (dev: vite server; prod: rendererServer over the built
// out/renderer). vadEngine.ts points baseAssetPath + onnxWASMBasePath at /vad/.
//
// We copy the EXACT files the wasm lane loads, not the whole ort dist (the jsep /
// asyncify / jspi wasm variants are 15–26MB EACH and unused by onnxruntime-web/wasm,
// which vad-web imports). If an ort/vad version bump renames a file, the presence
// check below hard-fails with both versions named — so a silent 404 (which would
// make the VAD fall back to passthrough undetected) can't slip through.
//
// Idempotent: skips a file already present at the same size unless --force.
// Output (src/renderer/public/vad/) is gitignored like the audio fixtures.
//
// Phase 5 additions, same dir (served at /vad/):
//   - @mediapipe/tasks-audio SIMD wasm pair (loopback speech/music classifier
//     runtime — Electron's Chromium always has wasm SIMD, so the nosimd
//     variants are deliberately not staged).
//   - yamnet.tflite (~4MB), DOWNLOADED from the official pinned MediaPipe
//     model URL and verified against a pinned sha256 — not checked into git.
import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import { fileURLToPath } from 'node:url'

const ROOT = fileURLToPath(new URL('../', import.meta.url))
const FORCE = process.argv.includes('--force')
const OUT_DIR = path.join(ROOT, 'src/renderer/public/vad')
const VAD_DIST = path.join(ROOT, 'node_modules/@ricky0123/vad-web/dist')
const ORT_DIST = path.join(ROOT, 'node_modules/onnxruntime-web/dist')
const MP_AUDIO_WASM = path.join(ROOT, 'node_modules/@mediapipe/tasks-audio/wasm')

// Official MediaPipe-hosted YAMNet (float32 v1). Version-pinned URL + sha256:
// a silent upstream swap fails the hash check instead of shipping unknown bits.
const YAMNET_URL =
  'https://storage.googleapis.com/mediapipe-models/audio_classifier/yamnet/float32/1/yamnet.tflite'
const YAMNET_SHA256 = '4d8b4a53282dc83ef04e3e7dbc4fbc98082e34e44ed798e16c3a0cdd4c584faf'
const YAMNET_FILE = 'yamnet.tflite'

function version(pkgDir) {
  try {
    return JSON.parse(fs.readFileSync(path.join(pkgDir, '../package.json'), 'utf8')).version
  } catch {
    return '?'
  }
}

// [sourceDir, filename] — the minimal set the /vad/ lane actually fetches.
const ASSETS = [
  [VAD_DIST, 'silero_vad_v5.onnx'], // model:'v5' weights
  [VAD_DIST, 'silero_vad_legacy.onnx'], // defensive: model:'legacy' fallback
  [VAD_DIST, 'vad.worklet.bundle.min.js'], // the 'vad-helper-worklet' processor
  [ORT_DIST, 'ort-wasm-simd-threaded.wasm'], // onnxruntime-web/wasm backend binary
  [ORT_DIST, 'ort-wasm-simd-threaded.mjs'], // its JS glue (referenced by the wasm bundle)
  [MP_AUDIO_WASM, 'audio_wasm_internal.js'], // MediaPipe AudioClassifier loader (SIMD)
  [MP_AUDIO_WASM, 'audio_wasm_internal.wasm'] // MediaPipe AudioClassifier runtime (SIMD)
]

function sha256(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')
}

/** Download yamnet.tflite (pinned URL) unless a hash-valid copy is present.
 *  A hash mismatch (upstream swap or truncated download) hard-fails. An
 *  unreachable URL on a fresh checkout DEGRADES to a warning (offline/CI
 *  without the cached asset): the loopback classifier already fails open to
 *  passthrough when the model is absent, so the build must not hard-fail on it. */
async function ensureYamnet() {
  const dest = path.join(OUT_DIR, YAMNET_FILE)
  if (!FORCE && fs.existsSync(dest) && sha256(dest) === YAMNET_SHA256) {
    log(`${YAMNET_FILE.padEnd(34)} already present (sha256 ok)`)
    return
  }
  log(`downloading ${YAMNET_FILE} …`)
  let res
  try {
    res = await fetch(YAMNET_URL)
  } catch (e) {
    log(`WARN yamnet download unreachable (${e.message}) — skipping; loopback classifier will pass through`)
    return
  }
  if (!res.ok) {
    log(`WARN yamnet download failed: HTTP ${res.status} — skipping; loopback classifier will pass through`)
    return
  }
  const buf = Buffer.from(await res.arrayBuffer())
  const got = crypto.createHash('sha256').update(buf).digest('hex')
  if (got !== YAMNET_SHA256) {
    // A mismatch (not just absence) is a supply-chain signal — still hard-fail.
    throw new Error(
      `[vad-assets] yamnet.tflite sha256 mismatch:\n  expected ${YAMNET_SHA256}\n  got      ${got}\n` +
        `  The pinned upstream file changed — verify the new model before updating the pin.`
    )
  }
  fs.writeFileSync(dest, buf)
  log(`${YAMNET_FILE.padEnd(34)} ${(buf.length / 1024 / 1024).toFixed(2)}MB downloaded (sha256 ok)`)
}

function log(msg) {
  console.log(`[vad-assets] ${msg}`)
}

async function main() {
  const missing = ASSETS.filter(([dir, file]) => !fs.existsSync(path.join(dir, file)))
  if (missing.length > 0) {
    const names = missing.map(([, f]) => f).join(', ')
    throw new Error(
      `[vad-assets] source asset(s) not found: ${names}\n` +
        `  vad-web@${version(VAD_DIST)}, onnxruntime-web@${version(ORT_DIST)}\n` +
        `  A version bump likely renamed these — update scripts/copy-vad-assets.mjs to match ` +
        `node_modules/@ricky0123/vad-web/dist and node_modules/onnxruntime-web/dist, then re-run ` +
        `\`pnpm vad:assets --force\`.`
    )
  }

  fs.mkdirSync(OUT_DIR, { recursive: true })
  let copied = 0
  for (const [dir, file] of ASSETS) {
    const src = path.join(dir, file)
    const dest = path.join(OUT_DIR, file)
    const srcSize = fs.statSync(src).size
    if (!FORCE && fs.existsSync(dest) && fs.statSync(dest).size === srcSize) continue
    fs.copyFileSync(src, dest)
    copied++
    log(`${file.padEnd(34)} ${(srcSize / 1024 / 1024).toFixed(2)}MB`)
  }
  log(
    copied === 0
      ? `all ${ASSETS.length} assets already present in ${OUT_DIR} (use --force to overwrite)`
      : `copied ${copied}/${ASSETS.length} → ${OUT_DIR} (vad-web@${version(VAD_DIST)}, ort@${version(ORT_DIST)})`
  )
  await ensureYamnet()
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
