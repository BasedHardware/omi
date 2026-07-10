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
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = fileURLToPath(new URL('../', import.meta.url))
const FORCE = process.argv.includes('--force')
const OUT_DIR = path.join(ROOT, 'src/renderer/public/vad')
const VAD_DIST = path.join(ROOT, 'node_modules/@ricky0123/vad-web/dist')
const ORT_DIST = path.join(ROOT, 'node_modules/onnxruntime-web/dist')

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
  [ORT_DIST, 'ort-wasm-simd-threaded.mjs'] // its JS glue (referenced by the wasm bundle)
]

function log(msg) {
  console.log(`[vad-assets] ${msg}`)
}

function main() {
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
}

main()
