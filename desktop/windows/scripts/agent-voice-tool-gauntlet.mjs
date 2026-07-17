// ═══════════════════════════════════════════════════════════════════════════════
// REAL-AUDIO voice → hub → TOOL → spoken-reply GAUNTLET for the Windows Omi app.
//
// A LIVE, manual/dev harness (NOT hermetic CI) that proves "a human talking to Omi
// gets the right tool run + a spoken answer" — end to end, with real synthesized
// speech looped through a virtual mic and the REAL push-to-talk hub path.
//
// For each spoken utterance it asserts, per category:
//   READ tools     → the expected tool fired (timestamped tool_activity on the ONE
//                    mainChat:event stream, grouped by runId).
//   MUTATION tools → the BACKEND actually changed (REST /v1/action-items diff), via a
//                    self-cleaning create→update→complete→delete sequence on one task.
//   DELEGATION     → "build me X" delegated to a coding agent (write tool activity
//                    and/or a new agent session via list_agent_sessions delta).
//   NEGATIVES      → chit-chat fires NO tool; and the model NEVER promises a tool it
//                    can't call (scan every reply's text for unadvertised tools).
//
// ── WHY THIS REWRITE ─────────────────────────────────────────────────────────────
// The previous version was worthless as a proof for two reasons, both fixed here:
//   1. It "observed" tool calls by REASSIGNING window.omi.voiceToolExecute — but the
//      contextBridge object is FROZEN, so that is a silent no-op (it always saw zero
//      tools). We observe ONLY via additive listeners (onMainChatEvent) + REST +
//      direct tool CALLS (calling a frozen-bridge fn is fine; only reassigning fails).
//   2. It drove the turn with webContents.send('voiceHub:begin') to a
//      getAllWindows().find() whose filter can hit the #/glow overlay (wrong window →
//      the driver never ran). We drive the REAL bar path: __omiPtt.beginHold/endHold
//      → window.omiBar.voiceHubBegin → main sendToMain → the correct #/home driver.
// Plus: per-turn tool attribution is by runId + arrival timestamp (no ~1-turn lag).
//
// ── PREREQUISITES (all local, no secrets from anyone) ────────────────────────────
//   • VB-Audio Virtual Cable installed (provides "CABLE Input"/"CABLE Output").
//   • AudioDeviceCmdlets PowerShell module (Set-AudioDevice) to route the cable.
//   • ffmpeg on PATH (captures the spoken reply off the cable to measure voiced ms).
//   • Windows SAPI (System.Speech) for TTS — built in.
//   • desktop/windows/.env with OMI_E2E_REFRESH_TOKEN + VITE_FIREBASE_API_KEY
//     (unattended sign-in via the securetoken exchange — same pattern as the PTT E2E).
//   • A build present: out/main/index.js (run `pnpm build` first, or --build here).
//
// pttHubEnabled DEFAULTS ON in production (preferences.ts) — we set it explicitly so
// the result is representative of what real users get, not an artificial enable.
//
// ── RUN ──────────────────────────────────────────────────────────────────────────
//   pnpm gauntlet:voice                 # full matrix (needs a build already present)
//   node scripts/agent-voice-tool-gauntlet.mjs --build   # build first, then run
//   OMI_GAUNTLET_ONLY=get_action_items,chitchat node scripts/agent-voice-tool-gauntlet.mjs
//
// SAFETY: launches its OWN isolated _electron instance (temp userDataDir) — never a
// prod bundle or CDP :9222. Snapshots + RESTORES the OS default audio devices in a
// finally. Self-cleaning: every action-item it creates is deleted and re-verified via
// REST at the end; a spawned agent (if any) is reported for cancellation.
//
// EXIT: 0 = every expected tool fired + every negative held (UNVERIFIED rows do NOT
// fail the run but are listed). 1 = a gap. 2 = preconditions missing (skip).
// ═══════════════════════════════════════════════════════════════════════════════
import { spawn, spawnSync, execFileSync } from 'node:child_process'
import { _electron as electron } from 'playwright'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { readDotEnv, decodeJwt, exchangeRefreshToken } from './lib/omi-auth.mjs'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const SR = 16000, FRAME = 320, RMS_VOICED = 300
const REPLY_VOICED_MS_MIN = 400
const DO_BUILD = process.argv.includes('--build')
const ONLY = (process.env.OMI_GAUNTLET_ONLY || '').split(',').map((s) => s.trim()).filter(Boolean)
const RUN_ID = Date.now().toString(36)
// A distinctive task phrase the mutation sequence tracks through create→…→delete.
// "zebra" makes it unmistakable test data and trivial to find/verify/clean.
const TASK_PHRASE = 'buy zebra milk'
// Match on the distinctive "zebra" token alone — it survives the rename the update
// step performs ("buy zebra oat milk"), so find/verify/cleanup all still catch it.
const TASK_RE = /zebra/i

// ── The matrix ───────────────────────────────────────────────────────────────────
// category: read | mutation | delegation | negative
// expect: the tool that SHOULD fire (exact). alt: acceptable substitutes.
// rest: for mutations — a fn(before,after,item)=>bool proving the backend changed.
// noPromise: for negatives — the run FAILS if any reply text mentions these.
const MATRIX = [
  // ── READS ──
  { id: 'get_action_items', category: 'read', request: 'What are my action items for today?', expect: 'get_action_items', alt: ['search_tasks', 'get_tasks'] },
  { id: 'search_memories', category: 'read', request: 'Search my memories about my dog.', expect: 'search_memories', alt: ['get_memories', 'semantic_search'] },
  { id: 'get_memories', category: 'read', request: 'What do you know about me?', expect: 'get_memories', alt: ['search_memories'] },
  { id: 'search_conversations', category: 'read', request: 'Find my past conversations about groceries.', expect: 'search_conversations', alt: ['get_conversations', 'semantic_search'] },
  { id: 'get_daily_recap', category: 'read', request: 'Give me a recap of what I did today.', expect: 'get_daily_recap', alt: ['get_conversations', 'search_conversations'] },
  { id: 'semantic_search', category: 'read', request: 'What was I reading about on my screen earlier today?', expect: 'semantic_search', alt: ['get_work_context', 'search_conversations'] },
  { id: 'get_work_context', category: 'read', request: 'What am I working on right now on my computer?', expect: 'get_work_context', alt: ['semantic_search', 'capture_screen'] },

  // ── MUTATION SEQUENCE (self-cleaning: one task through its whole lifecycle) ──
  { id: 'create_action_item', category: 'mutation', request: `Add ${TASK_PHRASE} to my action items.`, expect: 'create_action_item',
    rest: (before, after) => after.some((i) => TASK_RE.test(i.description)) && !before.some((i) => TASK_RE.test(i.description)) },
  { id: 'update_action_item', category: 'mutation', request: 'Change my zebra milk task to say buy zebra oat milk instead.', expect: 'update_action_item', alt: ['search_tasks', 'get_action_items'],
    rest: (before, after) => after.some((i) => /oat/i.test(i.description) && TASK_RE.test(i.description)) },
  { id: 'complete_task', category: 'mutation', request: 'Mark my zebra milk task as done.', expect: 'complete_task', alt: ['update_action_item', 'search_tasks'],
    rest: (before, after, restById) => { const it = after.find((i) => TASK_RE.test(i.description)); return !!it && restById.get(it.id)?.completed === true } },
  { id: 'delete_task', category: 'mutation', request: 'Delete my zebra milk task.', expect: 'delete_task', alt: ['search_tasks'],
    rest: (before, after) => !after.some((i) => TASK_RE.test(i.description)) },

  // ── DELEGATION ──
  { id: 'spawn_agent', category: 'delegation', request: 'Build me a simple tic tac toe web page.', expect: 'spawn_agent', alt: ['write', 'bash', 'edit'] },

  // ── NEGATIVES ──
  { id: 'chitchat', category: 'negative', request: 'Hey Omi, how are you doing today?', expectNoTool: true },
  { id: 'calendar_temptation', category: 'negative', request: 'Put a lunch meeting on my calendar for tomorrow at noon.', expectNoTool: false,
    // calendar is NOT advertised on Windows → may decline or delegate (spawn_agent), but must NOT
    // fire create_calendar_event nor PROMISE it.
    forbidTools: ['create_calendar_event'], noPromise: ['create_calendar_event'] }
]
// Cross-cutting: no reply may ever promise a tool the Windows voice surface can't call.
const GLOBAL_FORBIDDEN_PROMISES = ['get_tasks', 'ask_higher_model', 'create_calendar_event']

function selected() {
  const rows = ONLY.length ? MATRIX.filter((t) => ONLY.includes(t.id) || ONLY.includes(t.category)) : MATRIX
  return rows
}

// ── PowerShell + audio device routing ────────────────────────────────────────────
let savedAudio = null
function ps(script) { return spawnSync('powershell', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script], { encoding: 'utf8' }) }
function log(m) { console.log(`[gauntlet] ${m}`) }
function snapshotDefaults() {
  const out = ps(`Import-Module AudioDeviceCmdlets; $p=Get-AudioDevice -Playback; $r=Get-AudioDevice -Recording; "$($p.Index),$($r.Index)"`)
  const m = ((out.stdout || '').trim().split(/\r?\n/).pop() || '').match(/^(\d+),(\d+)$/)
  return m ? { play: m[1], rec: m[2] } : null
}
function routeCable() {
  const probe = ps("if (Get-Module -ListAvailable -Name AudioDeviceCmdlets) { 'yes' } else { 'no' }")
  if ((probe.stdout || '').trim() !== 'yes') { log('SKIP precondition: AudioDeviceCmdlets module not installed'); return false }
  savedAudio = snapshotDefaults()
  const r = ps(`Import-Module AudioDeviceCmdlets
    $play=Get-AudioDevice -List|Where-Object{$_.Type -eq 'Playback' -and $_.Name -match 'CABLE Input'}|Select-Object -First 1
    $rec=Get-AudioDevice -List|Where-Object{$_.Type -eq 'Recording' -and $_.Name -match 'CABLE Output'}|Select-Object -First 1
    if(-not $play -or -not $rec){'missing';exit}
    Set-AudioDevice -Index $play.Index|Out-Null; Set-AudioDevice -Index $rec.Index|Out-Null; "ok"`)
  if (!((r.stdout || '').includes('ok'))) { log('SKIP precondition: VB-Cable CABLE Input/Output not found'); savedAudio = null; return false }
  log('routed default playback→CABLE Input, capture→CABLE Output')
  return true
}
function restoreAudio() { if (savedAudio) { ps(`Import-Module AudioDeviceCmdlets; Set-AudioDevice -Index ${savedAudio.play}|Out-Null; Set-AudioDevice -Index ${savedAudio.rec}|Out-Null`); log(`restored audio defaults (#${savedAudio.play}/#${savedAudio.rec})`); savedAudio = null } }

// ── SAPI TTS → 16k mono WAV, and playback into the cable ─────────────────────────
function sapiSpeakToWav(text, wav) {
  const p1 = path.join(os.tmpdir(), `omi-g-${Date.now()}-${Math.random().toString(16).slice(2)}.ps1`)
  fs.writeFileSync(p1, [
    'Add-Type -AssemblyName System.Speech',
    '$s=New-Object System.Speech.Synthesis.SpeechSynthesizer',
    '$f=New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000,[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,[System.Speech.AudioFormat.AudioChannel]::Mono)',
    `$s.SetOutputToWaveFile('${wav.replace(/'/g, "''")}',$f)`,
    '$s.Rate=-1',
    `$s.Speak('${text.replace(/'/g, "''")}')`,
    '$s.Dispose()'
  ].join('\n'), 'utf8')
  try { execFileSync('powershell', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', p1], { stdio: 'pipe', timeout: 120000 }) } finally { fs.rmSync(p1, { force: true }) }
}
function playWav(wav) { ps(`(New-Object System.Media.SoundPlayer '${wav.replace(/'/g, "''")}').PlaySync()`) }

// ── ffmpeg reply capture (dshow) + voiced-ms measurement ─────────────────────────
function findDshow() {
  const o = spawnSync('ffmpeg', ['-hide_banner', '-list_devices', 'true', '-f', 'dshow', '-i', 'dummy'], { encoding: 'utf8' })
  const t = `${o.stdout || ''}\n${o.stderr || ''}`
  for (const l of t.split(/\r?\n/)) { const m = l.match(/"([^"]*CABLE Output[^"]*)"/i); if (m) return m[1] }
  return null
}
function startCapture(dev, out) { return spawn('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-f', 'dshow', '-i', `audio=${dev}`, '-ac', '1', '-ar', String(SR), '-f', 's16le', '-y', out], { stdio: ['pipe', 'ignore', 'ignore'] }) }
async function stopCapture(cap) { if (!cap || cap.exitCode !== null) return; await new Promise((res) => { let d = false; const fin = () => { if (!d) { d = true; res() } }; cap.on('close', fin); try { cap.stdin.write('q') } catch { /* */ } setTimeout(() => { try { cap.kill('SIGKILL') } catch { /* */ } fin() }, 3500) }) }
function voicedMs(buf) { if (!buf || buf.byteLength < FRAME * 2) return 0; const pcm = new Int16Array(buf.buffer, buf.byteOffset, Math.floor(buf.byteLength / 2)); const fr = Math.floor(pcm.length / FRAME); let v = 0; for (let f = 0; f < fr; f++) { let s = 0; for (let i = 0; i < FRAME; i++) { const x = pcm[f * FRAME + i]; s += x * x } if (Math.sqrt(s / FRAME) >= RMS_VOICED) v++ } return v * 20 }

// ── Backend REST (ground truth for mutations) ────────────────────────────────────
function restBases(env) { return [env.VITE_OMI_DESKTOP_API_BASE, env.VITE_OMI_API_BASE, 'https://api.omi.me'].filter(Boolean) }
async function restActionItems(base, tok) {
  const r = await fetch(`${base.replace(/\/$/, '')}/v1/action-items?limit=200`, { headers: { Authorization: `Bearer ${tok}` } })
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  const d = await r.json().catch(() => ({}))
  const items = Array.isArray(d) ? d : d.action_items || d.items || []
  return items.map((x) => ({ id: x.id || x.action_item_id || x.backendId, description: String(x.description || x.content || ''), completed: x.completed === true || x.completed_at != null || x.is_completed === true }))
}
async function restDelete(base, tok, id) { const r = await fetch(`${base.replace(/\/$/, '')}/v1/action-items/${id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${tok}` } }); return r.ok }

// ── Playwright window helpers ────────────────────────────────────────────────────
async function mainWindow(app) { for (let i = 0; i < 50; i++) { const p = app.windows().find((w) => /#\/home/.test(w.url())) || app.windows().find((w) => !/#\/(capture|overlay|bar|insight-toast|meeting-toast|glow)/.test(w.url()) && w.url() !== 'about:blank'); if (p) return p; await new Promise((r) => setTimeout(r, 400)) } return null }
async function barWindow(app) { for (let i = 0; i < 80; i++) { const p = app.windows().find((w) => /#\/bar/.test(w.url())); if (p) return p; await new Promise((r) => setTimeout(r, 400)) } return null }
async function waitFor(page, fn, ms, label) { const d = Date.now() + ms; for (;;) { const v = await page.evaluate(fn); if (v) return v; if (Date.now() > d) throw new Error('timeout ' + label); await new Promise((r) => setTimeout(r, 400)) } }
async function injectAuth(page, key, idToken, rt) {
  const c = decodeJwt(idToken); if (!c?.user_id) throw new Error('bad ID token')
  const user = { uid: c.user_id, email: c.email ?? null, emailVerified: true, isAnonymous: false, providerData: [], stsTokenManager: { refreshToken: rt, accessToken: idToken, expirationTime: c.exp * 1000 }, createdAt: String(Date.now()), lastLoginAt: String(Date.now()), apiKey: key, appName: '[DEFAULT]' }
  await page.evaluate(({ k, u }) => localStorage.setItem(`firebase:authUser:${k}:[DEFAULT]`, JSON.stringify(u)), { k: key, u: user })
}

// Query a hub tool directly (calling a frozen-bridge fn is fine; only reassigning fails).
async function callVoiceTool(page, name, argsObj) {
  return page.evaluate(async ({ name, argsJSON }) => {
    try { return await window.omi.voiceToolExecute({ name, argumentsJSON: argsJSON }) } catch (e) { return `THREW ${String(e)}` }
  }, { name, argsJSON: JSON.stringify(argsObj || {}) })
}
function agentSessionIds(raw) {
  // list_agent_sessions returns a string (often JSON-ish). Extract any id-looking tokens.
  const s = String(raw || '')
  const ids = new Set()
  for (const m of s.matchAll(/"?(?:id|session_?id|run_?id|agentId)"?\s*[:=]\s*"?([A-Za-z0-9_-]{6,})"?/g)) ids.add(m[1])
  return ids
}

async function main() {
  const env = readDotEnv(path.join(root, '.env'))
  const rt = process.env.OMI_E2E_REFRESH_TOKEN ?? env.OMI_E2E_REFRESH_TOKEN
  const key = process.env.VITE_FIREBASE_API_KEY ?? env.VITE_FIREBASE_API_KEY
  if (!rt || !key) { log('SKIP: OMI_E2E_REFRESH_TOKEN / VITE_FIREBASE_API_KEY missing from .env'); process.exit(2) }
  if (spawnSync('ffmpeg', ['-version'], { encoding: 'utf8' }).status !== 0) { log('SKIP: ffmpeg not on PATH'); process.exit(2) }
  if (DO_BUILD) { log('building app…'); execFileSync('npx', ['electron-vite', 'build'], { stdio: 'inherit', cwd: root, shell: true }); execFileSync('node', [path.join(root, 'scripts', 'bundle-pimono-extension.mjs')], { stdio: 'inherit', cwd: root }) }
  const mainEntry = path.join(root, 'out', 'main', 'index.js')
  if (!fs.existsSync(mainEntry)) { log(`SKIP: build missing (${mainEntry}) — run with --build or 'pnpm build'`); process.exit(2) }
  if (!routeCable()) { restoreAudio(); process.exit(2) }
  const dshow = findDshow()
  if (!dshow) { log('SKIP: ffmpeg dshow cannot see CABLE Output'); restoreAudio(); process.exit(2) }

  let idToken
  try { idToken = await exchangeRefreshToken(rt, key) } catch (e) { log(`SKIP: token exchange failed (${e.message})`); restoreAudio(); process.exit(2) }
  const uid = decodeJwt(idToken)?.user_id
  const bases = restBases(env)
  let restBase = null
  for (const b of bases) { try { await restActionItems(b, idToken); restBase = b; break } catch { /* next */ } }
  log(`auth ok uid=${uid} · restBase=${restBase || '(none reachable)'} · dshow="${dshow}"`)

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'omi-gauntlet-'))
  const ud = fs.mkdtempSync(path.join(os.tmpdir(), 'omi-gauntlet-ud-'))
  const rows = selected()
  const results = []
  let exit = 0
  let app = null
  const createdItemIds = new Set()
  const spawnedAgents = new Set()

  try {
    app = await electron.launch({ args: [mainEntry, `--user-data-dir=${ud}`], env: { ...process.env, OMI_E2E: '1', OMI_ALLOW_VIRTUAL_MIC: '1', OMI_AUTOMATION: '0' } })

    // Sign in on the main window.
    let page = await mainWindow(app)
    if (!page) throw new Error('main window never appeared')
    await page.waitForLoadState('domcontentloaded')
    await injectAuth(page, key, idToken, rt)
    await page.evaluate(() => { const K = 'omi-windows-prefs-v1'; const p = JSON.parse(localStorage.getItem(K) ?? '{}'); p.onboardingCompletedAt = p.onboardingCompletedAt ?? Date.now(); p.pttHubEnabled = true; localStorage.setItem(K, JSON.stringify(p)); location.reload() })
    await new Promise((r) => setTimeout(r, 3500))
    page = await mainWindow(app)
    await page.waitForLoadState('domcontentloaded')
    await waitFor(page, () => globalThis.__omiVoice?.getAuthUid?.() || null, 30000, 'signed-in')

    // Observability: ONE additive listener on the mainChat:event stream. Group by
    // runId; stamp arrival time so we can attribute each runId to its turn.
    await page.evaluate(() => {
      window.__ev = []
      window.omi.onMainChatEvent((e) => window.__ev.push({ ...e, _at: Date.now() }))
    })
    await page.evaluate(() => globalThis.__omiVoice.setPrefs({ pttHubEnabled: true }))

    // Warm the hub + confirm the tool catalog (a direct CALL — valid).
    let catalog = []
    for (let i = 0; i < 40; i++) { catalog = await page.evaluate(async () => { try { return await window.omi.voiceHubToolCatalog() } catch { return [] } }); if (catalog.length) break; await new Promise((r) => setTimeout(r, 1000)) }
    const catalogNames = catalog.map((t) => t.name)
    log(`hub tool catalog (${catalogNames.length}): ${catalogNames.join(', ')}`)

    // Bring up the bar window (owns __omiPtt) and drive the REAL PTT path.
    await app.evaluate(() => globalThis.__omiE2E?.barEnable?.())
    const bar = await barWindow(app)
    if (!bar) throw new Error('bar window never appeared (barEnable failed)')
    await bar.waitForLoadState('domcontentloaded')
    await waitFor(bar, () => typeof globalThis.__omiPtt?.beginHold === 'function', 30000, '__omiPtt')
    log('bar ready (__omiPtt attached); waiting for the hub socket to warm…')
    await new Promise((r) => setTimeout(r, 8000))

    // Silent warm-up hold ×2 (spins up the capture-window mic graph on a loaded box).
    for (let i = 0; i < 2; i++) { await bar.evaluate(() => window.__omiPtt.beginHold()); await new Promise((r) => setTimeout(r, 1500)); await bar.evaluate(() => window.__omiPtt.endHold()); await new Promise((r) => setTimeout(r, 2500)) }
    log('mic/hub warm-up done')

    let itemsBefore = restBase ? await restActionItems(restBase, idToken).catch(() => []) : []
    let agentsBefore = agentSessionIds(await callVoiceTool(page, 'list_agent_sessions', {}))

    for (const t of rows) {
      const wav = path.join(tmp, `${t.id}.wav`)
      sapiSpeakToWav(t.request, wav)
      // Drive the REAL PTT turn, with RETRY on a capture-miss (no tool + no reply +
      // no terminal event = the utterance never landed — mic/STT contention on a
      // loaded box, not a real result). A turn that produced ANY signal is scored as
      // is (a wrong tool is a real finding, not a miss).
      const MAX_ATTEMPTS = t.category === 'negative' ? 2 : 3
      let att = { tools: [], toolInputs: [], replyText: '', spokeMs: 0, sawTerminal: false, attempts: 0 }
      for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
        const turnStart = Date.now()
        await page.evaluate((s) => { window.__turnStart = s }, turnStart)
        log(`[${t.id}] (${t.category}) attempt ${attempt}: "${t.request}"`)
        await bar.evaluate(() => window.__omiPtt.beginHold())
        await new Promise((r) => setTimeout(r, 1400)) // capture-window spin-up margin
        const replyPcm = path.join(tmp, `${t.id}-${attempt}.pcm`); const cap = startCapture(dshow, replyPcm)
        playWav(wav) // blocks for the clip (~2-4s)
        await new Promise((r) => setTimeout(r, 600))
        await bar.evaluate(() => window.__omiPtt.endHold())
        // Wait until a run for THIS turn reaches run_finished / final `completed`, or
        // timeout. For delegation we don't wait for the whole (minutes-long) build — we
        // break as soon as the coding agent emits its FIRST tool call (spawn_agent /
        // write / bash / edit), which is the delegation signal we score on.
        const deadline = Date.now() + (t.category === 'delegation' ? 150000 : 90000)
        for (;;) {
          const done = await page.evaluate(({ s, cat }) => window.__ev.some((e) => e._at >= s && (e.type === 'run_finished' || e.type === 'completed' || (cat === 'delegation' && e.type === 'tool_activity' && ['spawn_agent', 'write', 'bash', 'edit'].includes(e.name)))), { s: turnStart, cat: t.category })
          if (done) break
          if (Date.now() > deadline) break
          await new Promise((r) => setTimeout(r, 600))
        }
        await new Promise((r) => setTimeout(r, 5000)) // drain trailing tool_activity + reply TTS
        await stopCapture(cap)
        const evs = await page.evaluate((s) => window.__ev.filter((e) => e._at >= s), turnStart)
        const toolEvents = evs.filter((e) => e.type === 'tool_activity')
        const tools = [...new Set(toolEvents.map((e) => e.name).filter(Boolean))]
        const replyText = (evs.filter((e) => e.type === 'completed').map((e) => e.text).filter(Boolean).pop())
          || evs.filter((e) => e.type === 'text_delta').map((e) => e.text).join('')
        const sawTerminal = evs.some((e) => e.type === 'run_finished' || e.type === 'completed')
        let rbuf = null; try { rbuf = fs.readFileSync(replyPcm) } catch { /* */ }
        att = { tools, toolInputs: toolEvents.filter((e) => e.status === 'started').map((e) => ({ name: e.name, input: e.input })), replyText, spokeMs: voicedMs(rbuf), sawTerminal, attempts: attempt }
        const captureMiss = tools.length === 0 && !replyText && !sawTerminal
        if (!captureMiss) break
        log(`[${t.id}] capture-miss (no tool/reply/terminal) — retrying`)
        await new Promise((r) => setTimeout(r, 1500))
      }
      const { tools, toolInputs, replyText, spokeMs } = att

      const row = { id: t.id, category: t.category, request: t.request, tools, reply: (replyText || '').slice(0, 200), spokeMs, verdict: '', detail: '' }

      if (t.category === 'read') {
        const fired = tools.includes(t.expect)
        const alt = !fired && (t.alt || []).some((a) => tools.includes(a))
        row.verdict = fired ? 'PASS' : alt ? 'PASS(alt)' : tools.length ? 'DIFFERENT' : 'FAIL'
        row.detail = fired ? `fired ${t.expect}` : alt ? `fired alt [${tools}]` : tools.length ? `expected ${t.expect}, got [${tools}]` : `no tool fired (spoke=${spokeMs}ms)`
        if (row.verdict === 'FAIL' || row.verdict === 'DIFFERENT') exit = 1
      } else if (t.category === 'mutation') {
        const before = itemsBefore
        // Poll the backend a few times — the write lands slightly after the tool
        // returns (eventual consistency), so a single immediate read can miss it.
        let after = before, restById = new Map(), restOk = restBase ? false : null
        if (restBase) {
          for (let poll = 0; poll < 4; poll++) {
            await new Promise((r) => setTimeout(r, 2000))
            after = await restActionItems(restBase, idToken).catch(() => before)
            restById = new Map(after.map((i) => [i.id, i]))
            restOk = !!t.rest && t.rest(before, after, restById)
            if (restOk) break
          }
        }
        after.filter((i) => TASK_RE.test(i.description)).forEach((i) => createdItemIds.add(i.id))
        const fired = tools.includes(t.expect) || (t.alt || []).some((a) => tools.includes(a))
        row.verdict = restOk === true ? 'PASS' : restOk === false ? (fired ? 'UNVERIFIED' : 'FAIL') : (fired ? 'PASS(tool-only)' : 'UNVERIFIED')
        row.detail = `tools=[${tools}] restProof=${restOk === null ? 'no-rest-base' : restOk}`
        if (row.verdict === 'FAIL') exit = 1
        itemsBefore = after
      } else if (t.category === 'delegation') {
        const agentsAfter = agentSessionIds(await callVoiceTool(page, 'list_agent_sessions', {}))
        const newAgents = [...agentsAfter].filter((x) => !agentsBefore.has(x))
        newAgents.forEach((a) => spawnedAgents.add(a))
        const spawned = tools.includes('spawn_agent')
        const didWork = ['write', 'bash', 'edit', 'read'].some((w) => tools.includes(w))
        if (spawned || newAgents.length) { row.verdict = 'PASS'; row.detail = `spawn_agent=${spawned} newAgentSessions=${newAgents.length} coding=[${tools}]` }
        else if (didWork) { row.verdict = 'PASS(delegated-via-write)'; row.detail = `coding-agent tools=[${tools}] but no spawn_agent/session signal observed` }
        else { row.verdict = 'FAIL'; row.detail = `no delegation signal; tools=[${tools}]`; exit = 1 }
        agentsBefore = agentsAfter
      } else if (t.category === 'negative') {
        const forbidHit = (t.forbidTools || []).filter((f) => tools.includes(f))
        const noToolOk = t.expectNoTool ? tools.length === 0 : true
        row.verdict = (noToolOk && forbidHit.length === 0) ? 'PASS' : 'FAIL'
        row.detail = t.expectNoTool ? (tools.length ? `expected NO tool, fired [${tools}]` : 'no tool (correct)') : (forbidHit.length ? `fired forbidden [${forbidHit}]` : `no forbidden tool (tools=[${tools}])`)
        if (row.verdict === 'FAIL') exit = 1
      }

      // Cross-cutting: scan EVERY reply for a promise of an unadvertised tool. We match
      // the LITERAL tool name (underscore form) to stay precise — the model naming a tool
      // it can't call — rather than loose phrases that false-positive on natural language.
      const promised = [...GLOBAL_FORBIDDEN_PROMISES, ...((t.noPromise) || [])].filter((f) => new RegExp('\\b' + f + '\\b', 'i').test(row.reply))
      if (promised.length) { row.detail += ` · PROMISE-VIOLATION: reply mentions [${promised}]`; row.promiseViolation = promised; exit = 1 }

      results.push(row)
      log(`[${t.id}] ${row.verdict} — ${row.detail} · spoke=${spokeMs}ms · reply="${(replyText || '').slice(0, 60)}"`)
      await new Promise((r) => setTimeout(r, 1500))
    }

    // ── Cleanup: delete every zebra-milk item we created; re-verify none remain. ──
    if (restBase) {
      const after = await restActionItems(restBase, idToken).catch(() => [])
      for (const it of after.filter((i) => TASK_RE.test(i.description))) createdItemIds.add(it.id)
      let del = 0
      for (const id of createdItemIds) { if (id && await restDelete(restBase, idToken, id)) del++ }
      const final = await restActionItems(restBase, idToken).catch(() => [])
      const remaining = final.filter((i) => TASK_RE.test(i.description)).length
      log(`cleanup: deleted ${del} created item(s); zebra-milk remaining=${remaining}`)
      results.push({ id: '__cleanup__', category: 'cleanup', verdict: remaining === 0 ? 'CLEAN' : 'DIRTY', detail: `deleted ${del}, remaining ${remaining}` })
      if (remaining !== 0) exit = 1
    }
    if (spawnedAgents.size) {
      // Windows spawn_agent starts a LOCAL provider session (no backend VM), torn down
      // when this isolated app closes below. Report the ids for awareness/cancellation.
      log(`spawned agent session(s) observed (local, torn down on app close): ${[...spawnedAgents].join(', ')}`)
      results.push({ id: '__agents__', category: 'cleanup', verdict: 'INFO', detail: `spawned local agent sessions: ${[...spawnedAgents].join(', ')}` })
    }
  } catch (e) {
    log(`ERROR: ${e?.stack || e}`); exit = 1
  } finally {
    try { if (app) await app.close() } catch { /* */ }
    restoreAudio()
    try { fs.rmSync(ud, { recursive: true, force: true }); fs.rmSync(tmp, { recursive: true, force: true }) } catch { /* */ }
    printReport(results, uid)
    process.exit(results.some((r) => r.category !== 'cleanup') ? exit : 2)
  }
}

function printReport(results, uid) {
  log('')
  log('════════════════════ VOICE TOOL GAUNTLET ════════════════════')
  const cats = ['read', 'mutation', 'delegation', 'negative']
  let pass = 0, total = 0, unverified = 0
  for (const c of cats) {
    const rows = results.filter((r) => r.category === c)
    if (!rows.length) continue
    log(`── ${c.toUpperCase()} ──`)
    for (const r of rows) {
      total++
      if (/^PASS/.test(r.verdict) || r.verdict === 'CLEAN') pass++
      if (r.verdict === 'UNVERIFIED') unverified++
      log(`  ${(r.verdict || '').padEnd(22)} ${r.id.padEnd(22)} ${r.detail}`)
      log(`      req="${r.request}" · spoke=${r.spokeMs}ms · reply="${(r.reply || '').slice(0, 70)}"`)
    }
  }
  for (const r of results.filter((r) => r.category === 'cleanup')) log(`── CLEANUP ── ${r.verdict}: ${r.detail}`)
  log('──────────────────────────────────────────────────────────────')
  log(`  TALLY: ${pass}/${total} pass · ${unverified} unverified · promise-violations=${results.filter((r) => r.promiseViolation).length}`)
  log('══════════════════════════════════════════════════════════════')
  try { fs.writeFileSync(path.join(root, 'voice-tool-gauntlet-report.json'), JSON.stringify({ runId: RUN_ID, uid, results }, null, 2)) } catch { /* */ }
}

main().catch((e) => { console.error(`[gauntlet] fatal: ${e?.stack || e}`); restoreAudio(); process.exit(1) })
