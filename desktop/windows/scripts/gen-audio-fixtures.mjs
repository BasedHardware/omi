// Generate PTT audio fixtures: real synthesized speech (Windows SAPI) plus derived
// silence/quiet/short clips, all as raw 16 kHz mono 16-bit little-endian PCM — the
// exact format the app streams and POSTs. Output is gitignored (test/fixtures/audio/);
// run `pnpm fixtures:audio` (idempotent; pass --force to regenerate).
//
// A manifest.json records per-fixture stats (bytes, ms, rms, voicedMs at the app's
// own 20ms/RMS-300 gate rule) so tests assert against measured values, not magic
// numbers. The generator self-checks that SAPI produced real speech (voicedMs >= 800
// on the hello clip) and hard-fails otherwise — catches a silent/broken TTS voice.
//
// ffmpeg (optional) can play a fixture back for a human ear:
//   ffmpeg -f s16le -ar 16000 -ac 1 -i test/fixtures/audio/speech-hello.pcm out.wav
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const OUT_DIR = fileURLToPath(new URL('../test/fixtures/audio/', import.meta.url))
const FORCE = process.argv.includes('--force')

const SAMPLE_RATE = 16000
// Mirror the app's gate constants (src/renderer/src/lib/ptt/constants.ts). Kept as
// literals here so the generator is dependency-free; the manifest self-check below
// would catch drift loudly if the gate rule ever changes.
const VOICED_RMS_THRESHOLD = 300
const VOICED_FRAME_SAMPLES = 320 // 20ms @ 16kHz

// Each clip opens with "Omi test fixture" (test-data hygiene) so that if a fixture
// is ever transcribed into a real account it is unmistakably identifiable as test
// data. The live PTT E2E only asserts the "hello"/"world" tokens, which remain.
const SPEECH_TEXTS = {
  'speech-hello': 'Omi test fixture. Hello world. Testing one two three.',
  'speech-long':
    'Omi test fixture. ' +
    Array(12)
      .fill(
        'The quick brown fox jumps over the lazy dog while the transcription service listens carefully to every word.'
      )
      .join(' ')
}

function log(msg) {
  console.log(`[fixtures] ${msg}`)
}

/** Render `text` to a 16kHz mono 16-bit WAV via Windows SAPI (System.Speech). */
function sapiSpeakToWav(text, wavPath) {
  const ps1 = path.join(os.tmpdir(), `omi-tts-${Date.now()}.ps1`)
  const script = [
    'Add-Type -AssemblyName System.Speech',
    '$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer',
    '$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(',
    '  16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,',
    '  [System.Speech.AudioFormat.AudioChannel]::Mono)',
    `$synth.SetOutputToWaveFile('${wavPath.replace(/'/g, "''")}', $fmt)`,
    '$synth.Rate = 0',
    `$synth.Speak('${text.replace(/'/g, "''")}')`,
    '$synth.Dispose()'
  ].join('\n')
  fs.writeFileSync(ps1, script, 'utf8')
  try {
    execFileSync('powershell', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ps1], {
      stdio: 'pipe',
      timeout: 120_000
    })
  } finally {
    fs.rmSync(ps1, { force: true })
  }
}

/** Extract the raw PCM payload from a WAV, verifying it is 16kHz/mono/16-bit.
 *  Walks RIFF chunks properly — SAPI may emit chunks beyond the canonical 44-byte
 *  header, so never assume a fixed offset. */
function wavToPcm(wavPath) {
  const buf = fs.readFileSync(wavPath)
  if (buf.toString('ascii', 0, 4) !== 'RIFF' || buf.toString('ascii', 8, 12) !== 'WAVE') {
    throw new Error(`${wavPath}: not a RIFF/WAVE file`)
  }
  let off = 12
  let fmt = null
  let data = null
  while (off + 8 <= buf.length) {
    const id = buf.toString('ascii', off, off + 4)
    const size = buf.readUInt32LE(off + 4)
    const body = off + 8
    if (id === 'fmt ') {
      fmt = {
        format: buf.readUInt16LE(body),
        channels: buf.readUInt16LE(body + 2),
        sampleRate: buf.readUInt32LE(body + 4),
        bitsPerSample: buf.readUInt16LE(body + 14)
      }
    } else if (id === 'data') {
      data = buf.subarray(body, body + size)
    }
    off = body + size + (size % 2) // chunks are word-aligned
  }
  if (!fmt || !data) throw new Error(`${wavPath}: missing fmt/data chunk`)
  if (fmt.format !== 1 || fmt.channels !== 1 || fmt.sampleRate !== SAMPLE_RATE || fmt.bitsPerSample !== 16) {
    throw new Error(`${wavPath}: expected PCM 16kHz/mono/16-bit, got ${JSON.stringify(fmt)}`)
  }
  return data
}

/** RMS of one 20ms frame — the single copy of the gate's frame rule here. */
function frameRms(pcm, frame) {
  const base = frame * VOICED_FRAME_SAMPLES
  let sumSq = 0
  for (let i = 0; i < VOICED_FRAME_SAMPLES; i++) sumSq += pcm[base + i] * pcm[base + i]
  return Math.sqrt(sumSq / VOICED_FRAME_SAMPLES)
}

/** Per-fixture stats using the app's gate rule (20ms frames, RMS >= threshold). */
function stats(pcmBuf) {
  const pcm = new Int16Array(pcmBuf.buffer, pcmBuf.byteOffset, pcmBuf.byteLength / 2)
  let sumSq = 0
  for (let i = 0; i < pcm.length; i++) sumSq += pcm[i] * pcm[i]
  const rms = pcm.length ? Math.round(Math.sqrt(sumSq / pcm.length)) : 0

  let voicedFrames = 0
  const frames = Math.floor(pcm.length / VOICED_FRAME_SAMPLES)
  for (let f = 0; f < frames; f++) {
    if (frameRms(pcm, f) >= VOICED_RMS_THRESHOLD) voicedFrames++
  }
  return {
    bytes: pcmBuf.byteLength,
    ms: Math.round((pcm.length / SAMPLE_RATE) * 1000),
    rms,
    voicedMs: voicedFrames * 20
  }
}

/** First 20ms frame index with RMS >= threshold, or -1. */
function firstVoicedFrame(pcm) {
  const frames = Math.floor(pcm.length / VOICED_FRAME_SAMPLES)
  for (let f = 0; f < frames; f++) {
    if (frameRms(pcm, f) >= VOICED_RMS_THRESHOLD) return f
  }
  return -1
}

function main() {
  const targets = [
    'speech-hello.pcm',
    'speech-long.pcm',
    'silence-2s.pcm',
    'speech-quiet.pcm',
    'speech-short-200ms.pcm',
    'manifest.json'
  ]
  if (!FORCE && targets.every((f) => fs.existsSync(path.join(OUT_DIR, f)))) {
    log('all fixtures present — skipping (use --force to regenerate)')
    return
  }
  fs.mkdirSync(OUT_DIR, { recursive: true })
  const manifest = {}

  // 1. Real speech via SAPI.
  const speech = {}
  for (const [name, text] of Object.entries(SPEECH_TEXTS)) {
    const wav = path.join(OUT_DIR, `${name}.wav`)
    log(`SAPI: rendering ${name} (${text.length} chars)…`)
    sapiSpeakToWav(text, wav)
    const pcm = wavToPcm(wav)
    fs.rmSync(wav, { force: true })
    fs.writeFileSync(path.join(OUT_DIR, `${name}.pcm`), pcm)
    speech[name] = pcm
    manifest[`${name}.pcm`] = stats(pcm)
  }

  // Self-check: a silent/broken TTS voice would poison every downstream test.
  if (manifest['speech-hello.pcm'].voicedMs < 800) {
    throw new Error(
      `SAPI produced only ${manifest['speech-hello.pcm'].voicedMs}ms of voiced audio for speech-hello — TTS voice appears broken`
    )
  }

  const hello = new Int16Array(
    speech['speech-hello'].buffer,
    speech['speech-hello'].byteOffset,
    speech['speech-hello'].byteLength / 2
  )

  // 2. Silence: low random noise (±20) — a realistic mic floor, far below RMS 300.
  const silence = new Int16Array(2 * SAMPLE_RATE)
  for (let i = 0; i < silence.length; i++) silence[i] = Math.floor(Math.random() * 41) - 20
  fs.writeFileSync(path.join(OUT_DIR, 'silence-2s.pcm'), Buffer.from(silence.buffer))
  manifest['silence-2s.pcm'] = stats(Buffer.from(silence.buffer))

  // 3. Quiet speech: hello attenuated below the gate (SAPI speech RMS is typically
  //    1500–4000; ×0.05 lands well under the 300 threshold).
  const quiet = new Int16Array(hello.length)
  for (let i = 0; i < hello.length; i++) quiet[i] = Math.round(hello[i] * 0.05)
  fs.writeFileSync(path.join(OUT_DIR, 'speech-quiet.pcm'), Buffer.from(quiet.buffer))
  manifest['speech-quiet.pcm'] = stats(Buffer.from(quiet.buffer))

  // 4. 200ms voiced slice: from the first gated-voiced frame of hello.
  const f0 = firstVoicedFrame(hello)
  if (f0 < 0) throw new Error('no voiced frame found in speech-hello — cannot cut short fixture')
  const start = f0 * VOICED_FRAME_SAMPLES
  const short = hello.slice(start, start + Math.round(0.2 * SAMPLE_RATE))
  fs.writeFileSync(path.join(OUT_DIR, 'speech-short-200ms.pcm'), Buffer.from(short.buffer))
  manifest['speech-short-200ms.pcm'] = stats(Buffer.from(short.buffer))

  fs.writeFileSync(path.join(OUT_DIR, 'manifest.json'), JSON.stringify(manifest, null, 2))
  log(`done → ${OUT_DIR}`)
  for (const [file, s] of Object.entries(manifest)) {
    log(`  ${file.padEnd(24)} ${String(s.ms).padStart(6)}ms  rms=${String(s.rms).padStart(5)}  voiced=${s.voicedMs}ms`)
  }
}

main()
