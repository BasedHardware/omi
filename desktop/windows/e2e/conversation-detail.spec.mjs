/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// ConversationDetail (PR6) E2E: drives the REAL built app (out/main/index.js) via
// Playwright's _electron and exercises the redesigned detail page against
// INTERCEPTED backend responses — page.route() fulfills every /v1/** call from
// fixtures, so this never touches a real backend or real account data.
//
// A catch-all /v1/** route is registered FIRST and aborts anything unmatched
// (Playwright matches routes in reverse registration order, so the specific
// handlers below still win). That is the guard that makes "no live traffic"
// structural rather than a promise.
//
// Captures the screenshot set to .playwright-mcp/pr6/ for an INDEPENDENT
// reviewer. Build first, then run: `pnpm test:e2e:conv-detail`.
import { describe, test } from 'node:test'
import assert from 'node:assert/strict'
import { _electron as electron } from 'playwright'
import { fileURLToPath } from 'node:url'
import { mkdtempSync, rmSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const mainEntry = path.join(root, 'out', 'main', 'index.js')
const shotsDir = path.join(root, '.playwright-mcp', 'pr6')

const baseEnv = {
  ...process.env,
  OMI_E2E: '1',
  OMI_E2E_FAKE_AUTH: '1',
  OMI_AUTOMATION: '0',
  OMI_SKIP_TUNNEL: '1'
}

const SECONDARY_HASHES = ['#/bar', '#/insight', '#/notch']
const isSecondary = (url) => SECONDARY_HASHES.some((h) => url.includes(h))

// ── Fixtures ────────────────────────────────────────────────────────────────
const PEOPLE = [{ id: 'p1', name: 'Nikita' }]
const FOLDERS = [{ id: 'f1', name: 'Work', color: null, icon: null, order: 0 }]

// Multi-speaker, including the user, plus a translated segment. Every segment has
// a REAL backend id (s0..s4) so speaker naming is addressable here. The unsynced
// (no-id) path — the Mac "#index:N" silent no-op bug — is covered by the unit
// tests in lib/conversations/speakers.test.ts.
const CONVERSATION = {
  id: 'e2e-conv-1',
  created_at: '2026-07-01T14:30:00Z',
  started_at: '2026-07-01T14:30:00Z',
  finished_at: '2026-07-01T14:35:30Z',
  status: 'completed',
  source: 'desktop',
  folder_id: null,
  starred: false,
  structured: {
    title: 'Roadmap sync',
    emoji: '🗺️',
    category: 'work',
    overview:
      'The team aligned on the **Q3 roadmap**. Two workstreams were confirmed:\n\n- Ship the Windows parity release\n- Start the speaker-naming rework\n\nRisks around the transcription backlog were raised and deferred to next week.',
    action_items: [
      { description: 'Draft the parity release notes', completed: false },
      { description: 'Book the transcription review', completed: true }
    ]
  },
  apps_results: [
    {
      app_id: 'app-summarizer',
      content:
        'This conversation covered roadmap planning with a focus on the Windows parity release. The team spent most of the time on sequencing, and agreed the speaker-naming rework should follow the parity work rather than run alongside it. A secondary thread covered the transcription backlog, which was explicitly deferred. Follow-ups were assigned to two owners.'
    }
  ],
  transcript_segments: [
    {
      id: 's0',
      text: 'Okay, let us start with the roadmap for Q3.',
      speaker: 'SPEAKER_00',
      speaker_id: 0,
      is_user: false,
      person_id: 'p1',
      start: 0,
      end: 4
    },
    {
      id: 's1',
      text: 'Sounds good. I think the parity release has to come first.',
      speaker: 'SPEAKER_01',
      speaker_id: 1,
      is_user: true,
      start: 5,
      end: 9
    },
    {
      id: 's2',
      text: 'Agreed — the speaker-naming rework can follow it.',
      speaker: 'SPEAKER_00',
      speaker_id: 0,
      is_user: false,
      person_id: 'p1',
      start: 10,
      end: 14
    },
    {
      id: 's3',
      text: 'Y el backlog de transcripcion sigue creciendo.',
      speaker: 'SPEAKER_02',
      speaker_id: 2,
      is_user: false,
      start: 15,
      end: 19,
      translations: [{ lang: 'en', text: 'And the transcription backlog keeps growing.' }]
    },
    {
      id: 's4',
      text: 'Let us defer that to next week.',
      speaker: 'SPEAKER_01',
      speaker_id: 1,
      is_user: true,
      start: 20,
      end: 23
    }
  ]
}

const PROCESSING = {
  id: 'e2e-conv-processing',
  created_at: '2026-07-01T16:00:00Z',
  started_at: '2026-07-01T16:00:00Z',
  finished_at: null,
  status: 'processing',
  deferred: true,
  source: 'desktop',
  structured: { title: 'Standup', emoji: '🎙️', action_items: [] },
  transcript_segments: [
    {
      id: 'p0',
      text: 'Quick standup before the sync.',
      speaker: 'SPEAKER_00',
      speaker_id: 0,
      is_user: false,
      start: 0,
      end: 3
    }
  ]
}

const json = (route, body) =>
  route.fulfill({
    status: 200,
    contentType: 'application/json',
    headers: { 'access-control-allow-origin': '*' },
    body: JSON.stringify(body)
  })

/** Every /v1/** call is served from fixtures; anything unexpected is aborted and
 *  recorded, so a stray live call fails the test instead of leaking out. */
async function stubBackend(page) {
  const unexpected = []

  // Registered first => lowest precedence. Nothing escapes to the network.
  await page.route('**/v1/**', (route) => {
    unexpected.push(route.request().method() + ' ' + route.request().url())
    return route.abort()
  })

  await page.route('**/v1/users/people**', (route) => {
    if (route.request().method() === 'POST') {
      return json(route, { id: 'p2', name: 'Chris' })
    }
    return json(route, PEOPLE)
  })
  await page.route('**/v1/folders**', (route) => json(route, FOLDERS))
  await page.route('**/v1/apps**', (route) => json(route, []))
  await page.route('**/v1/conversations/e2e-conv-1/segments/assign-bulk**', (route) =>
    json(route, CONVERSATION)
  )
  await page.route('**/v1/conversations/e2e-conv-1/title**', (route) =>
    json(route, { status: 'Ok' })
  )
  await page.route('**/v1/conversations/e2e-conv-1/action-items**', (route) =>
    json(route, { status: 'Ok' })
  )
  await page.route('**/v1/conversations/e2e-conv-1**', (route) => json(route, CONVERSATION))
  await page.route('**/v1/conversations/e2e-conv-processing**', (route) => json(route, PROCESSING))

  return unexpected
}

async function launch() {
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-convdetail-e2e-'))
  const app = await electron.launch({
    args: [mainEntry, `--user-data-dir=${dir}`],
    env: baseEnv
  })
  const cleanup = async () => {
    try {
      await app.close()
    } catch {
      /* already closed */
    }
    try {
      rmSync(dir, { recursive: true, force: true })
    } catch {
      /* best-effort */
    }
  }
  return { app, cleanup }
}

async function mainPage(app) {
  for (let i = 0; i < 120; i++) {
    const page = (await app.windows()).find((w) => !isSecondary(w.url()))
    if (page) {
      const ready = await page
        .evaluate(() => (document.querySelector('#root')?.childElementCount ?? 0) > 0)
        .catch(() => false)
      if (ready) return page
    }
    await new Promise((r) => setTimeout(r, 100))
  }
  throw new Error('main-window shell never mounted')
}

async function openDetail(page, id) {
  await page.evaluate((cid) => {
    window.location.hash = `#/conversations/${cid}`
  }, id)
}

describe('ConversationDetail — Mac-faithful redesign', () => {
  test('detail page, transcript drawer, speaker naming, rename, processing', async (t) => {
    mkdirSync(shotsDir, { recursive: true })
    const { app, cleanup } = await launch()
    t.after(cleanup)

    const page = await mainPage(app)
    await page.setViewportSize({ width: 1280, height: 800 })
    const unexpected = await stubBackend(page)

    // ── 1. The detail page ────────────────────────────────────────────────
    await openDetail(page, 'e2e-conv-1')
    await page
      .getByRole('heading', { level: 1, name: 'Roadmap sync' })
      .waitFor({ state: 'visible', timeout: 15000 })

    // Summary rendered as markdown (the bullet list becomes real <li>s).
    await page.getByText('Ship the Windows parity release').waitFor({ state: 'visible' })
    // Action items are interactive (Windows stays ahead of Mac here).
    const openItem = page.getByTitle('Mark as done').first()
    await openItem.waitFor({ state: 'visible' })
    // No star button in the detail header (Mac parity).
    assert.equal(await page.getByTitle('Star').count(), 0, 'detail header must have no star button')

    await page.screenshot({ path: path.join(shotsDir, '01-detail-page.png') })

    // ── 2. Transcript drawer ──────────────────────────────────────────────
    const drawer = page.getByTestId('transcript-drawer')
    assert.equal(
      await drawer.getAttribute('data-open'),
      'false',
      'drawer must be CLOSED by default (Mac parity)'
    )

    await page.getByRole('button', { name: /View Transcript/ }).click()
    await page.waitForFunction(
      () => document.querySelector('[data-testid=transcript-drawer]')?.dataset.open === 'true'
    )
    await page.waitForTimeout(400) // let the 0.25s slide settle

    const width = await drawer.evaluate((el) => el.getBoundingClientRect().width)
    assert.equal(Math.round(width), 450, `drawer must be exactly 450px, got ${width}`)

    // Multi-speaker bubbles + the user bubble + the italic translation bubble.
    await page
      .getByText('Okay, let us start with the roadmap for Q3.')
      .waitFor({ state: 'visible' })
    await page
      .getByText('And the transcription backlog keeps growing.')
      .waitFor({ state: 'visible' })
    // The named person resolved from the account-wide roster.
    await page
      .getByRole('button', { name: /Nikita/ })
      .first()
      .waitFor({ state: 'visible' })

    await page.screenshot({ path: path.join(shotsDir, '02-transcript-drawer.png') })

    // ── 3. NameSpeaker modal ──────────────────────────────────────────────
    // Speaker 2 has a single segment, so the "also tag N others" toggle is hidden;
    // click Nikita (speaker 0, two segments) to see the toggle default ON.
    await page
      .getByRole('button', { name: /Nikita/ })
      .first()
      .click()
    await page
      .getByRole('heading', { name: 'Who is speaking?' })
      .waitFor({ state: 'visible', timeout: 8000 })

    const toggle = page.getByRole('checkbox')
    assert.equal(await toggle.isChecked(), true, '"also tag N others" must DEFAULT ON')
    await page.getByText(/Also tag 1 other segment from this speaker/).waitFor({ state: 'visible' })
    // Roster: You + the account-wide person + Add Person.
    await page.getByRole('button', { name: 'You', exact: true }).waitFor({ state: 'visible' })
    await page.getByRole('button', { name: /Add Person/ }).waitFor({ state: 'visible' })

    await page.screenshot({ path: path.join(shotsDir, '03-name-speaker-modal.png') })
    await page.keyboard.press('Escape')

    // ── 4. Rename modal ───────────────────────────────────────────────────
    await page.getByRole('button', { name: 'Edit title' }).click()
    await page
      .getByRole('heading', { name: 'Edit title' })
      .waitFor({ state: 'visible', timeout: 8000 })
    const field = page.getByLabel('Conversation title')
    assert.equal(await field.inputValue(), 'Roadmap sync', 'rename field seeds the current title')
    await page.screenshot({ path: path.join(shotsDir, '04-rename-modal.png') })
    await page.keyboard.press('Escape')

    // ── 5. Processing / deferred state ────────────────────────────────────
    await openDetail(page, 'e2e-conv-processing')
    await page.getByText('Processing conversation…').waitFor({ state: 'visible', timeout: 15000 })
    await page.getByText('Generating summary and action items').waitFor({ state: 'visible' })
    // Status badge shows for a non-completed conversation.
    await page.getByText('processing', { exact: true }).first().waitFor({ state: 'visible' })
    await page.screenshot({ path: path.join(shotsDir, '05-processing-state.png') })

    assert.deepEqual(unexpected, [], `no live backend calls allowed; saw: ${unexpected.join(', ')}`)
  })
})
