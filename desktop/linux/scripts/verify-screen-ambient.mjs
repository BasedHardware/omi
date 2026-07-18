// One-off verification: does the always-on ambient screen block cause the backend
// to narrate the screen on UNRELATED messages? Hits the real /v2/messages with a
// Firebase token (env OMI_TOKEN), sending the exact framing readCurrentScreen()
// produces. Reads the SSE reply and reports whether it mentions the screen.
//
//   OMI_TOKEN=<firebase id token> node scripts/verify-screen-ambient.mjs
//
// Pass criteria:
//   • UNRELATED message ("what is 17 * 23?")  → reply must NOT mention the screen.
//   • SCREEN message ("what's on my screen?") → reply SHOULD reflect the screen text.

const OMI_BASE = process.env.VITE_OMI_API_BASE ?? 'https://api.omi.me'
const TOKEN = process.env.OMI_TOKEN
if (!TOKEN) {
  console.error('Set OMI_TOKEN to a fresh Firebase ID token.')
  process.exit(2)
}

// A representative "what's on screen" OCR blob, framed EXACTLY as the app does.
const FAKE_OCR = [
  'Visual Studio Code — invoice_parser.py',
  'def parse_invoice(path): total = 0  # TODO sum line items',
  'Terminal: pytest -k invoice  ... 3 failed, 12 passed',
  'Slack — #billing  "did the parser ship?"'
].join('\n')

const screenBlock = `[Screen context — OCR of what is on the user's screen right now, provided as background only. Use it ONLY if the user's message is about what is on their screen. If it is not, ignore this completely: do not describe, summarize, or mention the screen.]
${FAKE_OCR}`

async function ask(userMsg) {
  const text = `${screenBlock}\n\n${userMsg}`
  const res = await fetch(`${OMI_BASE}/v2/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${TOKEN}` },
    body: JSON.stringify({ text })
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`)
  // Same SSE parsing the app uses: strip `data:`/`done:`/`think:`, restore __CRLF__.
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let reply = ''
  const consume = (line) => {
    if (!line || line.startsWith('done:')) return
    const content = line.startsWith('data:') ? line.slice(5).replace(/^ /, '') : line
    if (content.startsWith('think:')) return
    reply += content.replace(/__CRLF__/g, '\n')
  }
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const l of lines) consume(l)
  }
  consume(buffer)
  return reply.trim()
}

// Heuristic: does the reply talk about the screen / the OCR'd content?
const SCREEN_WORDS = /\b(screen|on your display|invoice_parser|pytest|parse_invoice|slack|billing|terminal|vs ?code|visual studio code|line items)\b/i

async function main() {
  const cases = [
    { kind: 'UNRELATED', msg: 'What is 17 * 23?', wantScreen: false },
    { kind: 'UNRELATED', msg: 'Give me a one-sentence tip for staying focused.', wantScreen: false },
    { kind: 'SCREEN', msg: "What's on my screen right now?", wantScreen: true }
  ]
  let allPass = true
  for (const c of cases) {
    const reply = await ask(c.msg)
    const mentioned = SCREEN_WORDS.test(reply)
    const pass = mentioned === c.wantScreen
    allPass &&= pass
    console.log(`\n[${c.kind}] ${pass ? 'PASS' : 'FAIL'}  (mentioned screen: ${mentioned}, wanted: ${c.wantScreen})`)
    console.log(`  Q: ${c.msg}`)
    console.log(`  A: ${reply.replace(/\n/g, ' ').slice(0, 300)}`)
  }
  console.log(`\n=== ${allPass ? 'ALL PASS — ambient framing holds' : 'FAIL — framing leaks narration, escalate'} ===`)
  process.exit(allPass ? 0 : 1)
}
main().catch((e) => {
  console.error(e)
  process.exit(1)
})
