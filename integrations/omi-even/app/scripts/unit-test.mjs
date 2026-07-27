#!/usr/bin/env node
/**
 * Hermetic unit tests for the parts of the app that do not need glasses:
 * pagination, the bridge wire format, background-state snapshotting, and the
 * microphone lifecycle behind "Ask Omi".
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
const { toPcmBytes, peakLevel, meterBar, clock } = await import('../src/audio.ts')
const { AskRecorder } = await import('../src/ask-recorder.ts')

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

/** Same reporting, for a test that has to await something. Queued so the
 *  output stays in order. */
let chain = Promise.resolve()
function asyncTest(name, fn) {
  count++
  chain = chain.then(async () => {
    try {
      await fn()
      console.log(`  PASS  ${name}`)
    } catch (error) {
      failures++
      console.log(`  FAIL  ${name}`)
      console.log(`        ${error.message.split('\n').join('\n        ')}`)
    }
  })
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

// --------------------------------------------------------------------- audio

test('toPcmBytes: a Uint8Array is passed straight through', () => {
  const pcm = new Uint8Array([1, 2, 3, 4])
  assert.equal(toPcmBytes(pcm), pcm)
})

test('toPcmBytes: the host may hand over a number[] instead of bytes', () => {
  // The host is a Flutter app: a Uint8List crossing a JSON channel arrives as
  // an array of numbers, and forwarding that object as-is would send garbage.
  assert.deepEqual(toPcmBytes([0, 128, 255]), new Uint8Array([0, 128, 255]))
})

test('toPcmBytes: base64 is decoded', () => {
  globalThis.atob = globalThis.atob ?? ((s) => Buffer.from(s, 'base64').toString('binary'))
  assert.deepEqual(toPcmBytes('AAECAw=='), new Uint8Array([0, 1, 2, 3]))
})

test('toPcmBytes: an ArrayBuffer view respects its offset', () => {
  const backing = new Uint8Array([9, 9, 1, 2, 3])
  const view = new Uint8Array(backing.buffer, 2, 3)
  assert.deepEqual(toPcmBytes(view), new Uint8Array([1, 2, 3]))
})

test('toPcmBytes: anything that is not audio yields null, never a bad frame', () => {
  assert.equal(toPcmBytes(undefined), null)
  assert.equal(toPcmBytes(null), null)
  assert.equal(toPcmBytes({}), null)
  assert.equal(toPcmBytes([]), null)
  assert.equal(toPcmBytes(new Uint8Array(0)), null)
  assert.equal(toPcmBytes(['a', 'b']), null)
  assert.equal(toPcmBytes('not base64 !!!'), null)
})

test('peakLevel: reads samples as signed 16-bit little-endian', () => {
  assert.equal(peakLevel(new Uint8Array([0, 0, 0, 0])), 0)
  // 0x8000 little-endian is -32768, full scale negative.
  assert.equal(peakLevel(new Uint8Array([0x00, 0x80])), 1)
  // Big-endian would read 0x0080 = 128 here and report near silence.
  assert.ok(peakLevel(new Uint8Array([0x00, 0x40])) > 0.49)
  assert.ok(peakLevel(new Uint8Array([0x40, 0x00])) < 0.01)
})

test('peakLevel: an odd trailing byte cannot form a sample and is ignored', () => {
  assert.equal(peakLevel(new Uint8Array([0x00, 0x00, 0xff])), 0)
})

test('meterBar: fills with level and always keeps its width', () => {
  assert.equal(meterBar(0, 8), '[--------]')
  assert.equal(meterBar(1, 8), '[########]')
  const quiet = meterBar(0.05, 8)
  const loud = meterBar(0.5, 8)
  assert.ok(quiet.split('#').length - 1 < loud.split('#').length - 1)
  assert.equal(quiet.length, loud.length)
  // Out-of-range input must not produce a ragged bar.
  assert.equal(meterBar(-5, 8), '[--------]')
  assert.equal(meterBar(99, 8), '[########]')
})

test('clock: m:ss with a padded seconds field', () => {
  assert.equal(clock(0), '0:00')
  assert.equal(clock(9_400), '0:09')
  assert.equal(clock(65_000), '1:05')
  assert.equal(clock(-1), '0:00')
})

// ------------------------------------------------------------- ask recorder

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

/** The recorder narrates to the console; tests only care about the effects. */
async function quiet(fn) {
  const log = console.log
  const warn = console.warn
  console.log = () => {}
  console.warn = () => {}
  try {
    return await fn()
  } finally {
    console.log = log
    console.warn = warn
  }
}

function harness(overrides = {}) {
  const calls = { json: [], binary: [], mic: [], caps: 0 }
  const deps = {
    sendJson: (message) => {
      calls.json.push(message.type)
      return true
    },
    sendBinary: (pcm) => {
      calls.binary.push(pcm.length)
      return true
    },
    setMic: async (on) => {
      calls.mic.push(on)
      return true
    },
    onUpdate: () => {},
    onCap: () => {
      calls.caps++
    },
    maxMs: 10_000,
    // Long enough that the meter tick never fires unless a test wants it.
    tickMs: 10_000,
    ...overrides,
  }
  return { calls, recorder: new AskRecorder(deps) }
}

/** One 100 ms frame of 16 kHz PCM16, the size the SDK actually delivers. */
const frame = () => new Uint8Array(3_200)

asyncTest('ask: the bridge is told before the microphone opens', async () => {
  const { calls, recorder } = harness()
  await quiet(() => recorder.start())
  // ask_start first: a microphone with nowhere to send costs battery for
  // nothing, so the socket is proven before the hardware is touched.
  assert.deepEqual(calls.json, ['ask_start'])
  assert.deepEqual(calls.mic, [true])
  await quiet(() => recorder.stop('tap'))
})

asyncTest('ask: PCM only goes out between ask_start and ask_stop', async () => {
  const { calls, recorder } = harness()

  recorder.feed(frame()) // before start
  assert.deepEqual(calls.binary, [], 'a frame before ask_start must not be sent')

  await quiet(() => recorder.start())
  recorder.feed(frame())
  recorder.feed(frame())
  assert.deepEqual(calls.binary, [3_200, 3_200])

  await quiet(() => recorder.stop('tap'))
  recorder.feed(frame()) // after stop
  assert.deepEqual(calls.binary, [3_200, 3_200], 'a frame after ask_stop must not be sent')
  assert.deepEqual(calls.json, ['ask_start', 'ask_stop'])
  assert.equal(recorder.bytesSent, 6_400)
  assert.equal(recorder.framesSent, 2)
  assert.equal(recorder.framesIgnored, 2)
})

asyncTest('ask: stopping closes the microphone and closes the bracket', async () => {
  const { calls, recorder } = harness()
  await quiet(() => recorder.start())
  const asked = await quiet(() => recorder.stop('tap'))
  assert.equal(asked, true)
  assert.deepEqual(calls.mic, [true, false])
  assert.deepEqual(calls.json, ['ask_start', 'ask_stop'])
  assert.equal(recorder.isListening(), false)
})

asyncTest('ask: a cancel still sends ask_stop, because the bridge is holding a buffer', async () => {
  const { calls, recorder } = harness()
  await quiet(() => recorder.start())
  const asked = await quiet(() => recorder.stop('cancel'))
  assert.equal(asked, true)
  assert.deepEqual(calls.json, ['ask_start', 'ask_stop'])
  assert.deepEqual(calls.mic, [true, false])
})

asyncTest('ask: an offline bridge never opens the microphone', async () => {
  const { calls, recorder } = harness({ sendJson: () => false })
  const started = await quiet(() => recorder.start())
  assert.deepEqual(started, { ok: false, reason: 'offline' })
  assert.deepEqual(calls.mic, [])
  assert.equal(recorder.isListening(), false)
})

asyncTest('ask: a microphone that will not open closes the bracket it opened', async () => {
  const { calls, recorder } = harness({ setMic: async () => false })
  const started = await quiet(() => recorder.start())
  assert.deepEqual(started, { ok: false, reason: 'mic' })
  // Without this the bridge stays in ask mode and files the next frame it sees
  // as part of a question nobody asked.
  assert.deepEqual(calls.json, ['ask_start', 'ask_stop'])
  assert.equal(recorder.isListening(), false)
})

asyncTest('ask: stop reports false when ask_stop could not be sent', async () => {
  let online = true
  const { recorder } = harness({ sendJson: () => online })
  await quiet(() => recorder.start())
  online = false
  // No answer is owed when the bridge never heard the question, so the caller
  // must not sit waiting for one.
  assert.equal(await quiet(() => recorder.stop('tap')), false)
})

asyncTest('ask: the cap fires on its own and the stop path is the same one', async () => {
  const { calls, recorder } = harness({ maxMs: 30 })
  await quiet(() => recorder.start())
  await sleep(80)
  assert.equal(calls.caps, 1, 'the cap should have fired')
  // main.ts runs its normal stop from onCap; do the same and check the effects.
  await quiet(() => recorder.stop('cap'))
  assert.deepEqual(calls.mic, [true, false])
  assert.deepEqual(calls.json, ['ask_start', 'ask_stop'])
})

asyncTest('ask: stopping cancels the cap, so a later timer cannot fire', async () => {
  const { calls, recorder } = harness({ maxMs: 30 })
  await quiet(() => recorder.start())
  await quiet(() => recorder.stop('tap'))
  await sleep(80)
  assert.equal(calls.caps, 0)
})

asyncTest('ask: teardown releases the microphone without awaiting anything', async () => {
  const { calls, recorder } = harness()
  await quiet(() => recorder.start())
  quiet(() => recorder.teardown())
  assert.equal(recorder.isListening(), false)
  assert.deepEqual(calls.json, ['ask_start', 'ask_stop'])
  await sleep(0)
  assert.deepEqual(calls.mic, [true, false])
})

asyncTest('ask: stopping twice is a no-op, not a second ask_stop', async () => {
  const { calls, recorder } = harness()
  await quiet(() => recorder.start())
  await quiet(() => recorder.stop('tap'))
  assert.equal(await quiet(() => recorder.stop('cancel')), false)
  assert.deepEqual(calls.json, ['ask_start', 'ask_stop'])
})

asyncTest('ask: a dropped frame is counted, not retried forever', async () => {
  const { recorder } = harness({ sendBinary: () => false })
  await quiet(() => recorder.start())
  recorder.feed(frame())
  recorder.feed(frame())
  assert.equal(recorder.bytesSent, 0)
  assert.equal(recorder.framesDropped, 2)
  await quiet(() => recorder.stop('tap'))
})

asyncTest('ask: a frame that is not audio is dropped rather than sent', async () => {
  const { calls, recorder } = harness()
  await quiet(() => recorder.start())
  recorder.feed({ nope: true })
  recorder.feed(null)
  assert.deepEqual(calls.binary, [])
  assert.equal(recorder.framesDropped, 2)
  await quiet(() => recorder.stop('tap'))
})

// ---------------------------------------------------------------------- exit

await chain

console.log(
  failures === 0 ? `\nAll ${count} unit tests passed.\n` : `\n${failures} of ${count} unit tests failed.\n`,
)
process.exit(failures === 0 ? 0 : 1)
