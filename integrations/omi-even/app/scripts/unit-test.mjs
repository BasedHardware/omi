#!/usr/bin/env node
/**
 * Hermetic unit tests for the parts of the app that do not need glasses:
 * pagination, the bridge wire format, and background-state snapshotting.
 *
 * No simulator, no GUI, no network — unlike `verify-simulator.mjs` this is safe
 * to run anywhere, including CI. Uses Node's built-in TypeScript stripping, so
 * it imports `src/*.ts` directly with no build step.
 *
 * Usage: npm test
 */
import assert from 'node:assert/strict'

// `background-state.ts` installs its hooks on `window`; give it one before the
// module is imported, since Node has no DOM.
globalThis.window = globalThis.window ?? {}

const { paginate, clampPage } = await import('../src/paginate.ts')
const { parseInbound, frameType } = await import('../src/protocol.ts')
const { setBackgroundState, onBackgroundRestore } = await import('../src/background-state.ts')

let failures = 0
let count = 0

function test(name, fn) {
  count++
  try {
    fn()
    console.log(`  PASS  ${name}`)
  } catch (error) {
    failures++
    console.log(`  FAIL  ${name}`)
    console.log(`        ${error.message.split('\n').join('\n        ')}`)
  }
}

// ------------------------------------------------------------------ paginate

test('paginate: text shorter than the limit stays on one page', () => {
  assert.deepEqual(paginate('hello glasses', 380), ['hello glasses'])
})

test('paginate: empty text still yields one (empty) page', () => {
  assert.deepEqual(paginate('   \n  ', 380), [''])
})

test('paginate: every page fits the limit', () => {
  const text = Array.from({ length: 200 }, (_, i) => `sentence number ${i}`).join('. ')
  const pages = paginate(text, 380)
  assert.ok(pages.length > 1, `expected several pages, got ${pages.length}`)
  for (const page of pages) assert.ok(page.length <= 380, `page of ${page.length} chars exceeds 380`)
})

test('paginate: no word is split across a page boundary', () => {
  const text = Array.from({ length: 300 }, (_, i) => `word${i}`).join(' ')
  const pages = paginate(text, 100)
  // Re-joining with single spaces must reproduce the original word sequence.
  assert.deepEqual(pages.join(' ').split(/\s+/), text.split(/\s+/))
})

test('paginate: a word longer than a whole page is hard-cut rather than dropped', () => {
  const long = 'x'.repeat(250)
  const pages = paginate(long, 100)
  assert.equal(pages.join(''), long)
  assert.equal(pages.length, 3)
})

test('paginate: prefers a paragraph break over a mid-sentence space', () => {
  const first = 'a'.repeat(60)
  const second = 'b'.repeat(60)
  const pages = paginate(`${first}\n\n${second} tail words here`, 80)
  assert.equal(pages[0], first)
})

test('clampPage: keeps the index inside the page range', () => {
  assert.equal(clampPage(-3, 4), 0)
  assert.equal(clampPage(9, 4), 3)
  assert.equal(clampPage(2, 4), 2)
  assert.equal(clampPage(2, 0), 0)
})

// ------------------------------------------------------------------ protocol

test('parseInbound: accepts each documented message type', () => {
  assert.deepEqual(parseInbound('{"type":"chat_delta","text":"hi"}'), { type: 'chat_delta', text: 'hi' })
  assert.deepEqual(parseInbound('{"type":"chat_done","text":"done"}'), { type: 'chat_done', text: 'done' })
  assert.deepEqual(parseInbound('{"type":"today","text":"t"}'), { type: 'today', text: 't' })
  assert.deepEqual(parseInbound('{"type":"push","text":"p"}'), { type: 'push', text: 'p' })
  assert.deepEqual(parseInbound('{"type":"memories","items":[{"content":"m"}]}'), {
    type: 'memories',
    items: [{ content: 'm' }],
  })
  assert.deepEqual(parseInbound('{"type":"action_items","items":[{"description":"d","completed":true}]}'), {
    type: 'action_items',
    items: [{ description: 'd', completed: true }],
  })
})

test('parseInbound: a missing `completed` defaults to false rather than undefined', () => {
  assert.deepEqual(parseInbound('{"type":"action_items","items":[{"description":"d"}]}'), {
    type: 'action_items',
    items: [{ description: 'd', completed: false }],
  })
})

test('parseInbound: drops malformed items instead of rendering "undefined"', () => {
  assert.deepEqual(parseInbound('{"type":"memories","items":[{"content":"ok"},{},null,{"content":7}]}'), {
    type: 'memories',
    items: [{ content: 'ok' }],
  })
})

test('parseInbound: returns null for junk, so the socket callback cannot throw', () => {
  assert.equal(parseInbound('not json'), null)
  assert.equal(parseInbound('null'), null)
  assert.equal(parseInbound('[1,2,3]'), null)
  assert.equal(parseInbound('{"type":"chat_delta"}'), null)
  assert.equal(parseInbound('{"type":"memories"}'), null)
  assert.equal(parseInbound('{"type":"from_the_future","text":"x"}'), null)
})

test('frameType: names the type of a frame the app does not handle', () => {
  // The real bridge greets with `hello` and emits `transcript` / `pong`; none
  // are errors, so they must be identifiable for a quiet debug log.
  assert.equal(frameType('{"type":"hello","omi_api":"https://x"}'), 'hello')
  assert.equal(frameType('{"type":"transcript","text":"..."}'), 'transcript')
  assert.equal(frameType('not json'), null)
  assert.equal(frameType('{"no":"type"}'), null)
})

// ---------------------------------------------------------- background state

test('background state: a snapshot survives the round trip', () => {
  let value = { page: 3, label: 'chat' }
  setBackgroundState('round-trip', () => ({ ...value }))
  onBackgroundRestore('round-trip', (saved) => {
    value = { ...value, ...saved }
  })

  const snapshot = window.__getStateSnapshot()
  // The headless WebView starts from scratch; simulate that reset.
  value = { page: 0, label: '' }
  window.__restoreState(snapshot)

  assert.deepEqual(value, { page: 3, label: 'chat' })
})

test('background state: the snapshot is plain JSON', () => {
  const snapshot = JSON.parse(window.__getStateSnapshot())
  assert.equal(typeof snapshot, 'object')
  assert.deepEqual(snapshot['round-trip'], { page: 3, label: 'chat' })
})

test('background state: the exporter captures a copy, not a live reference', () => {
  let live = { n: 1 }
  setBackgroundState('copy', () => ({ ...live }))
  const snapshot = window.__getStateSnapshot()
  live.n = 99 // mutate after the snapshot was taken
  assert.equal(JSON.parse(snapshot).copy.n, 1)
})

test('background state: one throwing exporter does not cost the other keys', () => {
  setBackgroundState('explodes', () => {
    throw new Error('boom')
  })
  const snapshot = JSON.parse(window.__getStateSnapshot())
  assert.deepEqual(snapshot['round-trip'], { page: 3, label: 'chat' })
  assert.equal('explodes' in snapshot, false)
})

test('background state: a key absent from the snapshot leaves its state alone', () => {
  let untouched = 'original'
  onBackgroundRestore('never-exported', (saved) => {
    untouched = saved.value ?? untouched
  })
  window.__restoreState('{}')
  assert.equal(untouched, 'original')
})

test('background state: invalid snapshot JSON is ignored, not thrown', () => {
  assert.doesNotThrow(() => window.__restoreState('}{'))
  assert.doesNotThrow(() => window.__restoreState('null'))
})

// ---------------------------------------------------------------------- exit

console.log(
  failures === 0 ? `\nAll ${count} unit tests passed.\n` : `\n${failures} of ${count} unit tests failed.\n`,
)
process.exit(failures === 0 ? 0 : 1)
