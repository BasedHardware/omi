// Persistent OCR worker, the Linux counterpart of resources/ocr-worker.ps1.
// Runs under Electron's bundled Node (spawned with ELECTRON_RUN_AS_NODE=1) and
// shells out to the Tesseract CLI, so it needs no extra npm dependency.
//
// Protocol (identical to the PowerShell worker so rewind/ocr.ts is unchanged
// apart from how it launches this):
//   in:  one absolute image path per stdin line
//   out: one compact JSON result per stdout line
//        {"ok":true,"ready":true}                ready handshake
//        {"ok":true,"text":"..."}                a recognition result
//        {"ok":false,"error":"..."}              a per-image failure
//        {"ok":false,"fatal":true,"error":"..."} engine unavailable, worker exits

const { spawnSync, execSync } = require('child_process')
const readline = require('readline')

const OCR_TIMEOUT_MS = 15000

function emit(obj) {
  process.stdout.write(JSON.stringify(obj) + '\n')
}

// Tesseract is the engine. If it is not installed we fail permanently, exactly
// like the PowerShell worker does when no OCR language pack is present.
try {
  execSync('tesseract --version', { stdio: 'ignore', timeout: 3000 })
} catch {
  emit({ ok: false, fatal: true, error: 'tesseract not installed (apt install tesseract-ocr)' })
  process.exit(1)
}

emit({ ok: true, ready: true })

const rl = readline.createInterface({ input: process.stdin })
rl.on('line', (line) => {
  const path = line.trim()
  if (!path) return
  try {
    const res = spawnSync('tesseract', [path, 'stdout'], {
      encoding: 'utf8',
      timeout: OCR_TIMEOUT_MS,
      maxBuffer: 64 * 1024 * 1024
    })
    if (res.error) {
      emit({ ok: false, error: String(res.error.message || res.error).slice(0, 200) })
    } else if (res.status === 0) {
      emit({ ok: true, text: (res.stdout || '').replace(/\s+$/g, '') })
    } else {
      emit({ ok: false, error: (res.stderr || 'tesseract failed').slice(0, 200) })
    }
  } catch (e) {
    emit({ ok: false, error: String((e && e.message) || e).slice(0, 200) })
  }
})
rl.on('close', () => process.exit(0))
