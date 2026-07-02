// Dev utility: captures PNG screenshots of every renderer page via CDP.
// Usage: node scripts/cdp-screenshot.cjs [port] [outDir]
const http = require('http')
const fs = require('fs')
const path = require('path')
const WebSocket = require('ws')

const port = process.argv[2] || '9333'
const outDir = process.argv[3] || path.join(__dirname, '..', 'shots')
const CDP_TIMEOUT_MS = 10000

function getJson(url) {
  return new Promise((resolve, reject) => {
    const req = http
      .get(url, (res) => {
        if (res.statusCode !== 200) {
          res.resume()
          reject(new Error(`${url} returned HTTP ${res.statusCode}`))
          return
        }
        let data = ''
        res.on('data', (c) => (data += c))
        res.on('end', () => {
          try {
            resolve(JSON.parse(data))
          } catch (e) {
            reject(e)
          }
        })
      })
      .on('error', reject)
    req.setTimeout(CDP_TIMEOUT_MS, () => req.destroy(new Error(`${url} timed out`)))
  })
}

async function capture(target, index) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(target.webSocketDebuggerUrl, { maxPayload: 256 * 1024 * 1024 })
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
      new Promise((res, rej) => {
        if (ws.readyState !== WebSocket.OPEN) {
          rej(new Error(`CDP socket is not open for ${method}`))
          return
        }
        const msgId = ++id
        const timer = setTimeout(() => {
          pending.delete(msgId)
          rej(new Error(`CDP ${method} timed out`))
        }, CDP_TIMEOUT_MS)
        pending.set(msgId, { resolve: res, reject: rej, timer })
        ws.send(JSON.stringify({ id: msgId, method, params }), (err) => {
          if (!err) return
          clearTimeout(timer)
          pending.delete(msgId)
          rej(err)
        })
      })
    ws.on('open', async () => {
      try {
        await send('Page.enable')
        const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
        const title = (target.title || `page${index}`).replace(/[^a-z0-9-]/gi, '_').slice(0, 40)
        const file = path.join(outDir, `${index}_${title}.png`)
        fs.writeFileSync(file, Buffer.from(shot.data, 'base64'))
        console.log('saved', file)
      } catch (e) {
        console.error('capture failed for', target.title, e.message)
      }
      ws.close()
      resolve()
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
      }
    })
    ws.on('error', (err) => {
      failAll(err)
      resolve()
    })
    ws.on('close', () => failAll(new Error('CDP socket closed')))
  })
}

;(async () => {
  fs.mkdirSync(outDir, { recursive: true })
  const targets = await getJson(`http://127.0.0.1:${port}/json/list`)
  const pages = targets.filter((t) => t.type === 'page')
  if (pages.length === 0) {
    console.error('no pages found')
    process.exit(1)
  }
  for (let i = 0; i < pages.length; i++) await capture(pages[i], i)
})()
