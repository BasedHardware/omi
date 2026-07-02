// Walk the PACKAGED app: navigate by clicking the real sidebar buttons (by title)
// over CDP and screenshot each screen. No dev-only hooks (those are stripped from
// production); this exercises the actual navigation.
// Usage: node scripts/pkg-shoot.cjs <port> <outDir>
const http = require('http')
const fs = require('fs')
const path = require('path')
const WebSocket = require('ws')

const port = process.argv[2]
const outDir = process.argv[3]
const CDP_TIMEOUT_MS = 10000

// [filename, sidebar button title]
const PAGES = [
  ['dashboard', 'Dashboard'],
  ['conversations', 'Conversations'],
  ['chat', 'Chat'],
  ['memories', 'Memories'],
  ['tasks', 'Tasks'],
  ['rewind', 'Rewind'],
  ['apps', 'Apps'],
  ['goals', 'Goals'],
  ['focus', 'Focus'],
  ['insights', 'Insights'],
  ['graph', 'Graph'],
  ['persona', 'AI Persona'],
  ['settings', 'Settings']
]

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

function createCdpSender(ws) {
  let id = 0
  const pending = new Map()
  const failAll = (err) => {
    for (const [, p] of pending) {
      clearTimeout(p.timer)
      p.reject(err)
    }
    pending.clear()
  }
  const send = (method, params = {}) =>
    new Promise((resolve, reject) => {
      if (ws.readyState !== WebSocket.OPEN) {
        reject(new Error(`CDP socket is not open for ${method}`))
        return
      }
      const msgId = ++id
      const timer = setTimeout(() => {
        pending.delete(msgId)
        reject(new Error(`CDP ${method} timed out`))
      }, CDP_TIMEOUT_MS)
      pending.set(msgId, { resolve, reject, timer })
      ws.send(JSON.stringify({ id: msgId, method, params }), (err) => {
        if (!err) return
        clearTimeout(timer)
        pending.delete(msgId)
        reject(err)
      })
    })
  ws.on('message', (raw) => {
    let m
    try {
      m = JSON.parse(raw.toString())
    } catch {
      return
    }
    if (m.id && pending.has(m.id)) {
      const p = pending.get(m.id)
      pending.delete(m.id)
      clearTimeout(p.timer)
      if (m.error) p.reject(new Error(m.error.message || JSON.stringify(m.error)))
      else p.resolve(m.result || {})
    }
  })
  ws.on('error', failAll)
  ws.on('close', () => failAll(new Error('CDP socket closed')))
  return send
}

;(async () => {
  fs.mkdirSync(outDir, { recursive: true })
  const targets = await list()
  // Main window = the page target loading index.html (not the floating bar or glow overlay).
  const target =
    targets.find((t) => t.type === 'page' && /index\.html/.test(t.url) && !/floating|glow/.test(t.url)) ||
    targets.find((t) => t.type === 'page' && !/floating|glow|devtools/.test(t.url))
  if (!target) {
    console.log('NO main target. targets:', targets.map((t) => `${t.type}:${t.url}`).join(' | '))
    process.exit(2)
  }
  console.log('main target:', target.url)
  const ws = new WebSocket(target.webSocketDebuggerUrl, { maxPayload: 256 * 1024 * 1024 })
  const errors = []
  let send
  ws.on('message', (raw) => {
    let m
    try {
      m = JSON.parse(raw.toString())
    } catch {
      return
    }
    if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') {
      errors.push((m.params.args || []).map((a) => a.value || a.description || '').join(' '))
    } else if (m.method === 'Runtime.exceptionThrown') {
      errors.push('EXCEPTION: ' + (m.params.exceptionDetails && m.params.exceptionDetails.text))
    }
  })
  await new Promise((r) => ws.on('open', r))
  send = createCdpSender(ws)
  await send('Page.enable')
  await send('Runtime.enable')
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
  for (const [file, title] of PAGES) {
    const clicked = await send('Runtime.evaluate', {
      expression: `(() => { const b = document.querySelector('button[title=${JSON.stringify(title)}]'); if (b) { b.click(); return true } return false })()`,
      returnByValue: true
    })
    if (!clicked?.result?.value) throw new Error(`nav target not found: ${title}`)
    await sleep(1500)
    const shot = await send('Page.captureScreenshot', { format: 'png' })
    fs.writeFileSync(path.join(outDir, `${file}.png`), Buffer.from(shot.data, 'base64'))
    console.log('saved', file, '(nav clicked:', clicked && clicked.result && clicked.result.value, ')')
  }
  if (errors.length) {
    console.log('CONSOLE ERRORS (' + errors.length + '):')
    errors.slice(0, 20).forEach((e) => console.log('  ', e))
  } else {
    console.log('NO console errors during walkthrough')
  }
  ws.close()
  process.exit(0)
})()
