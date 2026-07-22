// PR8 LiveNotes E2E: launches the BUILT app (fake-auth shell), navigates to the
// two-column live view, drives a FIXTURE transcript through the real store +
// monitor, and asserts AI notes generate against a STUBBED Gemini proxy (never the
// real endpoint). Also exercises a user-typed note and the graceful
// generation-FAILURE path (proxy 500 → no crash, transcript intact, no new note).
//
// Screenshots → .playwright-mcp/pr8/ for an independent reviewer.
//
// Exit codes: 0 pass · 1 assertion failed · 2 skipped (build missing).
import { execFileSync } from 'node:child_process'
import { _electron as electron } from 'playwright'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const NO_BUILD = process.argv.includes('--no-build')
const shotDir = path.join(root, '.playwright-mcp', 'pr8')

function log(m) {
  console.log(`[livenotes-e2e] ${m}`)
}

async function findMainWindow(app) {
  for (let i = 0; i < 40; i++) {
    const page = app
      .windows()
      .find(
        (w) =>
          !/#\/(capture|overlay|bar|insight-toast|meeting-toast)/.test(w.url()) &&
          w.url() !== 'about:blank'
      )
    if (page) return page
    await new Promise((r) => setTimeout(r, 500))
  }
  return null
}

// Words that make one finalized transcript line of `n` words.
function words(prefix, n) {
  return Array.from({ length: n }, (_, i) => `${prefix}${i}`).join(' ')
}

async function main() {
  if (!NO_BUILD) {
    log('building app…')
    execFileSync('npx', ['electron-vite', 'build'], { stdio: 'inherit', cwd: root, shell: true })
  }
  const mainEntry = path.join(root, 'out', 'main', 'index.js')
  if (!fs.existsSync(mainEntry)) {
    log(`built main not found (${mainEntry}) — run without --no-build`)
    process.exit(2)
  }
  fs.mkdirSync(shotDir, { recursive: true })

  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'omi-livenotes-ud-'))
  const app = await electron.launch({
    args: [mainEntry, `--user-data-dir=${userDataDir}`],
    env: { ...process.env, OMI_E2E: '1', OMI_E2E_FAKE_AUTH: '1', OMI_AUTOMATION: '0' }
  })

  let exitCode = 0
  const fail = (msg) => {
    log(`FAIL: ${msg}`)
    exitCode = 1
  }

  // The note text the stubbed generator "returns".
  const aiNoteText = 'team aligned on the launch date'

  try {
    const page = await findMainWindow(app)
    if (!page) return fail('main window never appeared')
    await page.waitForLoadState('domcontentloaded')

    page.on('console', (m) => {
      const t = m.text()
      if (/live-notes|gemini|fallback/i.test(t)) log(`[renderer:${m.type()}] ${t}`)
    })
    page.on('pageerror', (e) => log(`[pageerror] ${e.message}`))

    // Tripwire: fail loudly if ANYTHING ever calls the real Gemini proxy — the LLM
    // boundary is stubbed in-renderer (below), so this must stay at zero hits.
    let routeHits = 0
    await page.route('**/v1/proxy/gemini/**', async (route) => {
      routeHits++
      return route.fulfill({ status: 500, body: 'must not hit the real proxy' })
    })

    // Wait for the E2E hook (attached at the App root once React mounts).
    let hooked = false
    for (let i = 0; i < 40 && !hooked; i++) {
      hooked = await page.evaluate(() => typeof globalThis.__omiLiveNotes?.pushSegment === 'function')
      if (!hooked) await new Promise((r) => setTimeout(r, 500))
    }
    if (!hooked) return fail('window.__omiLiveNotes hook never attached (OMI_E2E path broken)')

    // Navigate to the two-column live view.
    await page.evaluate(() => {
      window.location.hash = '#/conversations/live'
    })
    await page.waitForTimeout(800)
    await page.waitForSelector('text=Transcript', { timeout: 10000 })
    await page.waitForSelector('text=Notes', { timeout: 10000 })

    // Stub the LLM boundary in-renderer (never the real proxy).
    await page.evaluate((text) => globalThis.__omiLiveNotes.stubAi({ text }), aiNoteText)

    // Drive a fixture transcript > 50 words (one AI note), in a few lines.
    await page.evaluate(
      ([l1, l2]) => {
        const h = globalThis.__omiLiveNotes
        h.pushSegment({ id: 's1', speaker: 'Alex', text: l1 })
        h.pushSegment({ id: 's2', speaker: 'Sam', text: l2 })
      },
      [words('word', 30), words('term', 30)]
    )

    // Wait for the stubbed note to land.
    let got = 0
    for (let i = 0; i < 40 && got < 1; i++) {
      got = await page.evaluate(() => globalThis.__omiLiveNotes.noteCount())
      if (got < 1) await page.waitForTimeout(250)
    }
    if (got < 1) {
      const st = await page.evaluate(() => ({
        notes: globalThis.__omiLiveNotes.noteCount(),
        generating: globalThis.__omiLiveNotes.isGenerating(),
        hasCreateSession: typeof window.omi?.createTranscriptionSession,
        hasCreateNote: typeof window.omi?.createLiveNote
      }))
      log(`DIAG noteCount=${st.notes} generating=${st.generating} routeHits=${routeHits} createSession=${st.hasCreateSession} createNote=${st.hasCreateNote}`)
      return fail('AI note never generated from the fixture transcript')
    }
    log(`AI note generated (count=${got})`)
    await page.waitForTimeout(400)
    await page.screenshot({ path: path.join(shotDir, '01-two-column-ai-note.png') })

    // Add more speech → a second AI note (notes accumulating).
    await page.evaluate(
      ([l3]) => globalThis.__omiLiveNotes.pushSegment({ id: 's3', speaker: 'Alex', text: l3 }),
      [words('more', 55)]
    )
    for (let i = 0; i < 40; i++) {
      if ((await page.evaluate(() => globalThis.__omiLiveNotes.noteCount())) >= 2) break
      await page.waitForTimeout(250)
    }
    await page.waitForTimeout(400)
    await page.screenshot({ path: path.join(shotDir, '02-notes-accumulating.png') })

    // Type a manual note via the input field (separate row, pencil icon).
    const input = page.locator('input[placeholder="Add a note…"]')
    await input.fill('Follow up with design on the hero mock')
    await input.press('Enter')
    await page.waitForTimeout(500)
    const hasManual = await page.evaluate(() =>
      globalThis.__omiLiveNotes.getNotes().some((n) => !n.isAi)
    )
    if (!hasManual) return fail('user-typed note did not appear as a separate row')
    await page.screenshot({ path: path.join(shotDir, '03-user-typed-note.png') })

    // Failure path: generation throws → degrades gracefully (no crash, no new
    // note, transcript keeps rendering).
    await page.evaluate(() => globalThis.__omiLiveNotes.stubAi({ fail: true }))
    const before = await page.evaluate(() => globalThis.__omiLiveNotes.noteCount())
    await page.evaluate(
      ([l4]) => globalThis.__omiLiveNotes.pushSegment({ id: 's4', speaker: 'Sam', text: l4 }),
      [words('fail', 60)]
    )
    await page.waitForTimeout(2000)
    const after = await page.evaluate(() => globalThis.__omiLiveNotes.noteCount())
    const transcriptStillThere = await page.evaluate(
      () => !!document.querySelector('h2') && document.body.innerText.includes('Transcript')
    )
    if (after !== before) return fail(`a note was created despite the 500 (before=${before} after=${after})`)
    if (!transcriptStillThere) return fail('transcript pane vanished after a generation failure')
    log(`failure path graceful (notes unchanged at ${after}, transcript intact)`)
    await page.screenshot({ path: path.join(shotDir, '04-generation-failed-graceful.png') })

    if (routeHits !== 0) return fail(`the real Gemini proxy was hit ${routeHits}× (must be 0)`)
    log('PASS — screenshots in .playwright-mcp/pr8/')
  } catch (e) {
    fail(`threw: ${e?.stack || e}`)
  } finally {
    await app.close().catch(() => {})
  }
  process.exit(exitCode)
}

main()
