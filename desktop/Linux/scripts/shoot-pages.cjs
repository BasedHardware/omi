// Dev utility: navigate the main window through pages and screenshot each.
// Usage: node scripts/shoot-pages.cjs <port> <outDir> <page1> <page2> ...
const http = require('http')
const fs = require('fs')
const path = require('path')
const WebSocket = require('ws')

const port = process.argv[2]
const outDir = process.argv[3]
const pages = process.argv.slice(4)

function list() {
  return new Promise((res, rej) => {
    http.get(`http://127.0.0.1:${port}/json/list`, (r) => {
      let d = ''
      r.on('data', (c) => (d += c))
      r.on('end', () => res(JSON.parse(d)))
    }).on('error', rej)
  })
}

;(async () => {
  fs.mkdirSync(outDir, { recursive: true })
  const target = (await list()).find((t) => t.url === 'http://localhost:5173/')
  const ws = new WebSocket(target.webSocketDebuggerUrl, { maxPayload: 256 * 1024 * 1024 })
  let id = 0
  const pending = new Map()
  const send = (method, params = {}) =>
    new Promise((res) => {
      const msgId = ++id
      pending.set(msgId, res)
      ws.send(JSON.stringify({ id: msgId, method, params }))
    })
  ws.on('message', (raw) => {
    const m = JSON.parse(raw.toString())
    if (m.id && pending.has(m.id)) {
      pending.get(m.id)(m.result || {})
      pending.delete(m.id)
    }
  })
  await new Promise((r) => ws.on('open', r))
  await send('Page.enable')
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
  for (const page of pages) {
    await send('Runtime.evaluate', {
      expression: `window.__omiPreviewNavigate && window.__omiPreviewNavigate(${JSON.stringify(page)})`
    })
    await sleep(1400)
    const shot = await send('Page.captureScreenshot', { format: 'png' })
    fs.writeFileSync(path.join(outDir, `${page}.png`), Buffer.from(shot.data, 'base64'))
    console.log('saved', page)
  }
  ws.close()
  process.exit(0)
})()
