// REAL-AUDIO voice → hub → TOOL → spoken-reply gauntlet for the Windows Omi app.
//
// The definitive "a human talking to Omi gets tools run + a spoken answer" proof
// for the voice-hub tool loop (#182, origin/main b88a503e3). For each spoken
// request it asserts the four legs:
//   (a) STT transcribed the utterance,
//   (b) the TOOL FIRED via the hub (onToolRequest → voiceToolExecute → executeHostTool),
//   (c) Omi SPOKE the reply (voiced energy captured off the cable, ≥500ms),
//   (d) the turn was RECORDED to the ONE kernel chat thread (voiceHubRecordTurn — continuity, #176).
//
// PATH: default hub-native voice = Gemini Live. The renderer's VoiceHubDriverHost
// owns the turn; a spoken tool call dispatches IN-PROCESS via window.omi.voiceToolExecute
// (main executeHostTool) — this is a DIFFERENT provider path than the pi-mono managed
// chat lane, so it works even when that lane's upstream LLM is erroring.
//
// HOW WE DRIVE IT (no __omiPtt / no bar window needed — that e2e hook isn't in main):
//   * enable the hub route: __omiVoice.setPrefs({ pttHubEnabled: true }) → warms the hub.
//   * begin/end a turn by sending the SAME IPC the bar sends, straight to the main
//     window from the MAIN PROCESS: webContents.send('voiceHub:begin'|'voiceHub:end').
//   * play the SAPI-synth request WAV into the hold (default playback = CABLE Input →
//     loops to CABLE Output = the app mic). Capture the spoken reply off CABLE Output.
//   * OBSERVABILITY: wrap window.omi.voiceToolExecute (records every hub tool call +
//     result) and window.omi.voiceHubRecordTurn (records the kernel turn: transcript +
//     reply). Also subscribe onMainChatEvent as a secondary tool signal.
//
// SAFETY: only the isolated _electron instance we launch (never :9222). Snapshot +
// RESTORE OS audio defaults in a finally. Test-data hygiene: any "buy milk" task the
// run creates is deleted via REST (diff of action-items before/after); a spawned
// agent is cancelled.
//
// Exit: 0 all legs pass for every request · 1 a gap · 2 preconditions missing.
import { execFileSync, spawn, spawnSync } from 'node:child_process'
import { _electron as electron } from 'playwright'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { readDotEnv, decodeJwt, exchangeRefreshToken } from './lib/omi-auth.mjs'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const SAMPLE_RATE = 16000
const RUN_ID = Date.now().toString(36)
const VOICED_RMS_THRESHOLD = 300
const VOICED_FRAME_SAMPLES = 320
const REPLY_VOICED_MS_MIN = 500
const HOLD_MIN_MS = 400
const TURN_TIMEOUT_MS = 90_000
const FFMPEG = 'ffmpeg'

function log(m) {
  console.log(`[voice-tool] ${m}`)
}
const results = []

// ── VB-Cable routing (verbatim pattern from agent-voice-gauntlet.mjs) ─────────
let savedAudioDefaults = null
function ps(script) {
  return spawnSync('powershell', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script], { encoding: 'utf8' })
}
function snapshotDefaults() {
  const out = ps(`Import-Module AudioDeviceCmdlets; $p=Get-AudioDevice -Playback; $r=Get-AudioDevice -Recording; "$($p.Index),$($r.Index)"`)
  const line = ((out.stdout || '').trim().split(/\r?\n/).pop() || '').trim()
  const m = line.match(/^(\d+),(\d+)$/)
  return m ? { playIndex: Number(m[1]), recIndex: Number(m[2]) } : null
}
function setupVirtualCable() {
  const probe = ps("if (Get-Module -ListAvailable -Name AudioDeviceCmdlets) { 'yes' } else { 'no' }")
  if ((probe.stdout || '').trim() !== 'yes') {
    log('AudioDeviceCmdlets module not found — cannot route the cable.')
    return false
  }
  savedAudioDefaults = snapshotDefaults()
  const setup = ps(`Import-Module AudioDeviceCmdlets
    $play = Get-AudioDevice -List | Where-Object { $_.Type -eq 'Playback' -and $_.Name -match 'CABLE Input' } | Select-Object -First 1
    $rec  = Get-AudioDevice -List | Where-Object { $_.Type -eq 'Recording' -and $_.Name -match 'CABLE Output' } | Select-Object -First 1
    if (-not $play -or -not $rec) { 'missing'; exit }
    Set-AudioDevice -Index $play.Index | Out-Null
    Set-AudioDevice -Index $rec.Index  | Out-Null
    "ok $($play.Index) $($rec.Index)"`)
  const last = ((setup.stdout || '').trim().split(/\r?\n/).pop() || '').trim()
  const m = last.match(/^ok (\d+) (\d+)$/)
  if (!m) {
    savedAudioDefaults = null
    log('VB-Audio Virtual Cable devices not found (CABLE Input / CABLE Output).')
    return false
  }
  const target = { playIndex: Number(m[1]), recIndex: Number(m[2]) }
  if (savedAudioDefaults && savedAudioDefaults.playIndex === target.playIndex && savedAudioDefaults.recIndex === target.recIndex) savedAudioDefaults = null
  log('routed default playback→CABLE Input, capture→CABLE Output')
  return true
}
function restoreAudioDefaults() {
  if (!savedAudioDefaults) return
  const { playIndex, recIndex } = savedAudioDefaults
  ps(`Import-Module AudioDeviceCmdlets; Set-AudioDevice -Index ${playIndex} | Out-Null; Set-AudioDevice -Index ${recIndex} | Out-Null`)
  log(`restored default playback→#${playIndex}, capture→#${recIndex}`)
  savedAudioDefaults = null
}
function sapiSpeakToWav(text, wavPath) {
  const ps1 = path.join(os.tmpdir(), `omi-vtg-tts-${Date.now()}-${Math.random().toString(16).slice(2)}.ps1`)
  const script = [
    'Add-Type -AssemblyName System.Speech',
    '$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer',
    '$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)',
    `$synth.SetOutputToWaveFile('${wavPath.replace(/'/g, "''")}', $fmt)`,
    '$synth.Rate = 0',
    `$synth.Speak('${text.replace(/'/g, "''")}')`,
    '$synth.Dispose()'
  ].join('\n')
  fs.writeFileSync(ps1, script, 'utf8')
  try {
    execFileSync('powershell', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ps1], { stdio: 'pipe', timeout: 120_000 })
  } finally {
    fs.rmSync(ps1, { force: true })
  }
}
function playWav(wavPath) {
  ps(`(New-Object System.Media.SoundPlayer '${wavPath.replace(/'/g, "''")}').PlaySync()`)
}
function voicedMsOfPcm(pcmBuf) {
  if (!pcmBuf || pcmBuf.byteLength < VOICED_FRAME_SAMPLES * 2) return 0
  const pcm = new Int16Array(pcmBuf.buffer, pcmBuf.byteOffset, Math.floor(pcmBuf.byteLength / 2))
  const frames = Math.floor(pcm.length / VOICED_FRAME_SAMPLES)
  let voiced = 0
  for (let f = 0; f < frames; f++) {
    const base = f * VOICED_FRAME_SAMPLES
    let sumSq = 0
    for (let i = 0; i < VOICED_FRAME_SAMPLES; i++) sumSq += pcm[base + i] * pcm[base + i]
    if (Math.sqrt(sumSq / VOICED_FRAME_SAMPLES) >= VOICED_RMS_THRESHOLD) voiced++
  }
  return voiced * 20
}
function findDshowCaptureName() {
  const out = spawnSync(FFMPEG, ['-hide_banner', '-list_devices', 'true', '-f', 'dshow', '-i', 'dummy'], { encoding: 'utf8' })
  const text = `${out.stdout || ''}\n${out.stderr || ''}`
  for (const line of text.split(/\r?\n/)) {
    const m = line.match(/"([^"]*CABLE Output[^"]*)"/i)
    if (m) return m[1]
  }
  return null
}
function startReplyCapture(deviceName, outPath) {
  const child = spawn(FFMPEG, ['-hide_banner', '-loglevel', 'error', '-f', 'dshow', '-i', `audio=${deviceName}`, '-ac', '1', '-ar', String(SAMPLE_RATE), '-f', 's16le', '-y', outPath], { stdio: ['pipe', 'ignore', 'pipe'] })
  child.stderr.on('data', () => {})
  child.on('error', () => {})
  return { child }
}
async function stopReplyCapture(cap) {
  const { child } = cap
  if (!child || child.exitCode !== null || child.killed) return
  await new Promise((resolve) => {
    let done = false
    const fin = () => { if (!done) { done = true; resolve() } }
    child.on('close', fin)
    try { child.stdin.write('q') } catch { /* fall through */ }
    setTimeout(() => { try { child.kill('SIGKILL') } catch { /* already exiting */ } ; fin() }, 4000)
  })
}

// ── Playwright helpers ─────────────────────────────────────────────────────────
async function findMainWindow(app) {
  for (let i = 0; i < 40; i++) {
    const page = app.windows().find((w) => !/#\/(capture|overlay|bar|insight-toast|meeting-toast)/.test(w.url()) && w.url() !== 'about:blank')
    if (page) return page
    await new Promise((r) => setTimeout(r, 500))
  }
  return null
}
async function waitFor(page, fn, ms, label) {
  const d = Date.now() + ms
  for (;;) {
    const v = await page.evaluate(fn)
    if (v) return v
    if (Date.now() > d) throw new Error(`timeout waiting for ${label}`)
    await new Promise((r) => setTimeout(r, 400))
  }
}
async function injectAuth(page, { apiKey, idToken, refreshToken }) {
  const c = decodeJwt(idToken)
  if (!c?.user_id) throw new Error('bad injected ID token')
  const user = { uid: c.user_id, email: c.email ?? null, emailVerified: !!c.email_verified, displayName: c.name ?? null, isAnonymous: false, photoURL: c.picture ?? null, providerData: [], stsTokenManager: { refreshToken, accessToken: idToken, expirationTime: c.exp * 1000 }, createdAt: String(Date.now()), lastLoginAt: String(Date.now()), apiKey, appName: '[DEFAULT]' }
  await page.evaluate(({ key, value }) => localStorage.setItem(key, JSON.stringify(value)), { key: `firebase:authUser:${apiKey}:[DEFAULT]`, value: user })
}

// ── The spoken matrix ──────────────────────────────────────────────────────────
const TESTS = [
  { id: 'get_action_items', request: 'What are my tasks?', expect: ['get_action_items'], alt: ['get_tasks', 'search_tasks', 'execute_sql'] },
  { id: 'capture_screen', request: 'Take a screenshot of my screen.', expect: ['capture_screen'], alt: ['screenshot', 'get_work_context'], allowDenied: true },
  { id: 'create_action_item', request: 'Add a task: buy milk tomorrow.', expect: ['create_action_item'], creates: /buy milk/i },
  { id: 'get_memories', request: 'What do you know about me?', expect: ['get_memories'], alt: ['search_memories'] },
  { id: 'list_agent_sessions', request: 'List my running agent sessions.', expect: ['list_agent_sessions'], alt: ['get_agent_run'] }
]

async function restActionItems(base, idToken) {
  const res = await fetch(`${base.replace(/\/$/, '')}/v1/action-items?limit=200`, { headers: { Authorization: `Bearer ${idToken}` } })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const data = await res.json().catch(() => ({}))
  const items = Array.isArray(data) ? data : data.action_items || data.items || []
  return items.map((it) => ({ id: it.id || it.action_item_id || it.backendId, description: String(it.description || it.content || '') }))
}

async function main() {
  const env = readDotEnv(path.join(root, '.env'))
  const refreshToken = process.env.OMI_E2E_REFRESH_TOKEN ?? env.OMI_E2E_REFRESH_TOKEN
  const apiKey = process.env.VITE_FIREBASE_API_KEY ?? env.VITE_FIREBASE_API_KEY
  if (!refreshToken || !apiKey) { log('SKIP: refresh token / api key missing'); process.exit(2) }
  const restBases = [env.VITE_OMI_DESKTOP_API_BASE, env.VITE_OMI_API_BASE, 'https://api.omi.me'].filter(Boolean)

  if (spawnSync(FFMPEG, ['-version'], { encoding: 'utf8' }).status !== 0) { log('SKIP: ffmpeg not on PATH'); process.exit(2) }
  const mainEntry = path.join(root, 'out', 'main', 'index.js')
  if (!fs.existsSync(mainEntry)) { log(`SKIP: build missing (${mainEntry})`); process.exit(2) }
  if (!setupVirtualCable()) { restoreAudioDefaults(); process.exit(2) }
  const dshowName = findDshowCaptureName()
  if (!dshowName) { log('SKIP: ffmpeg dshow cannot see CABLE Output'); restoreAudioDefaults(); process.exit(2) }
  log(`ffmpeg reply device: "${dshowName}"`)

  let idToken
  try { idToken = await exchangeRefreshToken(refreshToken, apiKey) } catch (e) { log(`SKIP: token exchange failed (${e.message})`); restoreAudioDefaults(); process.exit(2) }
  const uid = decodeJwt(idToken)?.user_id
  log(`auth ok uid=${uid}`)

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'omi-vtg-'))
  const ud = fs.mkdtempSync(path.join(os.tmpdir(), 'omi-vtg-ud-'))
  const auditLog = path.join(tmp, 'pi-mono-audit.log')
  const mainLines = []
  let exitCode = 0
  let app = null

  try {
    app = await electron.launch({ args: [mainEntry, `--user-data-dir=${ud}`], env: { ...process.env, OMI_E2E: '1', OMI_ALLOW_VIRTUAL_MIC: '1', OMI_AUTOMATION: '0', OMI_PI_AUDIT_LOG: auditLog } })
    const proc = app.process()
    const keep = /mint|realtime|hub|gemini|openai|tool|voice|provider|upstream|401|402|403|429|5\d\d|error|warm|session/i
    const onLine = (d) => { for (const l of d.toString().split(/\r?\n/)) { const s = l.trim(); if (s && keep.test(s)) mainLines.push(s) } }
    proc.stderr?.on('data', onLine)
    proc.stdout?.on('data', onLine)

    // ── Sign in ──
    let page = await findMainWindow(app)
    if (!page) throw new Error('main window never appeared')
    await page.waitForLoadState('domcontentloaded')
    await injectAuth(page, { apiKey, idToken, refreshToken })
    await page.evaluate(() => { const K = 'omi-windows-prefs-v1'; const p = JSON.parse(localStorage.getItem(K) ?? '{}'); p.onboardingCompletedAt = p.onboardingCompletedAt ?? Date.now(); localStorage.setItem(K, JSON.stringify(p)); location.reload() })
    await new Promise((r) => setTimeout(r, 3000))
    page = await findMainWindow(app)
    await page.waitForLoadState('domcontentloaded')
    await waitFor(page, () => typeof globalThis.__omiVoice?.getAuthUid === 'function', 30_000, 'e2e hook')
    const signedUid = await waitFor(page, () => globalThis.__omiVoice.getAuthUid(), 30_000, 'signed-in uid')
    log(`signed in ${signedUid}`)

    // ── Enable the hub route + wire observability ──
    await page.evaluate(() => {
      globalThis.__omiVoice.setPrefs({ pttHubEnabled: true })
      window.__toolCalls = []
      window.__recorded = []
      window.__tev = []
      const oExec = window.omi.voiceToolExecute.bind(window.omi)
      window.omi.voiceToolExecute = async (args) => {
        const rec = { name: args?.name, argumentsJSON: args?.argumentsJSON, at: Date.now(), result: null }
        window.__toolCalls.push(rec)
        try { rec.result = await oExec(args) } catch (e) { rec.result = `THROW ${String(e)}` }
        return rec.result
      }
      const oRec = window.omi.voiceHubRecordTurn.bind(window.omi)
      window.omi.voiceHubRecordTurn = (a) => { window.__recorded.push({ userText: a?.userText, assistantText: a?.assistantText, at: Date.now() }); return oRec(a) }
      window.omi.onMainChatEvent((e) => window.__tev.push(e))
    })

    // Wait for the hub to warm: the tool catalog needs a signed-in owner, and the
    // hub warms via useHubWarmLifecycle once pttHubEnabled flips on. Poll the catalog.
    let catalog = []
    for (let i = 0; i < 40; i++) {
      catalog = await page.evaluate(async () => { try { return await window.omi.voiceHubToolCatalog() } catch { return [] } })
      if (catalog.length) break
      await new Promise((r) => setTimeout(r, 1000))
    }
    log(`voice tool catalog (${catalog.length}): ${catalog.map((t) => t.name).join(', ') || '(empty)'}`)
    // Give the warm socket time to mint + connect (best effort).
    await new Promise((r) => setTimeout(r, 8000))
    const warmLines = mainLines.filter((l) => /mint|warm|connect|realtime|session/i.test(l)).slice(-12)
    log(`hub warm log tail: ${warmLines.join(' || ') || '(none captured)'}`)

    // Silent warm-up turn: the FIRST mic-capture graph creation is slow, so warm it
    // (and give the hub a live begin/commit) with a short audio-less hold before the
    // scored matrix. Discarded regardless of outcome.
    try {
      await app.evaluate(({ BrowserWindow }) => {
        const win = BrowserWindow.getAllWindows().find((w) => { const u = w.webContents.getURL(); return !/#\/(capture|overlay|bar|insight-toast|meeting-toast)/.test(u) && u !== 'about:blank' })
        win?.webContents.send('voiceHub:begin', { backfillMs: 0 })
      })
      await new Promise((r) => setTimeout(r, 900))
      await app.evaluate(({ BrowserWindow }) => {
        const win = BrowserWindow.getAllWindows().find((w) => { const u = w.webContents.getURL(); return !/#\/(capture|overlay|bar|insight-toast|meeting-toast)/.test(u) && u !== 'about:blank' })
        win?.webContents.send('voiceHub:end')
      })
      await new Promise((r) => setTimeout(r, 4000))
      log('mic/hub warm-up hold done')
    } catch { /* non-fatal */ }

    // Snapshot action items for cleanup diff.
    let itemsBefore = []
    for (const b of restBases) { try { itemsBefore = await restActionItems(b, idToken); break } catch { /* try next base */ } }

    // ── Drive each spoken request ──
    for (const t of TESTS) {
      const wav = path.join(tmp, `${t.id}.wav`)
      sapiSpeakToWav(`Omi test fixture. ${t.request}`, wav)
      await page.evaluate(() => { window.__toolCalls = []; window.__recorded = []; window.__tev = [] })

      log(`[${t.id}] speaking: "${t.request}"`)
      // Begin the hub turn (main-process → main window IPC, same as the bar sends).
      await app.evaluate(({ BrowserWindow }) => {
        const win = BrowserWindow.getAllWindows().find((w) => { const u = w.webContents.getURL(); return !/#\/(capture|overlay|bar|insight-toast|meeting-toast)/.test(u) && u !== 'about:blank' })
        win?.webContents.send('voiceHub:begin', { backfillMs: 0 })
      })
      await new Promise((r) => setTimeout(r, 250))
      const holdStart = Date.now()
      playWav(wav) // blocks for the clip
      const held = Date.now() - holdStart
      if (held < HOLD_MIN_MS) await new Promise((r) => setTimeout(r, HOLD_MIN_MS - held + 50))
      await app.evaluate(({ BrowserWindow }) => {
        const win = BrowserWindow.getAllWindows().find((w) => { const u = w.webContents.getURL(); return !/#\/(capture|overlay|bar|insight-toast|meeting-toast)/.test(u) && u !== 'about:blank' })
        win?.webContents.send('voiceHub:end')
      })

      // Capture the spoken reply from now on.
      const replyPcm = path.join(tmp, `${t.id}-reply.pcm`)
      const cap = startReplyCapture(dshowName, replyPcm)

      // Wait for the turn to complete (recorded to kernel) OR a tool + reply, OR timeout.
      const deadline = Date.now() + TURN_TIMEOUT_MS
      for (;;) {
        const st = await page.evaluate(() => ({ recorded: window.__recorded.length, tools: window.__toolCalls.length }))
        if (st.recorded > 0) break
        if (Date.now() > deadline) break
        await new Promise((r) => setTimeout(r, 500))
      }
      // Drain the tail of the spoken reply.
      await new Promise((r) => setTimeout(r, 2500))
      await stopReplyCapture(cap)

      const snap = await page.evaluate(() => ({ toolCalls: window.__toolCalls, recorded: window.__recorded, tev: window.__tev.filter((e) => e.type === 'tool_activity') }))
      let replyPcmBuf = null
      try { replyPcmBuf = fs.readFileSync(replyPcm) } catch { /* no reply captured */ }
      const voicedMs = voicedMsOfPcm(replyPcmBuf)

      const toolNames = [...new Set(snap.toolCalls.map((c) => c.name).filter(Boolean))]
      const accepted = new Set([...(t.expect || []), ...(t.alt || [])])
      const firedExpected = toolNames.filter((n) => (t.expect || []).includes(n))
      const firedAccepted = toolNames.filter((n) => accepted.has(n))
      const rec = snap.recorded[snap.recorded.length - 1] || {}
      const transcript = (rec.userText || '').trim()
      const reply = (rec.assistantText || '').trim()
      // audit log corroboration (may or may not capture in-process host tools)
      let auditTools = []
      try {
        auditTools = [...new Set(fs.readFileSync(auditLog, 'utf8').split(/\r?\n/).filter(Boolean).map((l) => { try { return JSON.parse(l) } catch { return null } }).filter((o) => o && o.phase === 'after').map((o) => o.tool))]
      } catch { /* no audit log */ }

      const toolVerdict = firedExpected.length ? 'FIRED' : firedAccepted.length ? 'FIRED(alt)' : toolNames.length ? `DIFFERENT[${toolNames}]` : 'NO-TOOL'
      const transcribed = transcript.length > 0 || toolNames.length > 0 // a tool call implies STT produced text
      const spoke = voicedMs >= REPLY_VOICED_MS_MIN
      const recorded = snap.recorded.length > 0
      const toolResults = snap.toolCalls.map((c) => `${c.name}→${String(c.result || '').slice(0, 70).replace(/\s+/g, ' ')}`).join(' | ')

      results.push({ id: t.id, request: t.request, transcript, transcribed, toolVerdict, fired: (firedExpected[0] || firedAccepted[0] || toolNames.join(',') || '-'), spoke, voicedMs, recorded, reply: reply.slice(0, 90), toolResults: toolResults.slice(0, 180), audit: auditTools.join(',') })
      log(`[${t.id}] transcript="${transcript.slice(0, 50)}" tool=${toolVerdict} spoke=${spoke}(${voicedMs}ms) recorded=${recorded} reply="${reply.slice(0, 50)}"`)
      const ok = (toolVerdict.startsWith('FIRED') || toolVerdict.startsWith('DIFFERENT')) && recorded
      if (!ok) exitCode = 1
      await new Promise((r) => setTimeout(r, 1500))
    }

    // ── Cleanup: delete any "buy milk" task created during the run ──
    log('cleanup: removing created tasks…')
    let cleaned = 'nothing-to-clean'
    for (const b of restBases) {
      try {
        const after = await restActionItems(b, idToken)
        const beforeIds = new Set(itemsBefore.map((i) => i.id))
        const created = after.filter((i) => !beforeIds.has(i.id) && /buy milk/i.test(i.description))
        let del = 0
        for (const it of created) {
          if (!it.id) continue
          const r = await fetch(`${b.replace(/\/$/, '')}/v1/action-items/${it.id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${idToken}` } })
          if (r.ok) del++
        }
        cleaned = `base ${b}: created ${created.length}, deleted ${del}`
        break
      } catch (e) { cleaned = `REST err ${String(e).slice(0, 60)}` }
    }
    log(`cleanup: ${cleaned}`)
    results.push({ id: '— cleanup —', request: cleaned })
  } catch (e) {
    log(`ERROR: ${e?.stack || e}`)
    exitCode = 1
  } finally {
    try { if (app) await app.close() } catch { /* already closing */ }
    restoreAudioDefaults()
    try { fs.rmSync(ud, { recursive: true, force: true }) } catch { /* best-effort cleanup */ }
    // ── Report ──
    log('')
    log('════════════ VOICE TOOL GAUNTLET MATRIX ════════════')
    let pass = 0, groups = 0
    for (const r of results) {
      if (r.id.startsWith('—')) { log(`  ${r.id} ${r.request}`); continue }
      groups++
      const ok = (r.toolVerdict?.startsWith('FIRED') || r.toolVerdict?.startsWith('DIFFERENT')) && r.recorded
      if (ok) pass++
      log(`  ${r.id.padEnd(20)} transcribed=${r.transcribed} tool=${(r.toolVerdict || '-').padEnd(14)} spoke=${r.spoke}(${r.voicedMs}ms) recorded=${r.recorded}`)
      log(`      req="${r.request}" fired=${r.fired} transcript="${r.transcript?.slice(0, 60)}"`)
      log(`      reply="${r.reply}"  toolOut=${r.toolResults}`)
    }
    log('────────────────────────────────────────────────────')
    log(`  TALLY: ${pass}/${groups} requests fired a tool + recorded to kernel`)
    const gaps = results.filter((r) => !r.id.startsWith('—') && !((r.toolVerdict?.startsWith('FIRED') || r.toolVerdict?.startsWith('DIFFERENT')) && r.recorded))
    if (gaps.length) log(`  GAPS: ${gaps.map((g) => `${g.id}[tool=${g.toolVerdict},spoke=${g.spoke},rec=${g.recorded}]`).join(', ')}`)
    else log('  NO GAPS — every spoken request fired a tool + recorded.')
    log('════════════════════════════════════════════════════')
    try { fs.writeFileSync(path.join(root, 'voice-tool-gauntlet-report.json'), JSON.stringify({ runId: RUN_ID, uid, results, mainLog: mainLines.slice(-60) }, null, 2)) } catch { /* best-effort report write */ }
    try { fs.rmSync(tmp, { recursive: true, force: true }) } catch { /* best-effort cleanup */ }
    process.exit(results.some((r) => !r.id.startsWith('—')) ? exitCode : 2)
  }
}

main().catch((e) => { console.error(`[voice-tool] fatal: ${e?.stack || e}`); restoreAudioDefaults(); process.exit(1) })
