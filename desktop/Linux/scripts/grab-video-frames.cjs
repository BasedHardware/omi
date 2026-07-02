// Dev utility: play a local mp4 in a CDP-controlled browser, seek to a set of
// timestamps, and save a PNG frame at each. Used to extract reference frames
// from the Mac app's demo videos.
// Usage: node grab-video-frames.cjs <port> <fileUrlOfVideo> <outDir> <label> <t1,t2,...>
const http = require('http')
const fs = require('fs')
const path = require('path')
const WebSocket = require('ws')

const [, , port, videoUrl, outDir, label, tsArg] = process.argv
const timestamps = tsArg.split(',').map(Number)
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

;(async () => {
  fs.mkdirSync(outDir, { recursive: true })
  const target = (await list()).find((t) => t.type === 'page' && (t.url || '').includes('player.html'))
  if (!target) {
    console.error('player.html page not found')
    process.exit(2)
  }
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
  await new Promise((r) => ws.on('open', r))
  await send('Page.enable')
  await send('Runtime.enable')

  const dur = await send('Runtime.evaluate', {
    expression: `window.loadVid(${JSON.stringify(videoUrl)})`,
    awaitPromise: true,
    returnByValue: true
  })
  console.log('duration:', dur.result?.result?.value)

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
  for (const t of timestamps) {
    await send('Runtime.evaluate', { expression: `window.seek(${t})`, awaitPromise: true, returnByValue: true })
    await sleep(400)
    const shot = await send('Page.captureScreenshot', { format: 'png' })
    if (shot.data) {
      const file = path.join(outDir, `${label}_${String(t).replace('.', 'p')}s.png`)
      fs.writeFileSync(file, Buffer.from(shot.data, 'base64'))
      console.log('saved', file)
    }
  }
  ws.close()
  process.exit(0)
})()
