// QA probe: drives the running app via CDP, sweeps every page, and collects
// console errors/warnings, uncaught exceptions, and failed network requests.
// Usage: node scripts/probe.cjs <port>
const http = require('http')
const WebSocket = require('ws')

const port = process.argv[2] || '9333'
const CDP_TIMEOUT_MS = 10000
const PAGES = [
  'dashboard',
  'conversations',
  'chat',
  'memories',
  'tasks',
  'goals',
  'rewind',
  'focus',
  'insights',
  'graph',
  'apps',
  'settings',
  'help'
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

const issues = []

;(async () => {
  const targets = await list()
  const main = targets.find((t) => t.type === 'page' && !t.url.includes('floating') && !t.url.includes('glow'))
  const floating = targets.find((t) => t.type === 'page' && t.url.includes('floating'))
  if (!main) {
    console.error('main window not found')
    process.exit(2)
  }

  for (const [label, target] of [
    ['main', main],
    ['floating', floating]
  ]) {
    if (!target) continue
    const ws = new WebSocket(target.webSocketDebuggerUrl, { maxPayload: 64 * 1024 * 1024 })
    let currentPage = 'startup'
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
        const m = ++id
        const timer = setTimeout(() => {
          pending.delete(m)
          reject(new Error(`CDP ${method} timed out`))
        }, CDP_TIMEOUT_MS)
        pending.set(m, { resolve, reject, timer })
        ws.send(JSON.stringify({ id: m, method, params }), (err) => {
          if (!err) return
          clearTimeout(timer)
          pending.delete(m)
          reject(err)
        })
      })
    ws.on('message', (raw) => {
      let msg
      try {
        msg = JSON.parse(raw.toString())
      } catch {
        return
      }
      if (msg.id && pending.has(msg.id)) {
        const p = pending.get(msg.id)
        pending.delete(msg.id)
        clearTimeout(p.timer)
        if (msg.error) p.reject(new Error(msg.error.message || JSON.stringify(msg.error)))
        else p.resolve(msg.result || {})
        return
      }
      if (msg.method === 'Runtime.consoleAPICalled') {
        const t = msg.params.type
        if (t === 'error' || t === 'warning') {
          const text = (msg.params.args || []).map((a) => a.value ?? a.description ?? a.type).join(' ')
          issues.push({ win: label, page: currentPage, kind: `console.${t}`, text: text.slice(0, 300) })
        }
      } else if (msg.method === 'Runtime.exceptionThrown') {
        const e = msg.params.exceptionDetails
        issues.push({
          win: label,
          page: currentPage,
          kind: 'exception',
          text: (e.exception?.description || e.text || 'unknown').slice(0, 300)
        })
      } else if (msg.method === 'Network.responseReceived') {
        const r = msg.params.response
        if (r.status >= 400 && !r.url.includes('devtools')) {
          issues.push({ win: label, page: currentPage, kind: `http.${r.status}`, text: r.url.slice(0, 120) })
        }
      }
    })
    ws.on('error', failAll)
    ws.on('close', () => failAll(new Error('CDP socket closed')))
    await new Promise((r) => ws.on('open', r))
    await send('Runtime.enable')
    await send('Network.enable')
    await send('Page.enable')
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

    if (label === 'main') {
      // Confirm the nav hook is present (dev build).
      const hook = await send('Runtime.evaluate', {
        expression: 'typeof window.__omiPreviewNavigate',
        returnByValue: true
      })
      const hasHook = hook.result?.result?.value === 'function'
      await sleep(1500) // capture startup issues
      if (hasHook) {
        for (const page of PAGES) {
          currentPage = page
          await send('Runtime.evaluate', { expression: `window.__omiPreviewNavigate(${JSON.stringify(page)})` })
          await sleep(1600)
        }
      } else {
        currentPage = 'no-nav-hook(packaged or signed-out)'
        await sleep(1500)
      }
    } else {
      currentPage = 'floating'
      await sleep(1500)
    }
    ws.close()
    await sleep(200)
  }

  // Report
  console.log('\n===== PROBE RESULTS =====')
  console.log(`total issues: ${issues.length}\n`)
  const byKind = {}
  for (const i of issues) byKind[i.kind] = (byKind[i.kind] || 0) + 1
  console.log('by kind:', JSON.stringify(byKind))
  // Dedup identical text+kind
  const seen = new Set()
  for (const i of issues) {
    const key = i.kind + '|' + i.text
    if (seen.has(key)) continue
    seen.add(key)
    console.log(`[${i.win}/${i.page}] ${i.kind}: ${i.text}`)
  }
  process.exit(0)
})()
