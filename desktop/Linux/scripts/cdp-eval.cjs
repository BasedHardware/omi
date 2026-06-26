// Dev utility: evaluate a JS expression in a renderer page via CDP.
// Usage: node scripts/cdp-eval.cjs <port> <target-url-or-title-substring> <expression>
const http = require('http')
const WebSocket = require('ws')

const [, , port, filter, ...exprParts] = process.argv
const expression = exprParts.join(' ')

function getJson(url) {
  return new Promise((resolve, reject) => {
    http
      .get(url, (res) => {
        let data = ''
        res.on('data', (c) => (data += c))
        res.on('end', () => resolve(JSON.parse(data)))
      })
      .on('error', reject)
  })
}

;(async () => {
  const targets = await getJson(`http://127.0.0.1:${port}/json/list`)
  const target = targets.find(
    (t) => t.type === 'page' && ((t.url || '').includes(filter) || (t.title || '').includes(filter))
  )
  if (!target) {
    console.error('NO_TARGET', JSON.stringify(targets.map((t) => ({ type: t.type, title: t.title, url: t.url }))))
    process.exit(2)
  }
  const ws = new WebSocket(target.webSocketDebuggerUrl)
  ws.on('open', () => {
    ws.send(
      JSON.stringify({
        id: 1,
        method: 'Runtime.evaluate',
        params: { expression, awaitPromise: true, returnByValue: true }
      })
    )
  })
  ws.on('message', (raw) => {
    const msg = JSON.parse(raw.toString())
    if (msg.id === 1) {
      if (msg.result?.exceptionDetails) {
        console.error('EVAL_ERROR', JSON.stringify(msg.result.exceptionDetails.exception?.description || msg.result.exceptionDetails))
        process.exit(3)
      }
      console.log(JSON.stringify(msg.result?.result?.value ?? null))
      ws.close()
      process.exit(0)
    }
  })
  ws.on('error', (e) => {
    console.error('WS_ERROR', e.message)
    process.exit(4)
  })
  setTimeout(() => {
    console.error('TIMEOUT')
    process.exit(5)
  }, 20000)
})()
