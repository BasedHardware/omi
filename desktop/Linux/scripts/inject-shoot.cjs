// Dev utility: inject sample data into the exposed zustand stores, then screenshot
// the data-driven pages so the populated UI can be verified against the Mac app.
// Usage: node scripts/inject-shoot.cjs <port> <outDir>
const http = require('http')
const fs = require('fs')
const path = require('path')
const WebSocket = require('ws')

const port = process.argv[2]
const outDir = process.argv[3]
const CDP_TIMEOUT_MS = 10000

function list() {
  return new Promise((res, rej) => {
    const req = http.get(`http://127.0.0.1:${port}/json/list`, (r) => {
      if (r.statusCode !== 200) {
        r.resume()
        rej(new Error(`/json/list returned HTTP ${r.statusCode}`))
        return
      }
      let d = ''
      r.on('data', (c) => (d += c))
      r.on('end', () => {
        try {
          res(JSON.parse(d))
        } catch (e) {
          rej(e)
        }
      })
    }).on('error', rej)
    req.setTimeout(CDP_TIMEOUT_MS, () => req.destroy(new Error('/json/list timed out')))
  })
}

const INJECT = `(() => {
  const now = new Date().toISOString();
  const s = window.__omiStores; if (!s) return 'no stores';
  s.chat.setState({ historyLoaded: true, sessionId: null, messages: [
    { id:'u1', role:'user', text:'What should I focus on this morning?', createdAt: now },
    { id:'a1', role:'assistant', text:'You have three things on deck. Start with **the Q3 report** (due today, high priority), then clear the design feedback, and book the offsite when you get a moment. Want me to draft the report outline?', createdAt: now, rating: 0 },
    { id:'u2', role:'user', text:'Yes, draft it please.', createdAt: now },
    { id:'a2', role:'assistant', text:'Here is a tight outline:\\n\\n1. Headline metrics vs target\\n2. What moved the numbers\\n3. Risks for Q4\\n4. Asks\\n\\nExpand each into two or three bullets and you are done.', createdAt: now, rating: 0 }
  ]});
  s.tasks.setState({ loading:false, error:null, staged:[], incomplete: [
    { id:'t1', description:'Finish the Q3 report', completed:false, priority:'high', due_at: now, indent_level:0, sort_order:1000 },
    { id:'t2', description:'Reply to the design feedback', completed:false, priority:'medium', indent_level:0, sort_order:2000 },
    { id:'t3', description:'Book the team offsite', completed:false, priority:'low', indent_level:1, sort_order:3000 }
  ], completed: [
    { id:'t4', description:'Ship the Linux desktop build', completed:true, priority:'medium', indent_level:0, sort_order:0 }
  ]});
  return 'ok';
})()`

;(async () => {
  fs.mkdirSync(outDir, { recursive: true })
  const target = (await list()).find((t) => t.url === 'http://localhost:5173/')
  if (!target) {
    console.error('dev renderer target not found')
    process.exit(2)
  }
  const ws = new WebSocket(target.webSocketDebuggerUrl, { maxPayload: 256 * 1024 * 1024 })
  let id = 0
  const pending = new Map()
  const send = (method, params = {}) =>
    new Promise((res) => {
      const i = ++id
      pending.set(i, res)
      ws.send(JSON.stringify({ id: i, method, params }))
    })
  ws.on('message', (raw) => {
    const m = JSON.parse(raw.toString())
    if (m.id && pending.has(m.id)) {
      pending.get(m.id)(m.result || {})
      pending.delete(m.id)
    }
  })
  await new Promise((r) => ws.on('open', r))
  await send('Runtime.enable')
  await send('Page.enable')
  const r = await send('Runtime.evaluate', { expression: INJECT, returnByValue: true })
  console.log('inject:', r && r.result && r.result.value)
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
  for (const page of ['chat', 'tasks', 'dashboard']) {
    await send('Runtime.evaluate', { expression: `window.__omiPreviewNavigate && window.__omiPreviewNavigate('${page}')` })
    await sleep(1600)
    const shot = await send('Page.captureScreenshot', { format: 'png' })
    fs.writeFileSync(path.join(outDir, `${page}.png`), Buffer.from(shot.data, 'base64'))
    console.log('saved', page)
  }
  ws.close()
  process.exit(0)
})()
